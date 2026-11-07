"""Declared workflow routing regressions; scripted provider choices are not live-model evidence."""
from test_agent_requests import req, chat
from test_api import create_project
from test_agent_professional import create_record
from test_agent_batch_tools import claim
from test_agent_capabilities import tool


def test_mixed_scope_missing_schema_cannot_offer_availability_kind(client, monkeypatch):
    pid = create_project(client)['project_id']
    agent = client.app.state.agent
    result = create_record(client, pid, 'thermal')
    seen = []
    monkeypatch.setattr(agent.gateway, 'public', lambda: {'enabled': True, 'key_configured': True})
    responses = iter([
        tool('thermal_read', {'thermal_id': result['thermal_id']}),
        claim(result),
        tool('requested_availability', {'request_keys': ['equipment'], 'finish': True}),
    ])

    def complete(messages, tools):
        seen.append({t['function']['name']: t['function'] for t in tools})
        return next(responses)

    monkeypatch.setattr(agent.gateway, 'complete', complete)
    task = agent.start(pid, chat([
        req(purpose='results', record_id=result['thermal_id'], key='wall'),
        req('operation', key='equipment'),
    ]), background=False)
    assert task['status'] == 'succeeded', task.get('error')
    assert 'professional_missing' not in seen[0]  # No absence observed yet.
    assert 'professional_missing' not in seen[1]
    assert 'professional_missing' not in seen[2]
    assert task['answer']['read_request_coverage'] == 'all_declared_scopes_checked'
    assert [r['state'] for r in task['read_request_progress']] == ['result_verified', 'availability_verified']
    assert len(task['events']) <= 15
    assert not agent.store.jobs(pid)


def test_unread_second_result_still_has_missing_route(client, monkeypatch):
    pid = create_project(client)['project_id']
    agent = client.app.state.agent
    result = create_record(client, pid, 'thermal')
    absent = 'cost_' + 'f' * 32
    seen = []
    monkeypatch.setattr(agent.gateway, 'public', lambda: {'enabled': True, 'key_configured': True})
    responses = iter([
        tool('thermal_read', {'thermal_id': result['thermal_id']}),
        tool('material_cost_read', {'material_cost_id': absent}),
        claim(result),
        tool('professional_missing', {'missing': {'kinds': ['cost'], 'record_id': absent, 'finish': True}}),
    ])

    def complete(messages, tools):
        seen.append({t['function']['name']: t['function'] for t in tools})
        return next(responses)

    monkeypatch.setattr(agent.gateway, 'complete', complete)
    task = agent.start(pid, chat([
        req(purpose='results', record_id=result['thermal_id'], key='wall'),
        req('cost', purpose='results', record_id=absent, key='cost'),
    ]), background=False)
    assert task['status'] == 'succeeded', task.get('error')
    assert 'professional_missing' not in seen[1]
    missing = seen[2]['professional_missing']['parameters']['$defs']['Missing']
    assert missing['properties']['kinds']['items']['enum'] == ['cost']
    assert missing['properties']['record_id'] == {'type': 'string', 'enum': [absent]}
    assert 'record_id' in missing['required']
    assert task['answer']['read_request_coverage'] == 'all_declared_scopes_checked'
    assert [r['state'] for r in task['read_request_progress']] == ['result_verified', 'record_unavailable']
