"""Adversarial semantic claims, independent answers and real service paths (protocol fixtures)."""
import copy
import json

import pytest

from backend.agent import Chat
from backend.agent_semantics import Delivery, check, facts
from test_api import create_project
from test_agent_professional import create_record
from test_agent_contract import scripted, call, DONE


def delivery(record, kind='thermal', **changes):
    statement = {'fact': 'total_resistance_m2k_w', 'value': '1.97', 'unit': 'm2 K/W',
                 'period': 'steady_state', 'study_years': None, 'area_m2': None}
    statement.update(changes)
    return {'kind': kind, 'record_id': record[kind + '_id'], 'record_hash': record['hash'], 'statements': [statement]}


def tool(name, data):
    return call(name, json.dumps(data))


@pytest.mark.parametrize('change', [
    {'unit': 'W/(m K)'}, {'value': '1.97001'}, {'period': 'study_period', 'study_years': 1},
    {'area_m2': 927.2}, {'fact': 'energy_saving_rate', 'value': '99'}, {'value': None},
])
def test_wrong_units_values_periods_unknown_facts_rejected(client, change):
    pid = create_project(client)['project_id'];record = create_record(client, pid, 'thermal')
    with pytest.raises(ValueError):
        check(record, Delivery.model_validate(delivery(record, **change)))
    assert check(record, Delivery.model_validate(delivery(record)))['statements'][0]['value'] == '1.97'


def test_carbon_stage_totals_not_area_or_annual_and_exclusions_not_zero(client):
    pid = create_project(client)['project_id'];r = create_record(client, pid, 'lifecycle')
    d = delivery(r, 'lifecycle', fact='stage.operation', value='1065.6', unit='kgCO2e', period='study_period', study_years=12)
    # Independent: 240 kWh/year * .37 kg/kWh * 12 years = 1065.6 kg.
    assert check(r, Delivery.model_validate(d))['statements'][0]['value'] == '1065.6'
    for fields in ({'unit': 'kgCO2e/m2', 'area_m2': 927.2}, {'study_years': 1},
                   {'fact': 'stage.construction', 'value': '0'}, {'fact': 'issued_credits_t', 'value': '1.5976'}):
        wrong = copy.deepcopy(d);wrong['statements'][0].update(fields)
        with pytest.raises(ValueError):check(r, Delivery.model_validate(wrong))
    assert all(f['fact'] != 'stage.construction' for f in facts(r, 'lifecycle'))


def test_declared_display_precision_accepts_float_tail_only_not_arbitrary_rounding(client):
    pid = create_project(client)['project_id'];r = create_record(client, pid, 'thermal')
    r = copy.deepcopy(r);r['result']['u_w_m2k'] = 7.199999999999999
    fact = next(f for f in facts(r, 'thermal') if f['fact'] == 'u_w_m2k')
    assert fact['value'] == '7.2' and fact['source_value'] == '7.199999999999999'
    for value in ('7.2', '7.199999999999999'):
        assert check(r, Delivery.model_validate(delivery(r, fact='u_w_m2k', value=value, unit='W/(m2 K)')))['status'] == 'verified'
    with pytest.raises(ValueError):check(r, Delivery.model_validate(delivery(r, fact='u_w_m2k', value='7.20001', unit='W/(m2 K)')))
    r['result']['u_w_m2k'] = 1.234567890123e-15
    small = next(f for f in facts(r, 'thermal') if f['fact'] == 'u_w_m2k')
    assert float(small['value']) > 0 and small['value'] == '1.23456789012e-15'


def test_open_professional_route_corrects_bad_explanation_and_no_energy_gate(client, monkeypatch):
    pid = create_project(client)['project_id'];r = create_record(client, pid, 'thermal');a = client.app.state.agent
    good = delivery(r);bad = delivery(r, unit='W/(m K)')
    messages = scripted(a, monkeypatch, [tool('thermal_read', {'thermal_id':r['thermal_id']}),
        tool('professional_deliver', {'delivery':bad}), tool('professional_deliver', {'delivery':good}), DONE])
    task = a.start(pid, Chat(message='解释构造热阻', mode='provider'), background=False)
    assert task['status'] == 'succeeded' and task['answer']['task_completion'] == 'partial'
    assert task['recovery_attempts'] == 1 and task['answer']['can_simulate'] is None
    assert all(e['tool'] != 'evidence_validate' for e in task['events'])
    response = json.loads(messages[2][-1]['content'])
    assert response['corrections'][0]['expected']['unit'] == 'm2 K/W'
    assert task['answer']['checked_statements'][0]['facts'][0]['value'] == '1.97'
    assert task['llm_commentary_policy'] == 'audit_only' and 'invented' not in json.dumps(task['answer'])
    assert a.context(pid, task['agent_id'])[0]['professional_references'] == [{'kind':'thermal','record_id':r['thermal_id']}]
    assert not a.context(pid, task['agent_id'])[0]['model_commentary_unverified']


def test_open_multi_record_deliveries_and_history_revalidate_without_overwrite(client, monkeypatch):
    p = create_project(client);pid = p['project_id'];a = client.app.state.agent
    thermal = create_record(client, pid, 'thermal');carbon = create_record(client, pid, 'lifecycle')
    sequence = [tool('thermal_read', {'thermal_id':thermal['thermal_id']}),
                tool('lifecycle_read', {'lifecycle_id':carbon['lifecycle_id']})]
    # Batch two deliveries in one provider turn to leave a final prose turn within the five-turn budget.
    requests = [tool('professional_deliver', {'delivery':delivery(thermal)})['tool_calls'][0],
                tool('professional_deliver', {'delivery':delivery(carbon, 'lifecycle', fact='boundary_total_kgco2e',
                    value='1597.6', unit='kgCO2e', period='study_period', study_years=12)})['tool_calls'][0]]
    requests[1]['id'] = 'second'
    scripted(a, monkeypatch, sequence + [{'role':'assistant','tool_calls':requests}, DONE])
    t = a.start(pid, Chat(message='核查热阻与阶段碳清单', mode='provider'), background=False)
    assert t['status'] == 'succeeded', t.get('error')
    assert len(t['answer']['artifacts']) == 2 and all(c['passed'] for c in t['answer']['verification'])
    assert len(t['events']) <= 15
    snapshot = a.store.get('agent', t['agent_id'])
    assert client.put(f'/api/projects/{pid}/building',json={'expected_revision':p['revision'],
        'building':{**p['building'], 'area_m2':1000.}}).status_code == 200
    current = a.view(pid, t['agent_id'])
    assert current['answer']['task_completion'] == 'incomplete'
    assert current['answer']['artifacts'] == [] and current['answer']['checked_statements'] == []
    assert current['historical_task_completion'] == 'partial'
    assert a.store.get('agent', t['agent_id']) == snapshot


def test_delivery_cannot_skip_read_or_cross_project(client, monkeypatch):
    pid = create_project(client)['project_id'];foreign = create_project(client)['project_id']
    r = create_record(client, pid, 'thermal');f = create_record(client, foreign, 'thermal');a = client.app.state.agent
    scripted(a, monkeypatch, [tool('professional_deliver', {'delivery':delivery(r)}), DONE])
    t = a.start(pid, Chat(message='Deliver without reading', mode='provider'), background=False)
    assert t['answer']['task_completion'] == 'not_assessed' and not t['professional_deliveries']
    with pytest.raises(ValueError, match='Cross-project'):
        a.call(pid, 'professional_deliver', {'delivery':delivery(f)}, False)
    assert not a.store.jobs(pid)


def test_stale_hash_and_failed_final_read_do_not_expose_old_values(client, monkeypatch):
    pid = create_project(client)['project_id'];r = create_record(client, pid, 'thermal');a = client.app.state.agent
    bad = delivery(r);bad['record_hash'] = '0'*64
    with pytest.raises(ValueError, match='changed'):
        a.call(pid, 'professional_deliver', {'delivery':bad}, False)
    scripted(a, monkeypatch, [tool('thermal_read', {'thermal_id':r['thermal_id']}),
        tool('professional_deliver', {'delivery':delivery(r)}), DONE])
    t = a.start(pid, Chat(message='read', mode='provider'), background=False)
    original = a.store.get
    def missing(kind, key, *args):
        if kind == 'thermal' and key == r['thermal_id']:raise KeyError(key)
        return original(kind, key, *args)
    monkeypatch.setattr(a.store, 'get', missing)
    current = a.view(pid, t['agent_id'])
    assert current['answer']['task_completion'] == 'incomplete' and not current['answer']['artifacts']


@pytest.mark.parametrize('value', ['NaN', 'Infinity', '1e99999', '1'+('0'*80)])
def test_unbounded_or_nonfinite_claim_rejected(value):
    r = {'thermal_id':'thermal_'+'a'*32, 'hash':'b'*64}
    with pytest.raises(ValueError):Delivery.model_validate(delivery(r, value=value))
