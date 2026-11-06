"""Source validity and transaction-bound writes, using isolated real services."""
import importlib
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from backend import agent_calculations as calculations, core
from backend.agent_semantics import inspection, readable, model_projection, check, Delivery
from test_agent_calculations import chat, plan
from test_agent_engineering import make_plan
from test_api import create_project


KINDS = ['thermal', 'lifecycle', 'cost', 'engineering', 'schedule', 'operation']


def setup_plan(client, kind):
    project = create_project(client)
    pid = project['project_id']
    raw = plan(kind) if kind in KINDS[:3] else make_plan(client, pid, kind)
    p = chat([raw]).calculation_plans[0]
    return client.app.state.agent.domain, pid, p


def revise(domain, pid):
    p = domain.store.get('project', pid)
    p['building']['notes'] = 'Concurrent reviewed declaration'
    domain.store.put('project', p, p['revision'])


@pytest.mark.parametrize('kind', KINDS)
def test_project_change_between_plan_validation_and_save_is_rejected(client, monkeypatch, kind):
    domain, pid, p = setup_plan(client, kind)
    frozen = calculations.snapshot(domain, pid, [p])
    original = calculations.resolve
    def change_after_validation(*args):
        result = original(*args)
        revise(domain, pid)
        return result
    monkeypatch.setattr(calculations, 'resolve', change_after_validation)
    with pytest.raises(core.ValidationError, match='changed'):
        calculations.execute(domain, pid, p.plan_key, [p], frozen)
    assert not domain.store.list(kind, pid)


@pytest.mark.parametrize('kind', KINDS)
def test_revision_reason_reaches_current_artifact_without_mutating_history(client, kind):
    domain, pid, p = setup_plan(client, kind)
    spec = inspection(kind)
    service = spec.service(domain)
    record = service.save(pid, p.input)
    old = domain.store.get(kind, record[spec.record_key])
    revise(domain, pid)
    current = service.view(pid, record[spec.record_key])
    assert current['status'] == 'stale' and current['result'] is None
    assert current['stale_reasons'] == ['project_revision']
    assert spec.artifact(current)['stale_reasons'] == ['project_revision']
    detail = {'code': 'project_revision', 'subject_id': pid, 'expected': 1, 'current': 2}
    assert current['stale_details'] == [detail]
    projected = model_projection(readable(current, kind), kind)
    assert projected['limitation_delivery']['stale_details'] == [detail]
    checked = check(current, Delivery(kind=kind, record_id=record[spec.record_key], record_hash=record['hash'],
                                     statements=[], limitation_status='stale'))
    assert checked['limitation']['stale_details'] == [detail]
    assert domain.store.get(kind, record[spec.record_key]) == old


def with_evidence(client, domain, pid, p):
    ev = client.post(f'/api/projects/{pid}/evidence', json={
        'type':'literature', 'name':'Independent source', 'source_locator':'row 1', 'authority':'Audit author',
        'permission':'test only', 'acquisition_method':'test', 'responsible_person':'auditor', 'status':'IMPORTED'}).json()
    raw = p.model_dump(mode='json'); body = raw['input']; eid = ev['evidence_id']
    if p.kind == 'thermal': body['layers'][0]['evidence_id'] = eid
    elif p.kind == 'lifecycle': body['activities'][0]['factor']['evidence_id'] = eid
    elif p.kind == 'cost': body['lines'][0]['evidence_ids'] = [eid]
    else: body['evidence_ids'] = [eid]
    return chat([raw]).calculation_plans[0], ev


@pytest.mark.parametrize('kind', KINDS)
def test_evidence_revision_after_validation_cannot_rebind_frozen_plan(client, monkeypatch, kind):
    domain, pid, p = setup_plan(client, kind)
    p, ev = with_evidence(client, domain, pid, p)
    frozen = calculations.snapshot(domain, pid, [p]); original = calculations.resolve
    def change_after_validation(*args):
        result = original(*args)
        domain.store.put('evidence', {**ev, 'review_state':'confirmed'}, ev['revision'])
        return result
    monkeypatch.setattr(calculations, 'resolve', change_after_validation)
    with pytest.raises(core.ValidationError, match='changed'):
        calculations.execute(domain, pid, p.plan_key, [p], frozen)
    assert not domain.store.list(kind, pid)


@pytest.mark.parametrize('kind', KINDS)
@pytest.mark.parametrize('change', ['project', 'evidence'])
def test_revision_during_calculation_refuses_direct_service_write(client, monkeypatch, kind, change):
    domain, pid, p = setup_plan(client, kind)
    p, ev = with_evidence(client, domain, pid, p)
    service = inspection(kind).service(domain)
    module = importlib.import_module(service.__module__)
    function = 'analyze' if kind == 'operation' else 'calculate'
    original = getattr(module, function)
    def change_during_calculation(*args):
        result = original(*args)
        if change == 'project': revise(domain, pid)
        else:
            modified = {**ev, 'review_state':'rejected'}
            domain.store.put('evidence', modified, ev['revision'])
        return result
    monkeypatch.setattr(module, function, change_during_calculation)
    with pytest.raises(core.ValidationError, match='changed'):
        service.save(pid, p.input)
    assert not domain.store.list(kind, pid)


@pytest.mark.parametrize('kind', KINDS)
@pytest.mark.parametrize('change', ['rejected', 'revision', 'calculator'])
def test_exact_stale_cause_and_no_current_values(client, monkeypatch, kind, change):
    domain, pid, p = setup_plan(client, kind)
    p, ev = with_evidence(client, domain, pid, p)
    spec = inspection(kind); service = spec.service(domain)
    record = service.save(pid, p.input)
    if change == 'calculator':
        module = importlib.import_module(service.__module__)
        monkeypatch.setattr(module, 'provenance_version', lambda path: 'changed-test-version')
    else:
        domain.store.put('evidence', {**ev, 'review_state':'rejected' if change == 'rejected' else 'confirmed'}, ev['revision'])
    current = service.view(pid, record[spec.record_key])
    assert current['status'] == 'stale' and current['result'] is None
    assert [x['code'] for x in current['stale_details']] == [
        {'rejected':'evidence_rejected', 'revision':'evidence_revision', 'calculator':'calculator_version'}[change]]
    assert not model_projection(readable(current, kind), kind)['explanation_facts']
    assert domain.store.get(kind, record[spec.record_key])['result'] == record['result']


def test_file_corruption_is_a_source_failure_not_a_rule_event(client):
    domain, pid, p = setup_plan(client, 'operation'); spec = inspection('operation'); service = spec.service(domain)
    record = service.save(pid, p.input)
    _, path = domain.file_record(pid, p.input.file_id)
    path.write_text('corrupted original fixture', encoding='utf-8')
    current = service.view(pid, record['operation_id'])
    assert current['result'] is None
    assert current['stale_details'] == [{'code':'source_file_unavailable', 'subject_id':p.input.file_id,
                                        'expected':None, 'current':None}]


def test_write_transaction_blocks_separate_writer_until_calculation_insert(client, monkeypatch):
    domain, pid, p = setup_plan(client, 'thermal')
    entered, attempted, committed = threading.Event(), threading.Event(), threading.Event()
    original = domain.store.put_in
    def intercept(con, kind, record, expected=0):
        if kind == 'thermal':
            entered.set()
            assert attempted.wait(5)
            assert not committed.wait(.2), 'Concurrent source write crossed the calculation transaction'
        return original(con, kind, record, expected)
    monkeypatch.setattr(domain.store, 'put_in', intercept)
    def writer():
        assert entered.wait(5)
        attempted.set()
        revise(domain, pid)
        committed.set()
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(writer)
        record = inspection('thermal').service(domain).save(pid, p.input)
        pending.result(timeout=5)
    saved = domain.store.get('thermal', record['thermal_id'])
    assert saved['project_revision'] == 1
    current = inspection('thermal').service(domain).view(pid, record['thermal_id'])
    assert current['status'] == 'stale' and current['stale_reasons'] == ['project_revision']


def test_failed_insert_rolls_back_and_releases_write_lock(client, monkeypatch):
    domain, pid, p = setup_plan(client, 'thermal'); original = domain.store.put_in
    def fail_after_insert(con, kind, record, expected=0):
        original(con, kind, record, expected)
        raise RuntimeError('Injected insert failure')
    with monkeypatch.context() as patch:
        patch.setattr(domain.store, 'put_in', fail_after_insert)
        with pytest.raises(RuntimeError, match='Injected'):
            inspection('thermal').service(domain).save(pid, p.input)
    assert not domain.store.list('thermal', pid)
    revise(domain, pid)
    assert inspection('thermal').service(domain).save(pid, p.input)['project_revision'] == 2
