"""Replay real task-completion failures without claiming scripted model intelligence."""
import json
from backend import agent_requests
from test_agent_requests import req, chat
from test_api import create_project
from test_agent_professional import create_record
from test_agent_batch_tools import claim
from test_agent_capabilities import tool
from test_agent_contract import scripted


def test_fifth_response_receipts_are_rechecked_without_model_finish(client, monkeypatch):
    pid = create_project(client)['project_id']; agent = client.app.state.agent
    wall = create_record(client, pid, 'thermal'); ident = wall['thermal_id']
    absent = 'cost_' + 'f' * 32
    scripted(agent, monkeypatch, [
        tool('professional_read_many', {'record_ids': [ident, absent]}),
        tool('professional_missing', {'missing': {'kinds': ['cost'], 'record_id': absent, 'finish': False}}),
        tool('thermal_read', {'thermal_id': ident}),
        claim(wall),
        tool('requested_availability', {'request_keys': ['equipment'], 'finish': False}),
    ])
    task = agent.start(pid, chat([req(purpose='results', record_id=ident, key='wall'),
        req('cost', 'results', absent, 'cost'), req('operation', key='equipment')]), background=False)
    assert task['status'] == 'succeeded', task.get('error')
    assert task['answer']['read_request_coverage'] == 'all_declared_scopes_checked'
    assert task['termination']['reason'] == 'response_budget_exhausted'
    assert not task.get('model_finished_delivery')
    assert task['answer']['task_completion'] != 'verified'
    assert [r['state'] for r in task['read_request_progress']] == ['result_verified', 'record_unavailable', 'availability_verified']
    assert len(task['events']) <= 15
    assert [e['tool'] for e in task['events'][-3:]] == ['thermal_read', 'professional_missing_recheck', 'requested_availability_recheck']
    assert agent.view(pid, task['agent_id'])['answer']['termination'] == task['termination']


def test_exhausted_scope_does_not_invent_missing_delivery(client, monkeypatch):
    pid = create_project(client)['project_id']; agent = client.app.state.agent
    scripted(agent, monkeypatch, [tool('requested_availability', {'request_keys': ['known'], 'finish': False})] * 5)
    task = agent.start(pid, chat([req(key='known'), req('operation', key='not_read')]), background=False)
    assert task['status'] == 'succeeded', task.get('error')
    assert task['answer']['read_request_coverage'] == 'incomplete'
    assert task['termination']['pending_request_keys'] == ['not_read']
    assert [r['state'] for r in task['read_request_progress']] == ['availability_verified', 'unfulfilled']
    assert not task['professional_deliveries']
    assert len(task['events']) <= 15


def test_budget_end_still_refuses_failed_final_recheck(client, monkeypatch):
    pid = create_project(client)['project_id']; agent = client.app.state.agent
    scripted(agent, monkeypatch, [tool('requested_availability', {'request_keys': ['scope'], 'finish': False})] * 5)
    monkeypatch.setattr(agent_requests, 'recheck', lambda *args: {'checks': []})
    task = agent.start(pid, chat([req()]), background=False)
    assert task['status'] == 'failed' and task.get('answer') is None


def test_stale_scope_has_exact_limitation_action_without_auto_execution(client, monkeypatch):
    pid = create_project(client)['project_id']; agent = client.app.state.agent
    wall = create_record(client, pid, 'thermal'); ident = wall['thermal_id']
    project = agent.store.get('project', pid); project['building']['area_m2'] += 1
    agent.store.put('project', project, project['revision'])
    seen = []
    monkeypatch.setattr(agent.gateway, 'public', lambda: {'enabled': True, 'key_configured': True})
    def complete(messages, tools, **response_options):
        seen.append(messages)
        if len(seen) == 1: return tool('thermal_read', {'thermal_id': ident})
        if len(seen) > 2: return {'role': 'assistant', 'content': 'Done'}
        # Controller provides a next action from an actual read. The model still
        # chooses and calls it; omission must not be silently completed.
        state = json.loads(messages[0]['content'].split('当前控制流程状态：', 1)[1].split('\n总预算', 1)[0])
        action = state['declared_next_actions'][0]
        assert action['tool'] == 'professional_limit'
        assert action['arguments']['limitation'] == {
            'kind': 'thermal', 'record_id': ident, 'record_hash': wall['hash'], 'status': 'stale', 'finish': False}
        return tool(action['tool'], action['arguments']) if len(seen) == 2 else {'role': 'assistant', 'content': 'Done'}
    monkeypatch.setattr(agent.gateway, 'complete', complete)
    task = agent.start(pid, chat([req(purpose='results', record_id=ident)]), background=False)
    assert task['status'] == 'succeeded', task.get('error')
    assert task['read_request_progress'][0]['state'] == 'limitation_verified'
    assert not task['answer']['checked_statements']
    assert next(e for e in task['events'] if e['tool'] == 'professional_limit')['origin'] == 'model'


def test_wrong_prose_identifier_is_audited_then_model_can_correct(client, monkeypatch):
    pid = create_project(client)['project_id']; agent = client.app.state.agent
    wall = create_record(client, pid, 'thermal'); ident = wall['thermal_id']; wrong = ident + 'f'
    history = scripted(agent, monkeypatch, [
        tool('thermal_read', {'thermal_id': ident}),
        claim(wall, finish=False),
        {'role': 'assistant', 'content': 'Thermal resistance of ' + wrong + ' is 1.97 m2 K/W.'},
        {'role': 'assistant', 'content': 'Thermal resistance of ' + ident + ' is 1.97 m2 K/W.'},
    ])
    task = agent.start(pid, chat([req(purpose='results', record_id=ident)]), background=False)
    assert task['status'] == 'succeeded', task.get('error')
    assert len(history) == 4
    assert wrong not in task['llm_commentary']
    assert task['llm_commentary_review']['status'] == 'references_match'
    rejected = [e for e in task['events'] if (e.get('commentary_review') or {}).get('status') == 'reference_mismatch']
    assert len(rejected) == 1 and wrong in rejected[0]['model_commentary']
    assert task['answer']['task_completion'] != 'verified'


def test_wrong_prose_is_never_silently_rewritten_when_budget_ends(client, monkeypatch):
    pid = create_project(client)['project_id']; agent = client.app.state.agent
    wall = create_record(client, pid, 'thermal'); ident = wall['thermal_id']; wrong = ident + 'f'
    scripted(agent, monkeypatch, [
        tool('thermal_read', {'thermal_id': ident}), claim(wall, finish=False),
        *[{'role': 'assistant', 'content': wrong}] * 3,
    ])
    task = agent.start(pid, chat([req(purpose='results', record_id=ident)]), background=False)
    assert task['status'] == 'succeeded'
    assert task['llm_commentary'] == wrong
    assert task['llm_commentary_review']['status'] == 'reference_mismatch'
    assert task['answer']['read_request_coverage'] == 'all_declared_scopes_checked'


def test_submitted_availability_is_not_offered_again_while_result_pending(client, monkeypatch):
    pid = create_project(client)['project_id']; agent = client.app.state.agent
    wall = create_record(client, pid, 'thermal'); ident = wall['thermal_id']; rounds = []
    monkeypatch.setattr(agent.gateway, 'public', lambda: {'enabled': True, 'key_configured': True})
    responses = iter([
        tool('requested_availability', {'request_keys': ['equipment'], 'finish': False}),
        tool('thermal_read', {'thermal_id': ident}), claim(wall)])
    def complete(messages, tools, **response_options):
        rounds.append({t['function']['name'] for t in tools})
        return next(responses)
    monkeypatch.setattr(agent.gateway, 'complete', complete)
    task = agent.start(pid, chat([req(purpose='results', record_id=ident, key='wall'),
        req('operation', key='equipment')]), background=False)
    assert task['status'] == 'succeeded', task.get('error')
    assert 'requested_availability' in rounds[0]
    assert 'requested_availability' not in rounds[1]
    assert 'thermal_read' in rounds[1]
    assert task['answer']['read_request_coverage'] == 'all_declared_scopes_checked'
