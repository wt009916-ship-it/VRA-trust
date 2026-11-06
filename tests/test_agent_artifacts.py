"""Independent task completion/oracle tests; scripted prose is a protocol fault fixture."""
import copy
import json
from fractions import Fraction

import pytest

from backend.agent import Chat, WRITE_TOOLS
from test_api import create_project


def cost_input():
    return {'name': 'Independent area and item procurement', 'region': 'US-CO', 'currency': 'USD',
        'tax_basis': 'excluded', 'as_of': '2026-11-06', 'functional_scope': 'Synthetic procurement only',
        'exclusions': ['Transport', 'Labour', 'Tax'], 'lines': [
            {'line_id': key, 'material_id': key, 'name': key,
             'measure': {'mode': 'direct', 'unit': unit, 'quantity': quantity, 'source': 'Independent synthetic quantity'},
             'waste_ratio': waste, 'waste_basis': 'Independent synthetic allowance',
             'quote': {'quote_id': 'q-'+key, 'unit_price': price, 'per_unit': unit, 'currency': 'USD',
                       'tax_basis': 'excluded', 'region': 'US-CO', 'valid_from': '2026-01-01', 'valid_until': '2026-12-31',
                       'source': 'Synthetic price, not a market quotation', 'version': 'audit-2'}}
            for key, unit, quantity, waste, price in [('area', 'm2', 19.5, .04, 7.2), ('items', 'item', 3, .1, 2.675)]]}


def create_cost(client, pid, body=None):
    response = client.post(f'/api/projects/{pid}/material-costs', json=body or cost_input())
    assert response.status_code == 201, response.text
    return response.json()


def scripted(agent, monkeypatch, respond):
    monkeypatch.setattr(agent.gateway, 'public', lambda: {'enabled': True, 'key_configured': True})
    monkeypatch.setattr(agent.gateway, 'complete', respond)


def test_actual_cost_artifact_uses_decimal_strings_and_line_specific_methods(client):
    pid = create_project(client)['project_id']; record = create_cost(client, pid)
    agent = client.app.state.agent
    task = agent.start(pid, Chat(message='Read procurement', objective='inspect_material_cost'), background=False)
    answer = task['answer']; artifact = answer['artifact']
    assert task['status'] == 'succeeded' and answer['task_completion'] == 'verified'
    assert task['target_cost_id'] == record['cost_id'] and task['cost_selection_basis'] == 'latest_at_start'
    area = Fraction(195, 10) * Fraction(104, 100)
    assert Fraction(artifact['rows'][0]['purchase_quantity']) == area
    area_cents = area * Fraction(72, 10) * 100 + Fraction(1, 2)
    item_cents = 4 * Fraction(2675, 1000) * 100 + Fraction(1, 2)
    total_cents = area_cents.numerator // area_cents.denominator + item_cents.numerator // item_cents.denominator
    assert Fraction(artifact['material_total']) * 100 == total_cents == 15672
    assert artifact['rows'][0]['quantity_method'] == 'net_times_waste'
    assert artifact['rows'][1]['quantity_method'] == 'item_ceiling'
    assert artifact['rows'][1]['purchase_quantity'] == '4'
    assert artifact['rows'][0]['price_version'] == 'audit-2'
    assert artifact['record_hash'] == record['hash']
    assert not any(e['tool'] == 'evidence_validate' for e in task['events'])
    reads = [e for e in task['events'] if e['tool'] == 'material_cost_read']
    assert len(reads) == 2 and all(e['origin'] == 'controller' for e in reads)
    assert answer['can_simulate'] is None and 'IDF' not in answer['summary']


def test_fabricated_model_method_and_success_do_not_enter_deliverable(client, monkeypatch):
    pid = create_project(client)['project_id']; create_cost(client, pid); agent = client.app.state.agent
    captured = []
    def complete(messages, tools):
        captured.append(tools)
        return {'role': 'assistant', 'content': '采购面积向上取整为21m2，总额1美元，已经安全认证。'}
    scripted(agent, monkeypatch, complete)
    task = agent.start(pid, Chat(message='Read', mode='provider', objective='inspect_material_cost'), background=False)
    assert task['answer']['artifact']['material_total'] == '156.72'
    assert task['answer']['artifact']['rows'][0]['purchase_quantity'] == '20.280'
    assert task['llm_commentary_policy'] == 'audit_only' and '21m2' in task['llm_commentary']
    assert '21m2' not in json.dumps(task['answer'], ensure_ascii=False)
    assert {t['function']['name'] for t in captured[0]} == {'project_get', 'material_cost_list', 'material_cost_read'}


@pytest.mark.parametrize('missing', ['record', 'price', 'waste'])
def test_missing_data_is_incomplete_not_zero_or_success(client, missing):
    pid = create_project(client)['project_id']; body = cost_input()
    if missing == 'price': body['lines'][0]['quote']['unit_price'] = None
    if missing == 'waste': body['lines'][0]['waste_ratio'] = None
    if missing != 'record': create_cost(client, pid, body)
    task = client.app.state.agent.start(pid, Chat(message='Read', objective='inspect_material_cost'), background=False)
    assert task['answer']['task_completion'] == 'incomplete'
    assert not task['answer']['artifact'] or task['answer']['artifact']['material_total'] is None
    assert task['answer']['gaps'] and not any('IDF' in g['message'] for g in task['answer']['gaps'])


def test_source_change_during_model_call_is_rechecked_before_completion(client, monkeypatch):
    pid = create_project(client)['project_id']; create_cost(client, pid); agent = client.app.state.agent
    def changed(messages, tools):
        project = agent.store.get('project', pid); agent.store.put('project', project, project['revision'])
        return {'role': 'assistant', 'content': 'The old price is still valid'}
    scripted(agent, monkeypatch, changed)
    task = agent.start(pid, Chat(message='Read', mode='provider', objective='inspect_material_cost'), background=False)
    assert task['answer']['task_completion'] == 'incomplete'
    assert task['answer']['artifact']['status'] == 'stale' and task['answer']['artifact']['rows'] == []


def test_history_and_current_task_recheck_without_mutating_original_snapshot(client):
    pid = create_project(client)['project_id']; create_cost(client, pid); agent = client.app.state.agent
    task = agent.start(pid, Chat(message='Read', objective='inspect_material_cost'), background=False)
    original = copy.deepcopy(agent.store.get('agent', task['agent_id']))
    project = agent.store.get('project', pid); agent.store.put('project', project, project['revision'])
    view = client.get(f'/api/projects/{pid}/agent/{task["agent_id"]}').json()
    assert view['historical_task_completion'] == 'verified'
    assert view['answer']['task_completion'] == 'incomplete' and view['answer']['artifact']['material_total'] is None
    assert view['answer']['artifact']['rows'] == [] and view['event_snapshot_notice']
    history = client.get(f'/api/projects/{pid}/agent-tasks').json()
    assert history[0]['answer']['task_completion'] == 'incomplete'
    assert agent.store.get('agent', task['agent_id']) == original


def test_tampered_cost_never_returns_old_verified_answer(client):
    pid = create_project(client)['project_id']; cost = create_cost(client, pid); agent = client.app.state.agent
    task = agent.start(pid, Chat(message='Read', objective='inspect_material_cost'), background=False)
    with agent.store.connect() as con:
        con.execute("UPDATE records SET body=json_set(body,'$.result.material_total','0.00') WHERE kind='cost' AND id=?", (cost['cost_id'],))
    view = agent.view(pid, task['agent_id'])
    assert view['answer']['task_completion'] == 'incomplete' and view['answer']['artifact'] is None
    assert '核验' in view['answer']['gaps'][0]['message']


def test_explicit_and_continued_target_do_not_switch_to_newest_record(client):
    pid = create_project(client)['project_id']; first = create_cost(client, pid); agent = client.app.state.agent
    original = agent.start(pid, Chat(message='First', objective='inspect_material_cost', target_cost_id=first['cost_id']), background=False)
    second = create_cost(client, pid)
    continued = agent.start(pid, Chat(message='Continue', objective='inspect_material_cost', previous_agent_id=original['agent_id']), background=False)
    latest = agent.start(pid, Chat(message='Latest', objective='inspect_material_cost'), background=False)
    assert continued['target_cost_id'] == first['cost_id'] and continued['cost_selection_basis'] == 'previous_task'
    assert latest['target_cost_id'] == second['cost_id']
    assert continued['context_snapshot'][0]['model_commentary_unverified'] == ''


def test_cross_project_target_rejected_before_launch_and_get_is_private(client):
    pid = create_project(client)['project_id']; other = create_project(client)['project_id']
    cost = create_cost(client, pid); agent = client.app.state.agent
    response = client.post(f'/api/projects/{other}/agent/chat', json={'message': 'Read', 'objective': 'inspect_material_cost', 'target_cost_id': cost['cost_id']})
    assert response.status_code == 409 and agent.store.list('agent', other) == []
    task = agent.start(pid, Chat(message='Read', objective='inspect_material_cost'), background=False)
    assert client.get(f'/api/projects/{other}/agent/{task["agent_id"]}').status_code == 404


def test_cost_scope_remains_read_only_even_with_compute_checkbox(client, monkeypatch):
    pid = create_project(client)['project_id']; create_cost(client, pid); agent = client.app.state.agent
    def wrong(messages, tools):
        assert not ({t['function']['name'] for t in tools} & WRITE_TOOLS)
        return {'role': 'assistant', 'tool_calls': [{'id': 'bad', 'type': 'function', 'function': {'name': 'simulation_create', 'arguments': '{}'}}]}
    scripted(agent, monkeypatch, wrong)
    task = agent.start(pid, Chat(message='Read', mode='provider', allow_compute=True, objective='inspect_material_cost'), background=False)
    assert task['status'] == 'failed' and 'read-only' in task['error']
    assert not agent.store.jobs(pid)


@pytest.mark.parametrize('body', [
    {'objective': 'open_ended', 'target_cost_id': 'cost_'+'a'*32},
    {'objective': 'inspect_material_cost', 'target_cost_id': 'project_'+'a'*32},
    {'objective': 'inspect_material_cost', 'target_run_id': 'run_'+'a'*32}])
def test_ambiguous_target_contracts_rejected(client, body):
    pid = create_project(client)['project_id']
    assert client.post(f'/api/projects/{pid}/agent/chat', json={'message': 'Read', **body}).status_code == 422
