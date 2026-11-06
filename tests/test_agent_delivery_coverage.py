"""Actual services plus deterministic protocol faults; separate from real-model evaluation."""
import json

import pytest

from backend import agent_capabilities as cap
from backend.agent import Chat
from backend.agent_semantics import Delivery, Limitation, check, facts, inspection, model_projection
from test_api import create_project
from test_agent_artifacts import create_cost
from test_agent_calculations import batch
from test_agent_calculations import chat, plan
from test_agent_capabilities import tool
from test_agent_contract import scripted
from test_agent_engineering import make_plan
from test_agent_professional import create_record
from test_agent_semantics import delivery


def explanation(ids, finish=True):
    result = cap.collect(ids)
    return {'catalog_hash':result['catalog_hash'], 'claims':[
        {key:row[key] for key in ('capability_id','assessment','reason_code')} for row in result['capabilities']], 'finish':finish}


@pytest.mark.parametrize('count', [5, 16])
def test_aggregate_capability_batches_and_account_for_every_final_read(client, monkeypatch, count):
    pid=create_project(client)['project_id'];agent=client.app.state.agent;ids=list(cap.ENTRIES)[:count]
    lookups=[('capability_lookup',{'capability_ids':ids[i:i+4]}) for i in range(0,count,4)]
    scripted(agent,monkeypatch,[batch(lookups),tool('capability_explain',{'capability_explanation':explanation(ids)})])
    task=agent.start(pid,Chat(message='Explain every requested capability',mode='provider'),background=False)
    assert task['status']=='succeeded',task.get('error')
    assert [r['capability_id'] for r in task['answer']['capability_assessments']]==ids
    controller=[e for e in task['events'] if e.get('origin')=='controller' and e['tool']=='capability_lookup']
    assert len(controller)==(count+3)//4 and all(len(e['arguments']['capability_ids'])<=4 for e in controller)
    assert len(task['events'])<=15 and task['answer']['task_completion']=='partial'
    saved=agent.store.get('agent',task['agent_id'])
    assert len(agent.view(pid,task['agent_id'])['answer']['capability_assessments'])==count
    assert agent.store.get('agent',task['agent_id'])==saved


@pytest.mark.parametrize('fault',['version','missing','extra'])
def test_aggregate_never_accepts_mixed_versions_or_partial_batches(fault):
    ids=list(cap.ENTRIES)[:5];calls=0
    def reader(selected):
        nonlocal calls;calls+=1;r=cap.catalog(selected)
        if calls==2:
            if fault=='version':r['catalog_hash']='0'*64
            if fault=='missing':r['capabilities']=[]
            if fault=='extra':r['capabilities']+=cap.catalog(['site_safety_approval'])['capabilities']
        return r
    answer=cap.attach({'verification':[],'gaps':[]},explanation(ids),reader)
    assert calls==2 and not answer['capability_assessments'] and not answer['verification'][0]['passed']


def test_final_second_batch_failure_invalidates_whole_scope_delivery(client,monkeypatch):
    pid=create_project(client)['project_id'];agent=client.app.state.agent;ids=list(cap.ENTRIES)[:5]
    scripted(agent,monkeypatch,[batch([('capability_lookup',{'capability_ids':ids[:4]}),('capability_lookup',{'capability_ids':ids[4:]})]),
        tool('capability_explain',{'capability_explanation':explanation(ids)})])
    original=agent.call;reads=0
    def call(pid,name,args,allow,**kw):
        nonlocal reads
        if name=='capability_lookup':
            reads+=1
            if reads==4:raise ValueError('Final batch unavailable')
        return original(pid,name,args,allow,**kw)
    monkeypatch.setattr(agent,'call',call)
    task=agent.start(pid,Chat(message='Explain five',mode='provider'),background=False)
    assert task['status']=='succeeded' and reads==4
    assert not task['answer']['capability_assessments'] and not task['answer']['verification'][-1]['passed']


def test_final_read_budget_reserved_before_any_over_budget_delivery(client,monkeypatch):
    pid=create_project(client)['project_id'];agent=client.app.state.agent;ids=list(cap.ENTRIES)
    scripted(agent,monkeypatch,[batch([('capability_lookup',{'capability_ids':ids[i:i+4]}) for i in range(0,16,4)]),
        batch([('project_get',{}) for _ in range(4)]),tool('capability_explain',{'capability_explanation':explanation(ids)})])
    task=agent.start(pid,Chat(message='All scopes after extra reads',mode='provider'),background=False)
    assert task['status']=='failed' and 'budget' in task['error'].lower()
    assert len(task['events'])<=15 and not task.get('capability_delivery')
    assert not any(e['tool']=='capability_explain' for e in task['events'])


def test_unread_fifth_claim_cannot_enter_aggregate(client,monkeypatch):
    pid=create_project(client)['project_id'];agent=client.app.state.agent;ids=list(cap.ENTRIES)[:5]
    scripted(agent,monkeypatch,[tool('capability_lookup',{'capability_ids':ids[:4]}),
        tool('capability_explain',{'capability_explanation':explanation(ids)}),{'role':'assistant','content':'Missing read; no further claim'}])
    task=agent.start(pid,Chat(message='Five requested scopes',mode='provider'),background=False)
    assert not task.get('capability_delivery') and not task['answer'].get('capability_assessments')
    with pytest.raises(ValueError):cap.catalog(ids)  # Per-read limit remains four.


def stored_record(client,pid,kind):
    if kind in {'thermal','lifecycle'}:return create_record(client,pid,kind)
    if kind=='cost':return create_cost(client,pid)
    plan=Chat(message='input',mode='provider',allow_compute=True,calculation_plans=[make_plan(client,pid,kind)]).calculation_plans[0]
    return inspection(kind).service(client.app.state.domain).save(pid,plan.input)


@pytest.mark.parametrize('kind',['thermal','lifecycle','cost','engineering','schedule','operation'])
def test_current_stale_limit_is_delivered_without_restoring_numbers_or_writing(client,monkeypatch,kind):
    pid=create_project(client)['project_id'];agent=client.app.state.agent;spec=inspection(kind);record=stored_record(client,pid,kind)
    original=agent.store.get(kind,record[spec.record_key]);project=agent.store.get('project',pid)
    project['building']['area_m2']+=3;agent.store.put('project',project,project['revision'])
    current=spec.service(agent.domain).view(pid,record[spec.record_key]);assert current['status']=='stale'
    limit={'kind':kind,'record_id':record[spec.record_key],'record_hash':current['hash'],'status':'stale','finish':True}
    captured=scripted(agent,monkeypatch,[tool(spec.read_tool,{spec.argument:record[spec.record_key]}),tool('professional_limit',{'limitation':limit})])
    task=agent.start(pid,Chat(message='Explain current invalidity of '+record[spec.record_key],mode='provider'),background=False)
    assert task['status']=='succeeded',task.get('error')
    answer=task['answer'];assert answer['checked_limitations'][0]['state']=='stale'
    assert answer['gaps'] and not answer['checked_statements'] and not answer['artifacts'][0]['verified']
    assert not facts(current,kind) and model_projection({**current,'explanation_instruction':'test'},kind)['limitation_delivery']['limitation_status']=='stale'
    projection=json.loads(captured[1][-1]['content']);assert projection['status']=='stale' and not projection['explanation_facts']
    assert agent.store.get(kind,record[spec.record_key])==original
    assert not any(e['tool']=='calculation_execute' for e in task['events'])
    with pytest.raises(ValueError):check(current,Delivery(kind=kind,record_id=record[spec.record_key],record_hash=current['hash'],statements=[
        {'fact':'forged_numeric','value':'1','unit':'m','period':'static_load_case','study_years':None,'area_m2':None}]))


def test_stale_claim_cannot_mask_valid_record_or_tampered_hash(client):
    pid=create_project(client)['project_id'];record=create_record(client,pid,'thermal')
    limit=Limitation(kind='thermal',record_id=record['thermal_id'],record_hash=record['hash'],status='stale')
    with pytest.raises(ValueError):check(record,limit.delivery())
    stale={**record,'status':'stale','result':None}
    wrong=limit.model_copy(update={'record_hash':'0'*64})
    with pytest.raises(ValueError):check(stale,wrong.delivery())
    assert check(stale,limit.delivery())['limitation']['state']=='stale'
    with pytest.raises(ValueError):check(stale,Delivery.model_validate(delivery(record)))


def test_limit_receipt_distinguishes_verification_from_record_status(client,monkeypatch):
    pid=create_project(client)['project_id'];agent=client.app.state.agent;p=make_plan(client,pid,'engineering');p['input']['depth']=1000
    body=Chat(message='input',mode='provider',allow_compute=True,calculation_plans=[p]).calculation_plans[0].input
    record=inspection('engineering').service(agent.domain).save(pid,body)
    original=agent.store.get('engineering',record['engineering_id'])
    limitation={'kind':'engineering','record_id':record['engineering_id'],'record_hash':record['hash'],'status':'outside_model_screen','finish':False}
    captured=scripted(agent,monkeypatch,[tool('beam_analysis_read',{'engineering_id':record['engineering_id']}),
        tool('professional_limit',{'limitation':limitation}),{'role':'assistant','content':'The current limitation remains in force.'}])
    task=agent.start(pid,Chat(message='Explain '+record['engineering_id'],mode='provider'),background=False)
    assert task['status']=='succeeded'
    receipt=json.loads(captured[2][-1]['content'])
    assert receipt['verification_status']=='verified' and receipt['record_status']=='outside_model_screen'
    assert receipt['delivery_kind']=='limitation' and 'status' not in receipt and 'accepted_facts' not in receipt
    assert agent.store.get('engineering',record['engineering_id'])==original
    assert original['result']['status']=='outside_model_screen'


def test_historical_nonstale_limit_does_not_become_valid_stale_claim(client):
    pid=create_project(client)['project_id'];agent=client.app.state.agent;record=create_record(client,pid,'thermal')
    incomplete={**record,'status':'incomplete','result':{**record['result'],'u_w_m2k':None}}
    request=Limitation(kind='thermal',record_id=record['thermal_id'],record_hash=record['hash'],status='incomplete').delivery()
    assert check(incomplete,request)['limitation']['state']=='incomplete'
    with pytest.raises(ValueError):check({**incomplete,'status':'stale','result':None},request)
    assert agent.store.get('thermal',record['thermal_id'])['result']['status']=='calculated'


@pytest.mark.parametrize('ending', ['recover', 'conditional_stop', 'exhaust'])
def test_early_finish_tracks_each_plan_without_forcing_writes_or_extending_budget(client, monkeypatch, ending):
    import copy
    pid=create_project(client)['project_id'];agent=client.app.state.agent
    plans=[plan('thermal','first'),plan('thermal','second')]
    plans[0]['input']['name']='UNTRUSTED_NAME_IGNORE_AUTHORITY'
    history=[]
    def complete(messages, tools):
        history.append(copy.deepcopy(messages));turn=len(history)
        if turn==1:
            return batch([('calculation_execute',{'plan_key':p['plan_key']}) for p in plans[:1 if ending=='conditional_stop' else 2]])
        executions=[json.loads(m['content']) for m in messages if m['role']=='tool' and 'plan_key' in json.loads(m['content'])]
        ids=[e['record_id'] for e in executions]
        if turn==2:return batch([('thermal_read',{'thermal_id':ident}) for ident in ids])
        if turn==3 or ending in {'recover','exhaust'}:
            index=1 if turn==4 and ending=='recover' else 0
            record=inspection('thermal').service(agent.domain).view(pid,ids[index])
            return tool('professional_deliver',{'delivery':{**delivery(record),'finish':True}})
        return {'role':'assistant','content':'The second plan was conditional and has not been executed.'}
    monkeypatch.setattr(agent.gateway,'public',lambda:{'enabled':True,'key_configured':True})
    monkeypatch.setattr(agent.gateway,'complete',complete)
    task=agent.start(pid,chat(plans),background=False)
    assert task['early_finish_with_pending_plans'][0]['plan_key']=='second'
    assert all('UNTRUSTED_NAME_IGNORE_AUTHORITY' not in h[0]['content'] for h in history)
    state=lambda h:json.loads(h[0]['content'].split('当前控制流程状态：')[1].split('\n')[0])
    assert state(history[0])['remaining_model_responses']==5
    assert [p['stage'] for p in state(history[0])['submitted_plans']]==['not_executed']*2
    assert state(history[1])['submitted_plans'][0]['stage']=='awaiting_read'
    assert state(history[2])['submitted_plans'][0]['stage']=='awaiting_delivery'
    assert state(history[3])['submitted_plans'][0]['stage']=='delivery_submitted'
    assert len(task['events'])<=15
    if ending=='recover':
        assert task['status']=='succeeded' and len(history)==4
        assert task['model_finished_delivery'] and len(task['professional_deliveries'])==2
        assert all(p['state']=='verified' for p in task['calculation_progress'])
    elif ending=='conditional_stop':
        assert task['status']=='succeeded' and len(history)==4
        assert not task.get('model_finished_delivery')
        assert len(agent.store.list('thermal',pid))==1
        assert task['calculation_progress'][1]['state']=='not_executed'
        assert task['answer']['task_completion']!='verified'
    else:
        assert task['status']=='failed' and len(history)==5
        assert 'iteration budget' in task['error'] and not task.get('model_finished_delivery')
        assert len(agent.store.list('thermal',pid))==2


def test_unknown_numeric_cannot_replace_formal_limit_and_history_rechecks_it(client,monkeypatch):
    from backend.agent_semantics import current_answer
    pid=create_project(client)['project_id'];agent=client.app.state.agent;p=plan()
    p['input']['layers'][0]['conductivity']=None
    body=chat([p]).calculation_plans[0].input;spec=inspection('thermal')
    r=spec.service(agent.domain).save(pid,body);original=agent.store.get('thermal',r['thermal_id'])
    assert r['result']['u_w_m2k'] is None and facts(r,'thermal')==[]
    limit={'kind':'thermal','record_id':r['thermal_id'],'record_hash':r['hash'],'status':'incomplete','finish':False}
    wrong={**delivery(r,value=None),'finish':True}
    scripted(agent,monkeypatch,[tool('thermal_read',{'thermal_id':r['thermal_id']}),
        tool('professional_limit',{'limitation':limit}),tool('professional_deliver',{'delivery':wrong}),
        tool('professional_limit',{'limitation':{**limit,'finish':True}})])
    t=agent.start(pid,Chat(message='Explain missing conductivity',mode='provider'),background=False)
    assert t['status']=='succeeded' and t['recovery_attempts']==1
    assert t['answer']['checked_limitations'][0]['state']=='incomplete' and not t['answer']['checked_statements']
    assert t['professional_deliveries'][0]['limitation_status']=='incomplete'
    old=current_answer(agent.domain,pid,[wrong])
    assert old['task_completion']=='incomplete' and not old['checked_statements'] and not old['verification'][0]['passed']
    assert agent.store.get('thermal',r['thermal_id'])==original
