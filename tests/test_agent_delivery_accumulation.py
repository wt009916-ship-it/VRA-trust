"""Application protocol regressions, with scripted choices; not live-model scores."""
import copy

import pytest

from backend.agent import Chat
from test_api import create_project
from test_agent_capabilities import tool
from test_agent_contract import scripted


def setup_wall(client):
    project = create_project(client)
    body = {'name': 'Independent split-delivery reference', 'rsi_m2k_w': .13, 'rse_m2k_w': .04,
            'surface_basis': 'Explicit synthetic films', 'application': 'Uniform dry test assembly',
            'layers': [
                {'name': 'substrate', 'thickness': 150, 'thickness_unit': 'mm', 'conductivity': .6,
                 'conductivity_unit': 'W/(m K)', 'source': 'Synthetic independent input', 'correction_basis': 'Dry reference'},
                {'name': 'insulation', 'thickness': 9, 'thickness_unit': 'cm', 'conductivity': 45,
                 'conductivity_unit': 'mW/(m K)', 'source': 'Synthetic independent input', 'correction_basis': 'Dry reference'}]}
    response = client.post(f'/api/projects/{project["project_id"]}/thermal', json=body)
    assert response.status_code == 201
    return project, response.json()


def reference(record, fact, value, unit='m2 K/W'):
    return {'kind': 'thermal', 'record_id': record['thermal_id'], 'record_hash': record['hash'],
            'statements': [{'fact': fact, 'value': value, 'unit': unit, 'period': 'steady_state',
                            'study_years': None, 'area_m2': None}], 'finish': False}


def split_task(client, monkeypatch, *, extra_scope=False):
    project, record = setup_wall(client)
    agent = client.app.state.agent
    message = 'Give total R, layer R and U.' + (' Check schedule records.' if extra_scope else '')
    scopes = [{'request_key': 'wall', 'kind': 'thermal', 'purpose': 'results', 'record_id': record['thermal_id']}]
    plan = [{'request_key': 'wall', 'question_excerpt': 'Give total R, layer R and U.',
             'fact_keys': ['total_resistance_m2k_w', 'layer_resistance_m2k_w', 'u_w_m2k'], 'explanation_topics': []}]
    if extra_scope:
        scopes.append({'request_key': 'schedule', 'kind': 'schedule', 'purpose': 'availability', 'record_id': None})
        plan.append({'request_key': 'schedule', 'question_excerpt': 'Check schedule records.',
                     'fact_keys': [], 'explanation_topics': ['history']})
    refs = [reference(record, 'total_resistance_m2k_w', '2.42'),
            reference(record, 'layer_resistance_m2k_w', '2.25'),
            reference(record, 'u_w_m2k', '0.413223140496', 'W/(m2 K)')]
    captured = scripted(agent, monkeypatch, [tool('requested_output_plan', {'output_plan': plan}),
        tool('thermal_read', {'thermal_id': record['thermal_id']}),
        *[tool('professional_deliver', {'delivery': r}) for r in refs]])
    task = agent.start(project['project_id'], Chat(message=message, mode='provider', read_requests=scopes), background=False)
    return project, record, task, captured


def test_split_verified_facts_survive_later_delivery(client, monkeypatch):
    _, record, task, captured = split_task(client, monkeypatch)
    assert task['status'] == 'succeeded', task.get('error')
    assert len(captured) == 5  # No extra inference or increased execution budget.
    assert [e['status'] for e in task['events'] if e['tool'] == 'professional_deliver'] == ['succeeded'] * 3
    assert {s['fact'] for s in task['professional_deliveries'][0]['statements']} == {
        'total_resistance_m2k_w', 'layer_resistance_m2k_w', 'u_w_m2k'}
    assert task['answer']['output_contract_coverage'] == 'fulfilled'
    assert not task['answer']['requested_outputs'][0]['missing_fact_keys']
    assert len(task['answer']['checked_statements'][0]['facts']) == 3
    assert task['professional_deliveries'][0]['record_hash'] == record['hash']


def test_accumulation_does_not_hide_unqueried_scope_or_revive_stale_values(client, monkeypatch):
    project, _, task, captured = split_task(client, monkeypatch, extra_scope=True)
    assert task['status'] == 'succeeded', task.get('error')
    assert len(captured) == 5
    assert task['answer']['output_contract_coverage'] == 'incomplete'
    outputs = {r['request_key']: r for r in task['answer']['requested_outputs']}
    assert not outputs['wall']['missing_fact_keys']
    assert outputs['schedule']['state'] != 'fulfilled'
    assert not task.get('availability_deliveries')
    before = copy.deepcopy(client.app.state.agent.store.get('agent', task['agent_id']))
    assert client.put(f'/api/projects/{project["project_id"]}/building', json={
        'expected_revision': project['revision'], 'building': {**project['building'], 'area_m2': 1200}}).status_code == 200
    refreshed = client.app.state.agent.view(project['project_id'], task['agent_id'])
    assert not refreshed['answer']['checked_statements']
    assert client.app.state.agent.store.get('agent', task['agent_id']) == before


def test_accumulate_keeps_other_records_and_does_not_mutate_input():
    from backend.agent_semantics import accumulate
    record = {'thermal_id': 'thermal_' + 'a' * 32, 'hash': 'b' * 64}
    first = reference(record, 'total_resistance_m2k_w', '2.42')
    second = reference(record, 'u_w_m2k', '0.413223140496', 'W/(m2 K)')
    other = reference({**record, 'thermal_id': 'thermal_' + 'c' * 32}, 'total_resistance_m2k_w', '3')
    previous = [first, other]; original = copy.deepcopy(previous)
    merged = accumulate(previous, second)
    assert previous == original and len(second['statements']) == 1
    assert merged[0] == other
    assert len(merged[1]['statements']) == 2
    duplicate = accumulate(merged, second)
    assert duplicate == merged


@pytest.mark.parametrize('boundary', ['hash', 'limitation'])
def test_new_identity_or_limitation_replaces_numeric_accumulation(boundary):
    from backend.agent_semantics import accumulate
    record = {'thermal_id': 'thermal_' + 'a' * 32, 'hash': 'b' * 64}
    first = reference(record, 'total_resistance_m2k_w', '2.42')
    second = reference(record, 'u_w_m2k', '0.413223140496', 'W/(m2 K)')
    if boundary == 'hash':
        second['record_hash'] = 'c' * 64
    elif boundary == 'limitation':
        second.update(limitation_status='stale', statements=[])
    merged = accumulate([first], second)
    assert merged == [second]
    assert accumulate(merged, first) == [first]


def test_merged_payload_still_obeys_the_existing_statement_limit():
    from backend.agent_semantics import accumulate
    record = {'thermal_id': 'thermal_' + 'a' * 32, 'hash': 'b' * 64}
    first = reference(record, 'a', '1')
    first['statements'] = [{**first['statements'][0], 'fact': f'field_{i}'} for i in range(12)]
    original = copy.deepcopy(first)
    with pytest.raises(ValueError):
        accumulate([first], reference(record, 'thirteenth', '1'))
    assert first == original


def test_invalid_record_kind_is_rejected_without_overwriting_prior_facts():
    from backend.agent_semantics import accumulate
    record = {'thermal_id': 'thermal_' + 'a' * 32, 'hash': 'b' * 64}
    first = reference(record, 'total_resistance_m2k_w', '2.42')
    incoming = reference(record, 'u_w_m2k', '0.413223140496', 'W/(m2 K)')
    incoming['kind'] = 'engineering'
    original = copy.deepcopy(first)
    with pytest.raises(ValueError, match='Record kind and ID disagree'):
        accumulate([first], incoming)
    assert first == original


def test_rejected_later_fact_does_not_erase_previous_verified_fact(client, monkeypatch):
    project, record = setup_wall(client); agent = client.app.state.agent
    message = 'Give total R and U.'
    scope = {'request_key': 'wall', 'kind': 'thermal', 'purpose': 'results', 'record_id': record['thermal_id']}
    plan = {'request_key': 'wall', 'question_excerpt': message,
            'fact_keys': ['total_resistance_m2k_w', 'u_w_m2k'], 'explanation_topics': []}
    total = reference(record, 'total_resistance_m2k_w', '2.42')
    bad = reference(record, 'u_w_m2k', '999', 'W/(m2 K)')
    good = reference(record, 'u_w_m2k', '0.413223140496', 'W/(m2 K)')
    scripted(agent, monkeypatch, [tool('requested_output_plan', {'output_plan': [plan]}),
        tool('thermal_read', {'thermal_id': record['thermal_id']}),
        *[tool('professional_deliver', {'delivery': r}) for r in (total, bad, good)]])
    task = agent.start(project['project_id'], Chat(message=message, mode='provider', read_requests=[scope]), background=False)
    assert task['status'] == 'succeeded', task.get('error')
    assert [e['status'] for e in task['events'] if e['tool'] == 'professional_deliver'] == ['succeeded', 'failed', 'succeeded']
    assert task['answer']['output_contract_coverage'] == 'fulfilled'
    saved = task['professional_deliveries'][0]['statements']
    assert {s['fact']: s['value'] for s in saved} == {'total_resistance_m2k_w': '2.42', 'u_w_m2k': '0.413223140496'}
