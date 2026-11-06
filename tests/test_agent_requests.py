"""User-bound scope and real service receipts; scripted choices are not model intelligence."""
import json

import pytest

from backend.agent import Chat
from test_api import create_project
from test_agent_contract import scripted
from test_agent_capabilities import tool
from test_agent_professional import create_record
from test_agent_batch_tools import claim
from test_agent_calculations import batch


def req(kind='thermal',purpose='availability',record_id=None,key='scope'):
    return {'request_key':key,'kind':kind,'purpose':purpose,'record_id':record_id}


def chat(requests,**kw):
    return Chat(message='Inspect only my declared read scopes; do not calculate.',mode='provider',read_requests=requests,**kw)


def test_availability_present_and_missing_are_independent_without_numeric_delivery(client,monkeypatch):
    pid=create_project(client)['project_id'];a=client.app.state.agent;r=create_record(client,pid,'thermal')
    scopes=[req(record_id=r['thermal_id'],key='present'),req('operation',key='absent')]
    history=scripted(a,monkeypatch,[tool('requested_availability',{'request_keys':['present','absent'],'finish':True})])
    t=a.start(pid,chat(scopes),background=False)
    assert t['status']=='succeeded',t.get('error')
    assert [r['state'] for r in t['answer']['checked_availability']]==['records_present','no_record_available']
    assert [r['state'] for r in t['read_request_progress']]==['availability_verified']*2
    assert t['answer']['read_request_coverage']=='all_declared_scopes_checked'
    assert t['answer']['task_completion']=='partial' and not t['answer'].get('checked_statements')
    assert len(history)==1 and len(t['events'])==4
    assert not any(e['tool'].endswith('_read') or e['tool']=='calculation_execute' for e in t['events'])


def test_unrequested_same_project_result_is_refused_even_if_in_question_and_history(client,monkeypatch):
    pid=create_project(client)['project_id'];a=client.app.state.agent
    chosen=create_record(client,pid,'thermal');other=create_record(client,pid,'thermal')
    scripted(a,monkeypatch,[tool('thermal_read',{'thermal_id':other['thermal_id']})])
    body=chat([req(purpose='results',record_id=chosen['thermal_id'])])
    body.message='Do NOT read '+other['thermal_id']
    t=a.start(pid,body,background=False)
    assert t['status']=='failed' and 'outside this task' in t['error']
    assert not t['professional_deliveries'] and t['read_request_progress'][0]['state']=='unfulfilled'
    assert not any(e['tool']=='thermal_read' and e['status']=='succeeded' for e in t['events'])


def test_availability_scope_cannot_unlock_read_or_write(client,monkeypatch):
    pid=create_project(client)['project_id'];a=client.app.state.agent;r=create_record(client,pid,'thermal')
    for name,args in [('thermal_read',{'thermal_id':r['thermal_id']}),('simulation_create',{}),('professional_inventory',{'kinds':['engineering']})]:
        scripted(a,monkeypatch,[tool(name,args)])
        t=a.start(pid,chat([req(record_id=r['thermal_id'])]),background=False)
        assert t['status']=='failed' and t['recovery_attempts']==0
        assert not t['professional_deliveries'] and not a.store.jobs(pid)


def test_one_request_cannot_finish_other_declared_scope(client,monkeypatch):
    pid=create_project(client)['project_id'];a=client.app.state.agent
    scripted(a,monkeypatch,[tool('requested_availability',{'request_keys':['first'],'finish':True}),
        tool('requested_availability',{'request_keys':['second'],'finish':True})])
    t=a.start(pid,chat([req(key='first'),req('cost',key='second')]),background=False)
    assert t['status']=='succeeded',t.get('error')
    assert t['early_finish_with_declared_reads']==['second']
    assert t['answer']['read_request_coverage']=='all_declared_scopes_checked'


def test_mixed_result_and_available_record_require_distinct_delivery(client,monkeypatch):
    pid=create_project(client)['project_id'];a=client.app.state.agent;r=create_record(client,pid,'thermal')
    scripted(a,monkeypatch,[tool('requested_availability',{'request_keys':['exists'],'finish':True}),
        tool('thermal_read',{'thermal_id':r['thermal_id']}),claim(r)])
    t=a.start(pid,chat([req(record_id=r['thermal_id'],key='exists'),req(purpose='results',record_id=r['thermal_id'],key='value')]),background=False)
    assert t['status']=='succeeded',t.get('error')
    assert t['early_finish_with_declared_reads']==['value']
    assert [r['state'] for r in t['read_request_progress']]==['availability_verified','result_verified']
    assert t['answer']['checked_statements'][0]['facts'][0]['value']=='1.97'


def test_requested_result_missing_is_not_replaced_by_other_record_or_whole_kind(client,monkeypatch):
    pid=create_project(client)['project_id'];a=client.app.state.agent;create_record(client,pid,'thermal')
    ident='thermal_'+'d'*32
    scripted(a,monkeypatch,[tool('thermal_read',{'thermal_id':ident}),
        tool('professional_missing',{'missing':{'kinds':['thermal'],'record_id':ident,'finish':True}})])
    t=a.start(pid,chat([req(purpose='results',record_id=ident)]),background=False)
    assert t['status']=='succeeded',t.get('error')
    assert t['read_request_progress'][0]['state']=='record_unavailable'
    assert t['answer']['checked_missing'][0]['project_record_count']==1
    assert not t['answer'].get('checked_statements') and t['answer']['task_completion']=='incomplete'


def test_ignored_scope_remains_visible_after_five_responses(client,monkeypatch):
    pid=create_project(client)['project_id'];a=client.app.state.agent
    history=scripted(a,monkeypatch,[tool('requested_availability',{'request_keys':['first'],'finish':True}),
        *[{'role':'assistant','content':'Everything done.'}]*4])
    t=a.start(pid,chat([req(key='first'),req('operation',key='second')]),background=False)
    assert t['status']=='succeeded' and len(history)==5 and len(t['events'])<=15
    assert t['answer']['read_request_coverage']=='incomplete'
    assert [r['state'] for r in t['read_request_progress']]==['availability_verified','unfulfilled']
    assert not t.get('model_finished_delivery')


def test_current_history_invalidates_catalog_receipt_without_rewriting_original(client,monkeypatch):
    pid=create_project(client)['project_id'];a=client.app.state.agent
    scripted(a,monkeypatch,[tool('requested_availability',{'request_keys':['scope'],'finish':True})])
    t=a.start(pid,chat([req()]),background=False);before=a.store.get('agent',t['agent_id'])
    create_record(client,pid,'thermal')
    current=a.view(pid,t['agent_id'])
    assert not current['answer']['checked_availability']
    assert current['read_request_progress'][0]['state']=='delivery_not_currently_verified'
    assert current['answer']['read_request_coverage']=='incomplete'
    assert a.store.get('agent',t['agent_id'])==before


@pytest.mark.parametrize('overrides',[{'mode':'local'},{'allow_compute':True},{'objective':'inspect_thermal'},
    {'read_requests':[req(purpose='results')]},{'read_requests':[req(),req()]},
    {'read_requests':[req(record_id='cost_'+'a'*32)]}])
def test_invalid_scope_contract_rejected_before_execution(overrides):
    body={'message':'Read scopes','mode':'provider','read_requests':[req()]};body.update(overrides)
    with pytest.raises(ValueError):Chat.model_validate(body)


def test_model_schema_exposes_only_declared_availability_keys(client,monkeypatch):
    pid=create_project(client)['project_id'];a=client.app.state.agent;definitions=[]
    monkeypatch.setattr(a.gateway,'public',lambda:{'enabled':True,'key_configured':True})
    def complete(messages,tools):
        definitions.extend(tools)
        return tool('requested_availability',{'request_keys':['chosen'],'finish':True})
    monkeypatch.setattr(a.gateway,'complete',complete)
    t=a.start(pid,chat([req(key='chosen')]),background=False)
    assert t['status']=='succeeded'
    assert {d['function']['name'] for d in definitions}=={'project_get','requested_availability'}
    schema=next(d['function']['parameters'] for d in definitions if d['function']['name']=='requested_availability')
    assert schema['properties']['request_keys']['items']['enum']==['chosen']
    assert len(json.dumps(definitions,ensure_ascii=False))<20000


def test_six_availability_scopes_fit_original_budget_and_one_final_snapshot(client,monkeypatch):
    pid=create_project(client)['project_id'];a=client.app.state.agent
    kinds=['thermal','lifecycle','cost','engineering','schedule','operation']
    scripted(a,monkeypatch,[tool('requested_availability',{'request_keys':kinds,'finish':True})])
    t=a.start(pid,chat([req(k,key=k) for k in kinds]),background=False)
    assert t['status']=='succeeded' and len(t['events'])==4
    assert len(t['answer']['checked_availability'])==6
    assert t['events'][-1]['tool']=='requested_availability_recheck'
    assert t['events'][-1]['result']['snapshot_count']==1


def test_foreign_record_availability_does_not_reveal_other_project_existence(client,monkeypatch):
    pid=create_project(client)['project_id'];other=create_project(client)['project_id'];a=client.app.state.agent
    r=create_record(client,other,'thermal')
    scripted(a,monkeypatch,[tool('requested_availability',{'request_keys':['foreign','absent'],'finish':True})])
    t=a.start(pid,chat([req(record_id=r['thermal_id'],key='foreign'),req(record_id='thermal_'+'e'*32,key='absent')]),background=False)
    assert t['status']=='succeeded'
    rows=t['answer']['checked_availability']
    assert all(r['state']=='no_record_available' and r['project_record_count']==0 for r in rows)
    assert all(r['scope']=='requested_record_in_project' for r in rows)
    assert other not in json.dumps(t) and r['input']['name'] not in json.dumps(rows)


def test_two_result_ids_same_kind_remain_separate(client,monkeypatch):
    pid=create_project(client)['project_id'];a=client.app.state.agent
    first=create_record(client,pid,'thermal');second=create_record(client,pid,'thermal')
    deliveries=[claim(first)['tool_calls'][0],claim(second)['tool_calls'][0]]
    for i,c in enumerate(deliveries):c['id']=str(i)
    scripted(a,monkeypatch,[tool('professional_read_many',{'record_ids':[first['thermal_id'],second['thermal_id']]}),
        {'role':'assistant','tool_calls':deliveries}])
    t=a.start(pid,chat([req(purpose='results',record_id=r['thermal_id'],key='value'+str(i)) for i,r in enumerate([first,second])]),background=False)
    assert t['status']=='succeeded',t.get('error')
    assert [r['state'] for r in t['read_request_progress']]==['result_verified']*2
    assert {r['record_id'] for r in t['answer']['checked_statements']}=={first['thermal_id'],second['thermal_id']}
    assert len(t['events'])<=15


def test_stale_result_scope_can_only_deliver_current_limitation(client,monkeypatch):
    pid=create_project(client)['project_id'];a=client.app.state.agent;r=create_record(client,pid,'thermal')
    project=a.store.get('project',pid);project['building']['area_m2']+=1;a.store.put('project',project,project['revision'])
    scripted(a,monkeypatch,[tool('thermal_read',{'thermal_id':r['thermal_id']}),
        tool('professional_limit',{'limitation':{'kind':'thermal','record_id':r['thermal_id'],'record_hash':r['hash'],'status':'stale','finish':True}})])
    t=a.start(pid,chat([req(purpose='results',record_id=r['thermal_id'])]),background=False)
    assert t['status']=='succeeded',t.get('error')
    assert t['read_request_progress'][0]['state']=='limitation_verified'
    assert not t['answer']['checked_statements'] and t['answer']['checked_limitations'][0]['state']=='stale'


def test_current_catalog_change_before_final_check_invalidates_delivery(client,monkeypatch):
    pid=create_project(client)['project_id'];a=client.app.state.agent;calls=0
    monkeypatch.setattr(a.gateway,'public',lambda:{'enabled':True,'key_configured':True})
    def complete(*_):
        nonlocal calls;calls+=1
        if calls==1:return tool('requested_availability',{'request_keys':['scope'],'finish':False})
        create_record(client,pid,'thermal')
        return {'role':'assistant','content':'Done.'}
    monkeypatch.setattr(a.gateway,'complete',complete)
    t=a.start(pid,chat([req()]),background=False)
    assert t['status']=='succeeded' and not t['answer']['checked_availability']
    assert t['read_request_progress'][0]['state']=='delivery_not_currently_verified'


@pytest.mark.parametrize('name,args',[
    ('requested_availability',{'request_keys':['undeclared'],'finish':True}),
    ('requested_availability',{'request_keys':['scope','scope'],'finish':True}),
    ('requested_availability',{'request_keys':['scope'],'kind':'operation'}),
    ('requested_availability',{'request_keys':['scope'],'finish':'false'})])
def test_model_cannot_change_availability_scope_contract(client,monkeypatch,name,args):
    pid=create_project(client)['project_id'];a=client.app.state.agent
    scripted(a,monkeypatch,[tool(name,args)]*3)
    t=a.start(pid,chat([req()]),background=False)
    assert t['status']=='failed' and not t['availability_deliveries'] and len(t['events'])<=15


def test_declared_result_missing_cannot_expand_to_entire_kind(client,monkeypatch):
    pid=create_project(client)['project_id'];a=client.app.state.agent
    scripted(a,monkeypatch,[tool('professional_missing',{'missing':{'kinds':['thermal'],'finish':True}})])
    t=a.start(pid,chat([req(purpose='results',record_id='thermal_'+'f'*32)]),background=False)
    assert t['status']=='failed' and 'outside this task' in t['error'] and not t['missing_deliveries']


def test_declared_scope_overrides_history_records_and_quoted_question_targets(client,monkeypatch):
    pid=create_project(client)['project_id'];a=client.app.state.agent;old=create_record(client,pid,'thermal')
    scripted(a,monkeypatch,[tool('thermal_read',{'thermal_id':old['thermal_id']}),claim(old)])
    previous=a.start(pid,Chat(message='Read '+old['thermal_id'],mode='provider'),background=False)
    scripted(a,monkeypatch,[tool('thermal_read',{'thermal_id':old['thermal_id']})])
    t=a.start(pid,chat([req(purpose='results',record_id='thermal_'+'b'*32)],previous_agent_id=previous['agent_id']),background=False)
    assert t['status']=='failed' and 'outside this task' in t['error'] and not t['professional_deliveries']


def test_foreign_selected_result_refuses_whole_batch_before_leaf_reads(client,monkeypatch):
    pid=create_project(client)['project_id'];other=create_project(client)['project_id'];a=client.app.state.agent
    own=create_record(client,pid,'thermal');foreign=create_record(client,other,'thermal')
    scripted(a,monkeypatch,[tool('professional_read_many',{'record_ids':[own['thermal_id'],foreign['thermal_id']]})])
    t=a.start(pid,chat([req(purpose='results',record_id=r['thermal_id'],key=str(i)) for i,r in enumerate([own,foreign])]),background=False)
    assert t['status']=='failed' and 'Cross-project' in t['error']
    assert not any(e.get('parent_event') is not None for e in t['events'])


def test_repeated_availability_cannot_exceed_tool_budget(client,monkeypatch):
    pid=create_project(client)['project_id'];a=client.app.state.agent
    scripted(a,monkeypatch,[batch([('requested_availability',{'request_keys':['scope'],'finish':False})]*4)]*5)
    t=a.start(pid,chat([req()]),background=False)
    assert t['status']=='failed' and 'budget' in t['error'].lower() and len(t['events'])<=15


def test_scope_api_preserves_csrf_auth_and_project_ownership(client):
    from fastapi.testclient import TestClient
    from test_auth import register
    pid=create_project(client)['project_id'];url=f'/api/projects/{pid}/agent/chat'
    body=chat([req()]).model_dump(mode='json')
    assert client.post(url,json=body,headers={'X-CSRF-Token':'incorrect'}).status_code==403
    with TestClient(client.app) as other:
        assert other.post(url,json=body).status_code==401
        register(other,'scope_other_owner')
        assert other.post(url,json=body).status_code==404
    assert not client.app.state.domain.store.list('agent',pid)


def test_unrelated_kind_change_preserves_availability_receipt(client,monkeypatch):
    pid=create_project(client)['project_id'];a=client.app.state.agent
    scripted(a,monkeypatch,[tool('requested_availability',{'request_keys':['scope'],'finish':True})])
    t=a.start(pid,chat([req()]),background=False)
    create_record(client,pid,'lifecycle')
    current=a.view(pid,t['agent_id'])
    assert current['read_request_progress'][0]['state']=='availability_verified'
    assert current['answer']['checked_availability'][0]['state']=='no_record_available'


@pytest.mark.parametrize('failure',['exception','incomplete'])
def test_final_availability_recheck_failure_never_delivers_verified_answer(client,monkeypatch,failure):
    from backend import agent_requests,core
    pid=create_project(client)['project_id'];a=client.app.state.agent
    scripted(a,monkeypatch,[tool('requested_availability',{'request_keys':['scope'],'finish':True})])
    def fail(*args):
        if failure=='exception':raise core.ValidationError('Injected catalog read failure')
        return {'checks':[],'snapshot_count':1}
    monkeypatch.setattr(agent_requests,'recheck',fail)
    t=a.start(pid,chat([req()]),background=False)
    assert t['status']=='failed' and not t.get('answer')
    assert t['read_request_progress'][0]['state']=='delivery_not_currently_verified'
