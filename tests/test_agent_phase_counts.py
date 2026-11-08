"""Real source/withdrawal checks; scripted planning does not prove model ability."""
import copy

import pytest

from backend.agent import Chat
from backend.agent_semantics import can_deliver_requested_facts, inspection
from test_api import create_project
from test_agent_engineering import holdout_plan
from test_agent_read_execution import execute, scope
from test_agent_contract import scripted
from test_agent_capabilities import tool
from test_agent_professional import create_record, thermal_input


def source(client, pid):
    p = holdout_plan(client, pid, 'operation')
    p['input']['rules'].append({**p['input']['rules'][0], 'rule_id': 'overlap'})
    plan = Chat(message='fixture', mode='provider', allow_compute=True,
                calculation_plans=[p]).calculation_plans[0]
    return inspection('operation').service(client.app.state.agent.domain).save(pid, plan.input)


def test_partial_quality_counts_are_delivered_without_health_or_whole_record_claim(client, monkeypatch):
    pid = create_project(client)['project_id']; r = source(client, pid)
    expected = {'sample_count':'8', 'cell_issue_count':'1', 'gap_count':'1',
                'rule_event_sum':'4', 'rule_unknown_sample_sum':'2'}
    task = execute(client, monkeypatch, pid, [scope('operation', r)], {'operation': list(expected)})
    answer = task['answer']; artifact = answer['artifacts'][0]
    assert {f['fact']:f['value'] for f in answer['checked_statements'][0]['facts']} == expected
    assert answer['output_contract_coverage'] == 'fulfilled'
    assert answer['read_request_progress'][0]['state'] == 'result_verified'
    assert not artifact['verified'] and artifact['status'] == r['status'] == 'events_detected'
    assert artifact['result']['diagnosis'] == 'NOT_CONFIRMED'
    assert artifact['result']['control_action'] == 'NONE'
    assert answer['task_completion'] == 'partial' and not answer['can_recommend']
    assert '非故障数' in next(f['label'] for f in answer['checked_statements'][0]['facts'] if f['fact']=='rule_event_sum')


@pytest.mark.parametrize('when', ['before', 'after'])
def test_changed_operation_csv_withdraws_counts_without_rewriting_history(client, monkeypatch, when):
    pid = create_project(client)['project_id']; r = source(client, pid); a = client.app.state.agent
    def change():
        _, path = a.domain.file_record(pid, r['input']['file_id'])
        path.write_text(path.read_text(encoding='utf-8')+'2026-03-03T00:11:00Z,68\n', encoding='utf-8')
    if when == 'before':change()
    t = execute(client, monkeypatch, pid, [scope('operation', r)], {'operation':['sample_count','gap_count']})
    saved = copy.deepcopy(a.store.get('agent', t['agent_id']))
    if when == 'after':
        assert t['answer']['checked_statements']
        change()
    current = a.view(pid, t['agent_id'])
    assert not current['answer'].get('checked_statements')
    assert current['answer']['output_contract_coverage'] != 'fulfilled'
    assert not current['answer']['can_recommend']
    assert a.store.get('agent', t['agent_id']) == saved


def test_count_exception_cannot_unlock_thermal_or_invented_operation_fields(client):
    pid = create_project(client)['project_id']; r = source(client, pid)
    assert not can_deliver_requested_facts(r, 'operation', [])
    assert not can_deliver_requested_facts(r, 'operation', ['fault_count'])
    assert not can_deliver_requested_facts({**r, 'status':'stale', 'result':None}, 'operation', ['sample_count'])
    body = thermal_input(); body['rsi_m2k_w'] = None
    wall = create_record(client, pid, 'thermal', body)
    assert not can_deliver_requested_facts(wall, 'thermal', ['layer_resistance_m2k_w'])


def test_planning_retry_keeps_phase_boundary_and_validates_before_read(client, monkeypatch):
    pid = create_project(client)['project_id']; wall = create_record(client, pid, 'thermal')
    a = client.app.state.agent; question = '只列传热系数，不要解释。'
    item = dict(request_key='thermal', question_fragment_ids=['q1'], fact_keys=['u_w_m2k'], explanation_topics=[])
    calls = scripted(a, monkeypatch, [
        tool('requested_output_plan', {'output_plan':[{**item,'fact_keys':['invented_safety']}]}),
        tool('requested_output_plan', {'output_plan':[item]})])
    task = a.start(pid, Chat(message=question, mode='provider', read_requests=[scope('thermal', wall)]), background=False)
    assert task['status'] == 'succeeded' and len(calls) == 2
    for history in calls:
        assert '当前仅提取' in history[0]['content']
        assert '来源、缺口、准入必须回答' not in history[0]['content']
        assert any(m['role']=='user' and m['content']==question for m in history)
    failed = next(i for i,e in enumerate(task['events']) if e['tool']=='requested_output_plan' and e['status']=='failed')
    first_read = next(i for i,e in enumerate(task['events']) if e['tool']=='thermal_read')
    assert failed < first_read and task['answer']['output_plan']['intent_verified'] is False
    assert task['answer']['requested_outputs'][0]['explanations'] == []
