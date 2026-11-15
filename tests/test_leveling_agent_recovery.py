import json

from backend.agent import Chat
from backend.agent_metric_reads import key_schema
from backend.agent_intent_catalog import MEANINGS
from test_agent_contract import scripted, call, DONE
from test_construction_leveling import saved, request


def test_pre_read_schema_describes_selected_domain_fields_before_values():
    ident = 'schedule_' + 'a' * 32
    schema = key_schema({'objective': 'open_ended', 'events': []}, ident)
    for key in ['forecast_finish_day', 'leveled_duration_days', 'leveled_lower_bound_days']:
        assert key + '=' + MEANINGS['schedule'][key] in schema['description']
    assert 'thermal_' not in schema['description']
    assert '6.5' not in schema['description']  # Static domain meanings, no answer hints or record text.


def test_empty_selected_fact_does_not_crash_catalog_and_incomplete_can_deliver_limitation(client, monkeypatch):
    pid, base, source, _ = saved(client)
    r = client.post(base + '/schedules/' + source['schedule_id'] + '/resource-levelings',
        json={**request(source), 'resource_demands_complete': False}).json()
    agent = client.app.state.agent
    messages = scripted(agent, monkeypatch, [
        call('schedule_read', json.dumps({'schedule_id': r['schedule_id'], 'fact_keys': ['forecast_finish_day']})),
        call('professional_limit', json.dumps({'limitation': {'kind': 'schedule', 'record_id': r['schedule_id'],
            'record_hash': r['hash'], 'status': 'incomplete', 'finish': True}})), DONE])
    task = agent.start(pid, Chat(message='读取' + r['schedule_id'] + '的资源受限完成日；缺证正式说明限制', mode='provider'), background=False)
    assert task['status'] == 'succeeded'
    assert len(messages) == 2
    assert task['answer']['checked_statements'] == []
    assert task['answer']['checked_limitations'][0]['state'] == 'incomplete'
    assert not any(e['tool'] == 'professional_deliver' for e in task['events'])


def test_empty_selected_fact_keeps_no_numeric_tool_and_does_not_substitute_baseline(client, monkeypatch):
    pid, base, source, _ = saved(client)
    r = client.post(base + '/schedules/' + source['schedule_id'] + '/resource-levelings', json=request(source)).json()
    agent = client.app.state.agent; tools_seen = []
    # Capture the actual next-turn catalog, not a copy of the filtering implementation.
    replies = [call('schedule_read', json.dumps({'schedule_id': r['schedule_id'], 'fact_keys': ['forecast_finish_day']})), DONE]
    monkeypatch.setattr(agent.gateway, 'public', lambda: {'enabled': True, 'key_configured': True})
    def complete(messages, tools, **kwargs):
        tools_seen.append(tools)
        return replies.pop(0) if replies else DONE
    monkeypatch.setattr(agent.gateway, 'complete', complete)
    task = agent.start(pid, Chat(message='读取' + r['schedule_id'] + '的资源受限完成日', mode='provider'), background=False)
    assert 2 <= len(tools_seen) <= 5
    assert all('professional_deliver' not in [t['function']['name'] for t in batch] for batch in tools_seen[1:])
    assert task['status'] != 'failed' or 'Cannot offer fact selection' not in (task.get('error') or '')
    assert not (task.get('answer') or {}).get('checked_statements')
