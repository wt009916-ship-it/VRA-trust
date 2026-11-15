import copy
import json
import time
from fractions import Fraction as F
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend import construction_leveling as solver, core
from backend.construction import ScheduleInput
from backend.construction_records import LevelingRequest, ScheduleRecords
from backend.agent_semantics import facts
from backend.agent_inspections import schedule_review
from test_api import create_project

REFERENCES = json.loads((Path(__file__).parent / 'fixtures/resource_leveling_reference.json').read_text(encoding='utf-8'))['cases']


def inputs(case):
    return {'name': 'Independent ' + case['id'], 'scope': 'Independent synthetic scheduling case, not site data',
        'calendar': 'continuous_elapsed_days', 'time_origin': 'Synthetic reference day zero',
        'resources': [{'resource_id': r, 'name': r, 'capacity': c, 'unit': 'unit', 'source': 'Independent fixed reference'} for r, c in case['capacities'].items()],
        'tasks': [{'task_id': k, 'name': k, 'duration_days': v['duration_half_days'] / 2,
            'duration_source': 'Independent frozen reference',
            'predecessors': [{'task_id': p, 'lag_days': lag / 2, 'source': 'Independent frozen precedence'} for p, lag in v['predecessors']],
            'demands': [{'resource_id': r, 'units': units} for r, units in v['demands'].items()]} for k, v in case['tasks'].items()]}


def verify_independently(body, schedule):
    # Rational interval intersections, no production conversion/order/profile helpers.
    rows = {r['task_id']: r for r in schedule['rows']}
    assert set(rows) == {t['task_id'] for t in body['tasks']}
    for t in body['tasks']:
        r = rows[t['task_id']]; start, finish = F(r['start_day']), F(r['finish_day'])
        assert start >= 0 and finish - start == F(str(t['duration_days']))
        assert all(start >= F(rows[d['task_id']]['finish_day']) + F(str(d['lag_days'])) for d in t['predecessors'])
    points = sorted({F(r[k]) for r in rows.values() for k in ['start_day', 'finish_day']})
    for left, right in zip(points, points[1:]):
        midpoint = (left + right) / 2
        for resource in body['resources']:
            use = sum((F(str(d['units'])) for t in body['tasks'] for d in t.get('demands', [])
                if d['resource_id'] == resource['resource_id'] and F(rows[t['task_id']]['start_day']) <= midpoint < F(rows[t['task_id']]['finish_day'])), F(0))
            assert use <= F(str(resource['capacity']))
    assert F(schedule['duration_days']) == max(F(r['finish_day']) for r in rows.values())


@pytest.mark.parametrize('case', REFERENCES, ids=lambda c: c['id'])
def test_frozen_independent_references_and_nonoptimal_counterexample(case):
    body = inputs(case); r = solver.calculate(ScheduleInput(**body), case['priority'], True)
    assert r['status'] == 'calculated'
    p = r['schedule']; verify_independently(body, p)
    assert F(p['duration_days']) == F(str(case['expected_finish_days']))
    assert {k['task_id']: F(k['start_day']) for k in p['rows']} == {k: F(str(v)) for k, v in case['expected_starts_days'].items()}
    if case['id'] == 'R03':
        assert p['duration_days'] == '6.5' and F(str(case['independent_discrete_optimum']['minimum_makespan_days'])) == 4
        assert r['optimality'] == 'not_proven' and not r['lower_bound']['attained']


def test_microday_fractional_capacity_half_open_and_bound_never_rounds_up():
    b = inputs(REFERENCES[0]); b['tasks'] = b['tasks'][:2]
    for t in b['tasks']: t.update(duration_days=.000001, predecessors=[], demands=[{'resource_id': 'crew', 'units': .000001}])
    b['resources'][0]['capacity'] = .000003
    r = solver.calculate(ScheduleInput(**b), ['A', 'B'], True)
    verify_independently(b, r['schedule'])
    assert r['schedule']['duration_days'] == '0.000001'
    assert r['lower_bound']['days_floor_6dp'] == '0.000001'
    b['resources'][0]['capacity'] = .000001
    r = solver.calculate(ScheduleInput(**b), ['A', 'B'], True)
    assert r['schedule']['duration_days'] == '0.000002'
    verify_independently(b, r['schedule'])


def test_resource_workload_bound_preserves_exact_fraction_and_floors_display():
    b = inputs(REFERENCES[0])
    b['resources'][0]['capacity'] = 3
    for t in b['tasks']:
        t.update(duration_days=1, predecessors=[], demands=[{'resource_id': 'crew', 'units': 2}])
    b['tasks'] = b['tasks'][:2]
    r = solver.calculate(ScheduleInput(**b), ['A', 'B'], True)
    bound = r['lower_bound']
    assert F(bound['exact_days_numerator']) / F(bound['exact_days_denominator']) == F(4, 3)
    assert bound['days_floor_6dp'] == '1.333333' and not bound['attained']
    assert F(bound['days_floor_6dp']) < F(4, 3) < F(r['schedule']['duration_days'])


@pytest.mark.parametrize('change,reason', [
    (lambda b: b['tasks'][0].update(duration_days=None), 'duration_missing:A'),
    (lambda b: b['resources'][0].update(capacity=None), 'capacity_missing:crew'),
    (lambda b: b.update(progress={'as_of_day': 0, 'source': 'Synthetic progress source', 'observations': []}), 'progress_present_requires_separate_plan_snapshot'),
    (lambda b: b['resources'][0].update(capacity=0), 'single_task_exceeds_capacity'),
])
def test_missing_capacity_duration_progress_or_impossible_demand_has_no_schedule(change, reason):
    b = inputs(REFERENCES[0]); change(b)
    r = solver.calculate(ScheduleInput(**b), ['A', 'B', 'C'], True)
    assert reason in r['reasons'] and r['schedule'] is None and r['lower_bound'] is None


def test_unconfirmed_demands_no_resources_and_budget_never_publish_partial_schedule(monkeypatch):
    b = inputs(REFERENCES[0])
    assert solver.calculate(ScheduleInput(**b), ['A', 'B', 'C'], False)['schedule'] is None
    monkeypatch.setattr(solver, 'MAX_OPERATIONS', 1)
    r = solver.calculate(ScheduleInput(**b), ['A', 'B', 'C'], True)
    assert r['reasons'] == ['execution_budget_exhausted'] and r['schedule'] is None
    b['resources'] = []
    for t in b['tasks']: t['demands'] = []
    assert 'no_declared_resources' in solver.calculate(ScheduleInput(**b), ['A', 'B', 'C'], True)['reasons']


def test_maximum_250_tasks_10_resources_capacity_and_exact_serial_span():
    b = inputs(REFERENCES[0]); b['resources'] = [dict(b['resources'][0], resource_id='r' + str(i)) for i in range(10)]
    b['tasks'] = [dict(copy.deepcopy(b['tasks'][0]), task_id=str(i), duration_days=.1, predecessors=[],
        demands=[{'resource_id': r['resource_id'], 'units': 1} for r in b['resources']]) for i in range(250)]
    r = solver.calculate(ScheduleInput(**b), [t['task_id'] for t in b['tasks']], True)
    assert r['status'] == 'calculated' and r['schedule']['duration_days'] == '25'
    verify_independently(b, r['schedule'])
    assert r['operations'] < solver.MAX_OPERATIONS


def request(source, case=REFERENCES[0]):
    return {'name': 'Separate leveled plan', 'source_hash': source['hash'], 'priority': case['priority'],
        'resource_demands_complete': True, 'demand_basis': 'Independent complete task resource declarations, including no-demand tasks'}


def saved(client, evidence=False):
    pid = create_project(client)['project_id']; base = '/api/projects/' + pid
    body = inputs(REFERENCES[0]); ev = None
    if evidence:
        ev = client.post(base + '/evidence', json={'type': 'manual_input', 'name': 'Frozen source', 'source_locator': 'All tasks',
            'authority': 'Auditor', 'permission': 'Synthetic test', 'acquisition_method': 'Independent case',
            'responsible_person': 'Auditor', 'status': 'IMPORTED'}).json()
        body['evidence_ids'] = [ev['evidence_id']]
    response = client.post(base + '/schedules', json=body); assert response.status_code == 201, response.text
    return pid, base, response.json(), ev


def test_api_source_bound_variant_report_agent_and_source_withdrawal(client):
    pid, base, source, ev = saved(client, evidence=True)
    response = client.post(base + '/schedules/' + source['schedule_id'] + '/resource-levelings', json=request(source))
    assert response.status_code == 201, response.text
    r = response.json(); assert r['schedule_id'] != source['schedule_id']
    assert r['result']['leveled']['schedule']['duration_days'] == '6'
    assert r['result']['planned']['duration_days'] == source['result']['planned']['duration_days'] == '4'
    assert schedule_review(r)['verified'] is True
    assert {f['fact']: f['value'] for f in facts(r, 'schedule')}['leveled_duration_days'] == '6'
    url = base + '/schedules/' + r['schedule_id']
    assert '资源受限方案：6 连续经过日' in client.get(url + '/report.html').text
    assert client.get(base + '/schedules/' + source['schedule_id']).json() == source
    task = client.post(base + '/agent/chat', json={'message': '读取明确指定的资源受限方案', 'mode': 'local', 'objective': 'inspect_schedule', 'target_schedule_id': r['schedule_id']})
    assert task.status_code in (200, 201, 202), task.text
    task = task.json(); task_id = task['agent_id']
    deadline = time.monotonic() + 10
    while task['status'] == 'running' and time.monotonic() < deadline:
        time.sleep(.02)
        task = client.get(base + '/agent/' + task_id).json()
    # Local deterministic inspection is complete; this is not autonomous LLM acceptance.
    assert task['answer']['artifact']['result']['leveled']['schedule']['duration_days'] == '6'
    response = client.patch(base + '/evidence/' + ev['evidence_id'], json={'expected_revision': 1,
        'review_state': 'rejected', 'responsible_person': 'Auditor', 'review_note': 'Withdraw independent schedule evidence'})
    assert response.status_code == 200
    current = client.get(url).json(); assert current['status'] == 'stale' and current['result'] is None
    assert facts(current, 'schedule') == []
    assert '资源受限方案：6' not in client.get(url + '/report.html').text
    current_task = client.get(base + '/agent/' + task_id).json()
    assert current_task['answer']['artifact']['result'] is None
    raw = client.app.state.domain.store.get('schedule', r['schedule_id'])
    assert raw['result']['leveled']['schedule']['duration_days'] == '6'


def test_hash_priority_cross_project_derived_source_and_tamper_rejections(client):
    pid, base, source, _ = saved(client); url = base + '/schedules/' + source['schedule_id'] + '/resource-levelings'
    b = request(source)
    for change in [dict(source_hash='0' * 64), dict(priority=['A']), dict(priority=['A', 'B', 'X'])]:
        assert client.post(url, json={**b, **change}).status_code == 409
    assert client.post(url, json={**b, 'priority': ['A', 'A', 'C']}).status_code == 422
    assert client.post(url, json={**b, 'resource_demands_complete': 'yes'}).status_code == 422
    other = create_project(client)['project_id']
    assert client.post('/api/projects/' + other + '/schedules/' + source['schedule_id'] + '/resource-levelings', json=b).status_code == 409
    r = client.post(url, json=b).json()
    assert client.post(base + '/schedules/' + r['schedule_id'] + '/resource-levelings', json=request(r)).status_code == 409
    store = client.app.state.domain.store; raw = store.get('schedule', r['schedule_id']); raw['result']['leveled']['schedule']['duration_days'] = '0'
    store.put('schedule', raw, expected=raw['revision'])
    assert client.get(base + '/schedules/' + r['schedule_id']).status_code == 409


def test_atomic_source_withdrawal_during_calculation_creates_no_derived_record(client, monkeypatch):
    pid, base, source, ev = saved(client, evidence=True); domain = client.app.state.domain
    before = domain.store.list('schedule', pid); original = solver.calculate
    def changed(*args):
        r = original(*args)
        response = client.patch(base + '/evidence/' + ev['evidence_id'], json={'expected_revision': 1,
            'review_state': 'rejected', 'responsible_person': 'Auditor', 'review_note': 'Concurrent source withdrawal'})
        assert response.status_code == 200
        return r
    monkeypatch.setattr(solver, 'calculate', changed)
    with pytest.raises(core.ValidationError):
        ScheduleRecords(domain).level(pid, source['schedule_id'], LevelingRequest(**request(source)))
    assert domain.store.list('schedule', pid) == before


@pytest.mark.parametrize('priority', [['A', 'A'], ['x' * 61], []])
def test_request_contract_rejects_unbounded_or_duplicate_task_names(priority):
    with pytest.raises(ValidationError): LevelingRequest(**{**request({'hash': '1' * 64}), 'priority': priority})


def test_derived_calculator_change_withdraws_results_without_rewriting_original(client, monkeypatch):
    from backend import construction_records
    pid, base, source, _ = saved(client)
    service = ScheduleRecords(client.app.state.domain)
    record = service.level(pid, source['schedule_id'], LevelingRequest(**request(source)))
    monkeypatch.setattr(construction_records, 'version', lambda: 'changed-derived-calculator')
    current = service.view(pid, record['schedule_id'])
    assert current['status'] == 'stale' and current['result'] is None
    assert 'calculator_version' in current['stale_reasons']
    assert service.view(pid, source['schedule_id']) == source
    assert service.store.get('schedule', record['schedule_id'])['result']['leveled']['schedule']['duration_days'] == '6'
