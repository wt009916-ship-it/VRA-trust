"""Scripted protocol failures with real records; not live model acceptance."""
import copy
import json

import pytest

from backend.agent import Chat
from test_api import create_project
from test_agent_capabilities import tool
from test_agent_contract import scripted
from test_agent_professional import create_record, lifecycle_input
from test_agent_calculations import batch


def limited(client, project, *, stale=False):
    if stale:
        record = create_record(client, project['project_id'], 'thermal')
        response = client.put(f'/api/projects/{project["project_id"]}/building', json={
            'expected_revision': project['revision'], 'building': {**project['building'], 'area_m2': 217.}})
        assert response.status_code == 200
        return 'thermal', record, 'stale'
    body = lifecycle_input()
    body['activities'][0]['factor']['value'] = None
    record = create_record(client, project['project_id'], 'lifecycle', body)
    return 'lifecycle', record, 'incomplete'


def limit(kind, record, status, finish=False):
    return {'limitation': {'kind': kind, 'record_id': record[kind + '_id'],
                          'record_hash': record['hash'], 'status': status, 'finish': finish}}


@pytest.mark.parametrize('stale', [False, True])
def test_limit_can_finish_later_without_repeating_delivery_and_rechecks_source(client, monkeypatch, stale):
    project = create_project(client)
    kind, record, status = limited(client, project, stale=stale)
    agent = client.app.state.agent
    scripted(agent, monkeypatch, [tool(kind + '_read', {kind + '_id': record[kind + '_id']}),
        tool('professional_limit', limit(kind, record, status)), tool('professional_finish', {})])
    original = agent.gateway.complete
    offered = []
    def capture(messages, tools, **options):
        offered.append({t['function']['name'] for t in tools})
        return original(messages, tools, **options)
    monkeypatch.setattr(agent.gateway, 'complete', capture)
    task = agent.start(project['project_id'], Chat(mode='provider', message='Read current ' + record[kind + '_id']), background=False)
    assert task['status'] == 'succeeded', task.get('error')
    assert all('professional_finish' in names for names in offered)
    assert task['model_finished_delivery']
    assert not task['answer'].get('checked_statements')
    assert task['answer']['task_completion'] != 'verified'
    assert sum(e['tool'] == 'professional_limit' for e in task['events']) == 1
    assert [e['origin'] for e in task['events'] if e['tool'] == kind + '_read'] == ['model', 'controller']


def test_empty_finish_cannot_turn_unperformed_task_into_success(client, monkeypatch):
    project = create_project(client); agent = client.app.state.agent
    scripted(agent, monkeypatch, [tool('professional_finish', {}), tool('requested_defer', {})])
    task = agent.start(project['project_id'], Chat(mode='provider', message='Unknown requested result'), background=False)
    assert not task.get('model_finished_delivery')
    assert task['answer']['task_completion'] == 'incomplete'
    assert any(e['tool'] == 'professional_finish' and e['status'] == 'failed' for e in task['events'])


def test_delivery_then_finish_is_available_in_same_action_batch(client, monkeypatch):
    project = create_project(client); agent = client.app.state.agent
    kind, record, status = limited(client, project)
    scripted(agent, monkeypatch, [tool(kind + '_read', {kind + '_id': record[kind + '_id']}),
        batch([('professional_limit', limit(kind, record, status)), ('professional_finish', {})])])
    task = agent.start(project['project_id'], Chat(mode='provider', message='Read ' + record[kind + '_id']), background=False)
    assert task['status'] == 'succeeded', task.get('error')
    assert task['model_finished_delivery'] and not task.get('question_deferral')
    assert len([e for e in task['events'] if e['tool'] == 'llm.request']) == 2
    assert not task['answer'].get('checked_statements')


def test_no_authorized_plan_has_an_exit_without_executing_any_plan(client, monkeypatch):
    from test_agent_calculations import plan
    project = create_project(client); agent = client.app.state.agent
    proposal = {**plan(), 'execution_authorized': False}
    scripted(agent, monkeypatch, [tool('requested_defer', {'defer_reason': 'missing_calculation_plan'})])
    task = agent.start(project['project_id'], Chat(mode='provider', message='Execute the plan when authorized',
        allow_compute=True, calculation_plans=[proposal]), background=False)
    assert task['status'] == 'succeeded', task.get('error')
    assert not agent.store.list('thermal', project['project_id'])
    assert task['answer']['task_completion'] == 'incomplete'
    assert task['question_deferral']['calculation_scope']['authorized_plan_keys'] == []


def test_finish_cannot_skip_second_selected_record(client, monkeypatch):
    project = create_project(client); agent = client.app.state.agent
    kind, first, status = limited(client, project)
    _, second, _ = limited(client, project)
    ids = [r['lifecycle_id'] for r in [first, second]]
    scripted(agent, monkeypatch, [tool('professional_read_many', {'record_ids': ids}),
        batch([('professional_limit', limit(kind, first, status)), ('professional_finish', {})]),
        tool('professional_limit', limit(kind, second, status, True))])
    task = agent.start(project['project_id'], Chat(mode='provider', message='Read both ' + ' '.join(ids)), background=False)
    assert task['status'] == 'succeeded', task.get('error')
    assert task['early_finish_with_unresolved_reads'] == [ids[1]]
    assert len(task['professional_deliveries']) == 2 and not task['unresolved_selected_reads']
    assert not task['answer'].get('checked_statements')


def test_continuation_does_not_suggest_finish_with_pending_declared_scope():
    from backend.agent_task_exit import continuation
    record = {'events': [], 'read_requests': [{'request_key': 'untouched', 'kind': 'thermal',
               'purpose': 'results', 'record_id': 'thermal_' + 'a' * 32}], 'objective': 'open_ended'}
    result = continuation(record)
    assert result['pending_observed_targets']['declared_request_keys'] == ['untouched']
    assert result['next_call_if_no_additional_user_targets'] is None


@pytest.mark.parametrize('allow,reason', [(False, 'calculation_not_authorized'), (True, 'missing_calculation_plan')])
def test_new_calculation_gap_is_explicit_persistent_and_does_not_reuse_previous_permission(client, monkeypatch, allow, reason):
    project = create_project(client); agent = client.app.state.agent
    record = create_record(client, project['project_id'], 'thermal')
    previous = agent.start(project['project_id'], Chat(message='Read', objective='inspect_thermal'), background=False)
    before = copy.deepcopy(agent.store.list('thermal', project['project_id']))
    scripted(agent, monkeypatch, [tool('requested_defer', {'defer_reason': reason})])
    task = agent.start(project['project_id'], Chat(mode='provider', allow_compute=allow,
        message='Create another calculation using previous parameters', previous_agent_id=previous['agent_id']), background=False)
    assert task['status'] == 'succeeded', task.get('error')
    assert agent.store.list('thermal', project['project_id']) == before
    for result in [task, agent.view(project['project_id'], task['agent_id'])]:
        answer = result['answer']
        assert answer['task_completion'] == 'incomplete' and not answer.get('checked_statements')
        gap = answer['question_deferral']
        assert gap['reason'] == reason and gap['calculation_scope']['allow_compute'] is allow
        assert gap['calculation_scope']['authorized_plan_keys'] == []
        assert not gap['calculation_scope']['historical_authorization_inherited']
        assert '本轮' in answer['summary'] and '计算' in answer['summary']
    assert record['thermal_id'] not in json.dumps(task.get('professional_deliveries'))


def test_model_cannot_falsely_claim_missing_current_permission(client, monkeypatch):
    project = create_project(client); agent = client.app.state.agent
    scripted(agent, monkeypatch, [tool('requested_defer', {'defer_reason': 'calculation_not_authorized'}),
        tool('requested_defer', {'defer_reason': 'missing_calculation_plan'})])
    task = agent.start(project['project_id'], Chat(mode='provider', allow_compute=True,
        message='Create a new calculation'), background=False)
    assert task['status'] == 'succeeded', task.get('error')
    assert task['question_deferral']['reason'] == 'missing_calculation_plan'
    assert any(e['status'] == 'failed' and 'permits computation' in e.get('error', '') for e in task['events'])


def test_foreign_leaf_read_is_indistinguishable_from_missing_and_never_views_foreign_data(client, monkeypatch):
    project = create_project(client); other = create_project(client); agent = client.app.state.agent
    foreign = create_record(client, other['project_id'], 'thermal')
    original = agent.call; reads = []
    def capture(pid, name, args, allow, **options):
        if name == 'thermal_read':reads.append(args)
        return original(pid, name, args, allow, **options)
    monkeypatch.setattr(agent, 'call', capture)
    scripted(agent, monkeypatch, [tool('thermal_read', {'thermal_id': foreign['thermal_id']}),
        tool('professional_missing', {'missing': {'kinds': ['thermal'], 'record_id': foreign['thermal_id'], 'finish': True}})])
    task = agent.start(project['project_id'], Chat(mode='provider', message='Read ' + foreign['thermal_id']), background=False)
    assert task['status'] == 'succeeded', task.get('error')
    assert not reads and not task['answer'].get('checked_statements')
    assert other['project_id'] not in json.dumps(task)
    assert task['answer']['checked_missing'][0]['record_id'] == foreign['thermal_id']
    # Direct access remains forbidden; only the model's current-project absence path recovers.
    with pytest.raises(ValueError, match='Cross-project'):
        original(project['project_id'], 'thermal_read', {'thermal_id': foreign['thermal_id']}, False)
