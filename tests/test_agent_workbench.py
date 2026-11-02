"""Controlled protocol tests of real tool execution and reviewable work products."""
import json

import pytest
from pydantic import ValidationError

from backend import core
from backend.agent import Chat
from backend.agent_actions import WorkPlan
from test_api import create_project


def call(name, arguments):
    return {'role':'assistant','content':None,'tool_calls':[{'id':'call_'+name,'type':'function',
             'function':{'name':name,'arguments':json.dumps(arguments)}}]}


def ready(client, monkeypatch, replies):
    agent = client.app.state.agent
    monkeypatch.setattr(agent.gateway, 'public', lambda: {'enabled':True,'key_configured':True,'provider':'controlled','model':'protocol'})
    stream = iter(replies)
    seen = []
    def complete(messages, tools, **kwargs):
        seen.append(json.loads(json.dumps(messages)))
        return next(stream)
    monkeypatch.setattr(agent.gateway, 'complete', complete)
    return agent, seen


def step(sid, tool, args=None, depends=None):
    return {'step_id':sid,'purpose':'Inspect current source for '+sid,'tool':tool,'arguments':args or {},'depends_on':depends or []}


def shortlist():
    return {'goal':'Compare glazing for west-facing office', 'requirements':['Preserve daylight and obtain actual quotations'],
            'directions':[{'research_id':sid,'reason':'Compare the documented direction within the stated scope',
                           'tradeoff':'Product-level optical testing and quotations remain missing'}
                          for sid in ['lab6-2003','lowe-control']]}


def test_model_plan_executes_sources_and_saves_review_required_product(client, monkeypatch):
    pid = create_project(client)['project_id']
    agent, _ = ready(client, monkeypatch, [
        call('engineering_work_plan', {'work_plan':{'goal':'Inspect two glazing directions','steps':[
            step('rare','material_research',{'query':'LaB6','limit':5}), step('control','material_research',{'query':'Low-E','limit':5},['rare'])]}}),
        call('material_shortlist_propose', {'shortlist':shortlist()}),
        call('request_project_input', {'questions':[{'question':'Which glazing area is documented?', 'why_needed':'Required to compare same engineering scope without inventing quantities'}]}),
        {'role':'assistant','content':'已形成两条待复核方向。缺工程量、产品检测和报价，不能认定节能或采购胜出。'}])
    result = agent.start(pid, Chat(message='请形成可复核的窗改造方向并保留采光',mode='provider'), background=False)
    assert result['status']=='partial' and result['explanation_status']=='available'
    assert [e['tool'] for e in result['events'][:2]] == ['project_get','llm.request']
    assert result['model_tool_calls']==2
    assert len(result['work_plans'])==1 and all(s['status']=='succeeded' for s in result['work_plans'][0]['steps'])
    product=result['work_products'][0]
    assert product['state']=='REVIEW_REQUIRED' and product['current']
    assert product['prices'] is None and product['energy_saving'] is None
    assert {d['role'] for d in product['directions']}=={'rare_earth_direction','conventional_direction'}
    assert result['answer']['can_recommend'] is False and result['input_questions']
    assert not client.app.state.domain.store.jobs(pid)


def test_only_prose_without_engineering_calls_is_rejected(client, monkeypatch):
    pid=create_project(client)['project_id']
    agent,_=ready(client,monkeypatch,[{'role':'assistant','content':'全部检查已完成。'}]*2)
    r=agent.start(pid,Chat(message='检查项目现状',mode='provider'),background=False)
    assert r['status']=='partial' and r['llm_commentary'] is None
    assert r['explanation_status']=='invalid' and r['model_tool_calls']==0
    assert not any(e['tool']=='evidence_validate' for e in r['events'])


def test_plan_failure_preserves_failed_step_and_skips_dependents(client, monkeypatch):
    pid=create_project(client)['project_id']
    plan={'goal':'Inspect missing source and dependent check','steps':[
        step('source','ifc_source_inventory',{'file_id':'file_'+'e'*32}),step('dependent','model_get',depends=['source'])]}
    agent,_=ready(client,monkeypatch,[call('engineering_work_plan',{'work_plan':plan}),
        call('evidence_validate',{}),{'role':'assistant','content':'原件读取失败，依赖检查未执行，已读取当前准入缺口。'}])
    r=agent.start(pid,Chat(message='核对原件和依赖检查',mode='provider'),background=False)
    assert r['status']=='partial'
    assert [s['status'] for s in r['work_plans'][0]['steps']]==['failed','skipped']
    assert not any(e['tool']=='model_get' for e in r['events'])


def test_entire_plan_validated_before_any_batch_execution(client,monkeypatch):
    pid=create_project(client)['project_id']
    plan={'goal':'Controlled forbidden batch write','steps':[step('read','weather_summary'),step('write','simulation_create')]}
    agent,_=ready(client,monkeypatch,[call('engineering_work_plan',{'work_plan':plan}),call('evidence_validate',{}),
        {'role':'assistant','content':'批量写入被拒绝，没有提交仿真；已核对当前缺口。'}])
    r=agent.start(pid,Chat(message='检查这个受控计划',mode='provider',allow_compute=True),background=False)
    assert not any(e['tool']=='weather_summary' for e in r['events'])
    assert not client.app.state.domain.store.jobs(pid)
    assert r['work_plans']==[]


def test_unknown_unread_shortlist_cannot_be_saved(client,monkeypatch):
    pid=create_project(client)['project_id']
    agent,_=ready(client,monkeypatch,[call('material_shortlist_propose',{'shortlist':shortlist()}),call('evidence_validate',{}),
        {'role':'assistant','content':'候选来源未读，提议未保存；需要先查询资料。'}])
    r=agent.start(pid,Chat(message='形成方向',mode='provider'),background=False)
    assert r['work_products']==[] and r['status']=='partial'
    assert any(e['tool']=='material_shortlist_propose' and e['status']=='failed' for e in r['events'])


def test_continuation_keeps_context_but_rechecks_current_tools(client,monkeypatch):
    pid=create_project(client)['project_id']
    agent,_=ready(client,monkeypatch,[call('evidence_validate',{}),
        call('request_project_input',{'questions':[{'question':'请补充建筑用途与已有原件范围','why_needed':'用于确定下一步应读取的资料而非推测'}]}),
        {'role':'assistant','content':'等待补充建筑用途及资料。'}])
    parent=agent.start(pid,Chat(message='请检查校舍资料',mode='provider'),background=False)
    raw=agent.store.get('agent',parent['agent_id'])
    agent.store.put('agent',{**raw,'llm_commentary':'PRIVATE OLD EXCERPT MUST NOT LEAK'},raw['revision'])
    agent,seen=ready(client,monkeypatch,[call('project_sources',{}),{'role':'assistant','content':'已重新读取当前原件目录，尚无可分析原件。'}])
    child=agent.start(pid,Chat(message='用途是教学楼，目前尚无图纸',mode='provider',parent_task_id=parent['agent_id']),background=False)
    assert child['parent_task_id']==parent['agent_id'] and child['status']=='succeeded'
    assert '请检查校舍资料' in json.dumps(seen,ensure_ascii=False)
    assert 'PRIVATE OLD EXCERPT' not in json.dumps(seen)
    other=create_project(client)['project_id']
    with pytest.raises(core.ValidationError):
        agent.start(other,Chat(message='试图跨项目接续',parent_task_id=parent['agent_id']),background=False)


def test_sources_paged_and_exclude_disk_path(client):
    pid=create_project(client)['project_id'];d=client.app.state.domain
    for n in range(7):d.add_file(pid,f'source-{n}.csv',b'type,name,geometry\n')
    a=client.app.state.agent.call(pid,'project_sources',{},False)
    b=client.app.state.agent.call(pid,'project_sources',{'offset':a['next_offset']},False)
    assert len(a['files'])==5 and len(b['files'])==2 and b['next_offset'] is None
    assert all('path' not in f and 'text_preview' not in f for f in a['files'])
    assert {f['file_id'] for f in a['files']}.isdisjoint(f['file_id'] for f in b['files'])
    counts=client.app.state.agent.call(pid,'project_diagnose',{},False)['source_counts']
    assert counts['uploaded_files']==7 and counts['registered_evidence_records']==0
    assert client.app.state.agent.call(pid,'evidence_validate',{},False)['source_counts']==counts


def test_proposal_requires_structured_next_steps_and_history_is_bounded(client,monkeypatch):
    pid=create_project(client)['project_id']
    agent,_=ready(client,monkeypatch,[call('material_research',{'query':'LaB6 Low-E'}),
        call('material_shortlist_propose',{'shortlist':shortlist()}),
        {'role':'assistant','content':'已保存方向，是否需要我整理补证问题？'},
        call('request_project_input',{'questions':[{'question':'请提供拟改造窗的实测面积及测量来源','why_needed':'用于相同工程量下比较材料成本，不能编造数量'}]}),
        {'role':'assistant','content':'已保存待复核方向与实测面积问题；尚不能用于采购。'}])
    r=agent.start(pid,Chat(message='保存材料方向及继续比较必需的问题',mode='provider'),background=False)
    assert r['completion_repairs']==1 and r['input_questions'] and r['status']=='partial'
    summary=client.get(f'/api/projects/{pid}/agent?summary=true')
    assert summary.status_code==200 and summary.json()[0]['agent_id']==r['agent_id']
    assert 'events' not in summary.json()[0] and 'work_products' not in summary.json()[0]
    detail=client.get(f'/api/projects/{pid}/agent/{r["agent_id"]}').json()
    assert detail['work_products'][0]['current'] and detail['events']


def test_invalid_dependency_and_numeric_proposal_are_rejected():
    with pytest.raises(ValidationError):
        WorkPlan.model_validate({'goal':'Invalid forward dependency','steps':[step('a','project_get',depends=['b']),step('b','project_get')]})
    from backend.agent_actions import Shortlist
    s=shortlist();s['price_cny']=20
    with pytest.raises(ValidationError):Shortlist.model_validate(s)


def test_filter_miss_actually_recovers_once_and_preserves_both_events(client,monkeypatch):
    pid=create_project(client)['project_id'];d=client.app.state.domain
    for n in range(7):d.add_file(pid,f'English-{n}.csv',b'public controlled fixture')
    agent,seen=ready(client,monkeypatch,[call('project_sources',{'query':'原件 上传 文件'}),
        {'role':'assistant','content':'首次筛选未命中，服务已实际重查首批5份，共7份，剩余分页未读。'}])
    r=agent.start(pid,Chat(message='列出当前原件',mode='provider'),background=False)
    ev=[e for e in r['events'] if e['tool']=='project_sources']
    assert len(ev)==2 and ev[0]['result']['total']==0
    assert ev[1]['origin']=='recovery' and len(ev[1]['result']['files'])==5
    assert ev[1]['result']['total']==7 and ev[1]['result']['next_offset']==5
    assert 'unfiltered_retry' in json.dumps(seen) and r['recoveries'][0]['returned']==5
    assert r['model_tool_calls']==1


@pytest.mark.parametrize('usage,threshold,reason',[(20,5,'reported'),(None,5,'missing'),(20,None,'requests')])
def test_model_budget_stops_before_next_request(client,monkeypatch,usage,threshold,reason):
    pid=create_project(client)['project_id'];reply=call('evidence_validate',{})
    reply['_request']={'usage':{} if usage is None else {'total_tokens':usage}}
    agent,seen=ready(client,monkeypatch,[reply])
    r=agent.start(pid,Chat(message='检查资料并说明缺口',mode='provider',
        max_model_requests=1 if reason=='requests' else 8,reported_token_threshold=threshold),background=False)
    assert len(seen)==1 and r['status']=='partial' and r['budget_stop']
    assert r['execution_budget']['requests_started']==1
    assert r['execution_budget']['reported_tokens']==(usage or 0)
    assert r['execution_budget']['usage_missing_requests']==int(usage is None)


@pytest.mark.parametrize('provider_fails',[False,True])
def test_cancel_during_provider_wait_does_not_execute_returned_tool(client,monkeypatch,provider_fails):
    import threading
    import time
    pid=create_project(client)['project_id'];entered=threading.Event();release=threading.Event()
    agent,_=ready(client,monkeypatch,[])
    def complete(*args,**kwargs):
        entered.set();assert release.wait(5)
        if provider_fails:raise RuntimeError('Controlled provider failure while cancellation requested')
        return call('evidence_validate',{})
    monkeypatch.setattr(agent.gateway,'complete',complete)
    r=agent.start(pid,Chat(message='读取资料状态',mode='provider'),background=True)
    try:
        assert entered.wait(5)
        assert agent.store.get('agent',r['agent_id'])['execution_budget']['requests_started']==1
        url=f'/api/projects/{pid}/agent/{r["agent_id"]}/cancel'
        csrf=client.headers.pop('X-CSRF-Token')
        assert client.post(url).status_code==403
        client.headers['X-CSRF-Token']=csrf
        with pytest.raises(KeyError):agent.store.get('agentcontrol',r['agent_id'])
        for _ in range(2):
            response=client.post(url)
            assert response.status_code==200 and response.json()['cancel_requested']
        assert client.get(f'/api/projects/{pid}/agent/{r["agent_id"]}').json()['cancel_requested']
    finally:
        release.set()
    end=time.monotonic()+5
    while time.monotonic()<end:
        task=agent.store.get('agent',r['agent_id'])
        if task['status']!='running':break
        time.sleep(.02)
    assert task['status']=='cancelled' and task['execution_budget']['requests_started']==1
    assert not any(e['tool']=='evidence_validate' for e in task['events'])
    assert not agent.store.jobs(pid)


def test_weather_write_requires_permission_even_when_called_directly(client):
    pid=create_project(client)['project_id']
    with pytest.raises(core.ValidationError):
        client.app.state.agent.call(pid,'weather_epw_analyze',{'file_id':'file_'+'a'*32},False)
    assert not client.app.state.domain.weather.list(pid)


def test_weather_operation_saves_actual_reference_analysis_without_copying_rows(client):
    from pathlib import Path
    pid=create_project(client)['project_id'];d=client.app.state.domain
    f=d.add_file(pid,'reference.epw',(Path(__file__).resolve().parents[1]/'fixtures/demo/reference_5zone/weather.epw').read_bytes())
    a=client.app.state.agent.call(pid,'weather_epw_analyze',{'file_id':f['file_id']},True)
    assert a['quality']['records']==8760 and a['annual']['temperature_c']==9.761
    assert 'rows' not in a and 'daily' not in a and a['source_hash']==f['hash']
    assert len(d.weather.list(pid))==1
    b=client.app.state.agent.call(pid,'weather_epw_analyze',{'file_id':f['file_id']},True)
    assert b['weather_id']==a['weather_id'] and len(d.weather.list(pid))==1


def test_structural_provider_error_repaired_without_executing_rejected_calls(client,monkeypatch):
    from backend.gateway import ProviderError
    pid=create_project(client)['project_id']
    agent,_=ready(client,monkeypatch,[])
    attempts=[]
    def complete(*args,**kwargs):
        attempts.append(1)
        if len(attempts)==1:
            raise ProviderError('INVALID_RESPONSE',[{'status':'failed','validation_code':'TOOL_CALL_LIMIT'}],validation_code='TOOL_CALL_LIMIT')
        if len(attempts)==2:return call('evidence_validate',{})
        return {'role':'assistant','content':'修正协议后已实际检查准入，缺失资料仍需补齐。'}
    monkeypatch.setattr(agent.gateway,'complete',complete)
    r=agent.start(pid,Chat(message='检查现有资料',mode='provider'),background=False)
    assert r['status']=='succeeded' and r['explanation_status']=='available'
    assert r['protocol_recoveries'][0]['validation_code']=='TOOL_CALL_LIMIT'
    assert len([e for e in r['events'] if e['tool']=='evidence_validate'])==1
    assert any(e['status']=='failed' for e in r['events'] if e['tool']=='llm.request')
