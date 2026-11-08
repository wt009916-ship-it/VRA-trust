"""Scripted planning, real services; application execution is not model intelligence."""
import copy
import pytest

from backend.agent import Chat, WRITE_TOOLS
from backend.agent_semantics import inspection
from test_api import create_project
from test_agent_contract import scripted
from test_agent_capabilities import tool
from test_agent_professional import create_record
from test_agent_artifacts import create_cost
from test_agent_engineering import inputs


def execute(client, monkeypatch, pid, requests, requirements):
    message = 'Read the requested fields and query the declared catalogs.'
    plan = [{'request_key': r['request_key'], 'question_excerpt': message,
             'fact_keys': requirements.get(r['request_key'], []), 'explanation_topics': ['status']}
            for r in requests]
    agent = client.app.state.agent
    calls = scripted(agent, monkeypatch, [tool('requested_output_plan', {'output_plan': plan})])
    result = agent.start(pid, Chat(message=message, mode='provider', read_requests=requests), background=False)
    assert result['status'] == 'succeeded', result.get('error')
    assert len(calls) == 1
    assert len(result['events']) <= 15
    assert not any(e['tool'] in WRITE_TOOLS for e in result['events'])
    assert not result['answer']['output_plan']['intent_verified']
    assert result['answer']['task_completion'] != 'verified'
    return result


def scope(kind, record, key=None):
    return {'request_key': key or kind, 'kind': kind, 'purpose': 'results', 'record_id': record[kind+'_id']}


def availability(kind):
    return {'request_key': kind+'_catalog', 'kind': kind, 'purpose': 'availability', 'record_id': None}


def make(client, pid, kind):
    if kind in {'thermal', 'lifecycle'}:
        return create_record(client, pid, kind)
    if kind == 'cost':
        return create_cost(client, pid)
    body = inputs(client, pid, kind)
    if kind == 'operation':
        body['rules'][0]['upper'] = 50  # No synthetic threshold events for the valid-source case.
    plan = Chat(message='fixture', mode='provider', allow_compute=True,
                calculation_plans=[{'plan_key':'fixture', 'kind':kind, 'input':body}]).calculation_plans[0]
    return inspection(kind).service(client.app.state.agent.domain).save(pid, plan.input)


@pytest.mark.parametrize('kinds', [('thermal','lifecycle','cost'), ('engineering','schedule','operation')])
def test_three_records_three_catalogs_execute_in_one_model_response(client, monkeypatch, kinds):
    pid = create_project(client)['project_id']
    records = {k: make(client, pid, k) for k in kinds}
    keys = {'thermal':['total_resistance_m2k_w','layer_resistance_m2k_w','u_w_m2k'],
            'lifecycle':['boundary_total_kgco2e','kgco2e_m2_over_study_period','stage.operation'],
            'cost':['material_total'], 'engineering':['left_reaction_n','max_abs_moment_nm'],
            'schedule':['planned_duration_days'], 'operation':['sample_count','rule_event_sum']}
    requests = [scope(k, records[k]) for k in kinds] + [availability(k) for k in kinds]
    task = execute(client, monkeypatch, pid, requests, keys)
    assert task['answer']['output_contract_coverage'] == 'fulfilled'
    assert len(task['read_execution_receipt']['requests']) == 6
    assert all(e['origin'] == 'controller' for e in task['events'] if e['tool'] in
               {'professional_deliver','requested_availability'})
    assert len(task['answer']['checked_availability']) == 3
    assert all(not r['missing_fact_keys'] for r in task['answer']['requested_outputs'])
    assert len(task['events']) == 14  # project + model + plan + 3*(read/deliver/recheck) + 2 catalogs


def test_missing_record_does_not_cancel_later_result_or_catalog(client, monkeypatch):
    pid = create_project(client)['project_id']; wall = make(client, pid, 'thermal')
    missing = scope('cost', {'cost_id':'cost_'+'f'*32})
    task = execute(client, monkeypatch, pid, [missing,scope('thermal',wall),availability('schedule')],
                   {'cost':['material_total'],'thermal':['u_w_m2k']})
    outputs = {r['request_key']:r for r in task['answer']['requested_outputs']}
    assert outputs['cost']['state'] == 'source_limited'
    assert outputs['thermal']['state'] == outputs['schedule_catalog']['state'] == 'fulfilled'
    assert task['answer']['output_contract_coverage'] == 'addressed_with_source_limits'
    assert task['missing_deliveries'][0]['request']['record_id'] == missing['record_id']


def test_cross_project_refusal_is_not_absence_and_other_scope_continues(client, monkeypatch):
    pid = create_project(client)['project_id']; other = create_project(client)['project_id']
    foreign = make(client, other, 'thermal')
    task = execute(client, monkeypatch, pid, [scope('thermal',foreign),availability('schedule')],
                   {'thermal':['total_resistance_m2k_w']})
    assert task['answer']['output_contract_coverage'] == 'incomplete'
    assert not task['professional_deliveries'] and not task['missing_deliveries']
    assert task['answer']['requested_outputs'][1]['state'] == 'fulfilled'
    assert not task['answer']['checked_statements'] if 'checked_statements' in task['answer'] else True


@pytest.mark.parametrize('case', ['stale','unknown_stage','read_failure'])
def test_limits_and_errors_do_not_fabricate_requested_values(client, monkeypatch, case):
    project = create_project(client);pid = project['project_id'];a=client.app.state.agent
    kind = 'lifecycle' if case == 'unknown_stage' else 'thermal';r=make(client,pid,kind)
    fact = 'stage.construction' if case == 'unknown_stage' else 'u_w_m2k'
    if case == 'stale':
        assert client.put(f'/api/projects/{pid}/building',json={'expected_revision':project['revision'],
            'building':{**project['building'],'area_m2':1357}}).status_code == 200
    if case == 'read_failure':
        original = a.call
        def call(pid, name, args, allow, **kw):
            if name == 'thermal_read':raise OSError('synthetic disk failure')
            return original(pid,name,args,allow,**kw)
        monkeypatch.setattr(a,'call',call)
    task=execute(client,monkeypatch,pid,[scope(kind,r),availability('schedule')],{kind:[fact]})
    out=task['answer']['requested_outputs']
    assert out[0]['state'] != 'fulfilled' and out[1]['state'] == 'fulfilled'
    assert not task['answer'].get('checked_statements')
    assert not task['missing_deliveries']
    assert not task['professional_deliveries'] or task['professional_deliveries'][0]['limitation_status']=='stale'


def test_final_source_recheck_and_history_still_withdraw_values(client,monkeypatch):
    project=create_project(client);pid=project['project_id'];r=make(client,pid,'thermal')
    task=execute(client,monkeypatch,pid,[scope('thermal',r),availability('schedule')],{'thermal':['u_w_m2k']})
    a=client.app.state.agent;stored=copy.deepcopy(a.store.get('agent',task['agent_id']))
    assert client.put(f'/api/projects/{pid}/building',json={'expected_revision':project['revision'],
        'building':{**project['building'],'area_m2':1456}}).status_code == 200
    current=a.view(pid,task['agent_id'])
    assert current['answer']['output_contract_coverage']=='incomplete'
    assert not current['answer']['checked_statements']
    assert a.store.get('agent',task['agent_id'])==stored


def test_invalid_plan_never_starts_application_reads(client,monkeypatch):
    pid=create_project(client)['project_id'];r=make(client,pid,'thermal');a=client.app.state.agent
    bad=tool('requested_output_plan',{'output_plan':[{'request_key':'thermal','question_excerpt':'Read',
        'fact_keys':['invented_safety_certificate'],'explanation_topics':[]}]})
    scripted(a,monkeypatch,[bad,bad,bad])
    task=a.start(pid,Chat(message='Read',mode='provider',read_requests=[scope('thermal',r)]),background=False)
    assert task['status']=='failed'
    assert not any(e['tool']=='thermal_read' for e in task['events'])
    assert not task.get('read_execution_receipt')


@pytest.mark.parametrize('at_read', [1, 2])
def test_source_change_during_delivery_or_final_check_withholds_numbers(client,monkeypatch,at_read):
    p=create_project(client);pid=p['project_id'];r=make(client,pid,'thermal');a=client.app.state.agent
    original=a.call;count=0
    def call(project_id,name,args,allow,**kw):
        nonlocal count
        result=original(project_id,name,args,allow,**kw)
        if name=='thermal_read':
            count+=1
            if count==at_read:
                assert client.put(f'/api/projects/{pid}/building',json={'expected_revision':p['revision'],
                    'building':{**p['building'],'area_m2':1567}}).status_code==200
                if at_read==2:return original(project_id,name,args,allow,**kw)
        return result
    monkeypatch.setattr(a,'call',call)
    task=execute(client,monkeypatch,pid,[scope('thermal',r),availability('schedule')],{'thermal':['u_w_m2k']})
    assert task['answer']['output_contract_coverage']=='incomplete'
    assert not task['answer'].get('checked_statements')


def test_three_absent_records_fit_budget_and_keep_all_identifiers(client,monkeypatch):
    pid=create_project(client)['project_id'];kinds=['thermal','cost','schedule']
    requests=[scope(k,{k+'_id':k+'_'+'e'*32}) for k in kinds]+[availability(k) for k in kinds]
    task=execute(client,monkeypatch,pid,requests,{'thermal':['u_w_m2k'],'cost':['material_total'],'schedule':['planned_duration_days']})
    assert task['answer']['output_contract_coverage']=='addressed_with_source_limits'
    assert len(task['answer']['checked_missing'])==3
    assert len(task['events'])<=15


def test_model_cannot_combine_plan_and_unrequested_action(client,monkeypatch):
    pid=create_project(client)['project_id'];r=make(client,pid,'thermal');a=client.app.state.agent
    first=tool('requested_output_plan',{'output_plan':[{'request_key':'thermal','question_excerpt':'Read',
        'fact_keys':['u_w_m2k'],'explanation_topics':[]}]})
    first['tool_calls']+=tool('simulation_create',{})['tool_calls']
    scripted(a,monkeypatch,[first])
    task=a.start(pid,Chat(message='Read',mode='provider',read_requests=[scope('thermal',r)]),background=False)
    assert task['status']=='failed'
    assert not any(e['tool'] in WRITE_TOOLS or e['tool']=='thermal_read' for e in task['events'])
    assert not task.get('output_plan')
