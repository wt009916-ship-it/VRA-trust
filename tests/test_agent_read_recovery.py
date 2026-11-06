"""Real catalogs and controlled protocol faults; not live-model intelligence evidence."""
import json

import pytest

from backend.agent import Chat
from test_api import create_project
from test_agent_contract import scripted
from test_agent_capabilities import tool
from test_agent_professional import create_record
from test_agent_batch_tools import claim


def tool_reply(history):
    return json.loads(next(m['content'] for m in history if m['role']=='tool'))


def test_batch_missing_error_names_all_unavailable_targets_and_safe_next_calls(client,monkeypatch):
    pid=create_project(client)['project_id'];a=client.app.state.agent
    ids=['thermal_'+'4'*32,'operation_'+'5'*32]
    history=scripted(a,monkeypatch,[tool('professional_read_many',{'record_ids':ids}),
        {'role':'assistant','content':'Unable to complete.'}]*3)
    task=a.start(pid,Chat(message='Check '+', '.join(ids),mode='provider'),background=False)
    reply=tool_reply(history[1])
    assert reply['error_code']=='professional_record_unavailable'
    assert reply['unavailable_record_ids']==ids and reply['present_record_ids']==[]
    assert reply['lookup_tool']=='professional_missing'
    assert [s['arguments']['missing']['record_id'] for s in reply['suggested_calls']]==ids
    assert not any(e.get('parent_event') is not None for e in task['events'])


def test_mixed_batch_error_distinguishes_present_metadata_from_actual_result_read(client,monkeypatch):
    pid=create_project(client)['project_id'];r=create_record(client,pid,'thermal');a=client.app.state.agent
    absent='cost_'+'6'*32
    history=scripted(a,monkeypatch,[tool('professional_read_many',{'record_ids':[absent,r['thermal_id']]}),
        {'role':'assistant','content':'Cannot finish.'}]*3)
    task=a.start(pid,Chat(message='Read '+absent+' and '+r['thermal_id'],mode='provider'),background=False)
    reply=tool_reply(history[1])
    assert reply['present_record_ids']==[r['thermal_id']]
    assert reply['unavailable_record_ids']==[absent] and reply['result_reads_executed']==0
    assert not any(e['tool']=='thermal_read' for e in task['events'])
    assert 'value' not in str(reply['suggested_calls'])


def test_one_absence_delivery_does_not_erase_other_selected_missing_target(client,monkeypatch):
    pid=create_project(client)['project_id'];a=client.app.state.agent
    thermal='thermal_'+'7'*32;operation='operation_'+'8'*32
    scripted(a,monkeypatch,[tool('professional_read_many',{'record_ids':[thermal,operation]}),
        tool('professional_missing',{'missing':{'kinds':['thermal'],'record_id':thermal,'finish':True}}),
        tool('professional_missing',{'missing':{'kinds':['operation'],'record_id':operation,'finish':True}})])
    task=a.start(pid,Chat(message='Check '+thermal+' and '+operation,mode='provider'),background=False)
    assert task['status']=='succeeded',task.get('error')
    assert {r['record_id'] for r in task['answer']['checked_missing']}=={thermal,operation}
    assert task['early_finish_with_unresolved_reads']==[operation]
    assert task['unresolved_selected_reads']==[]


@pytest.mark.parametrize('foreign_first',[False,True])
def test_foreign_target_refuses_whole_batch_without_partial_metadata(client,monkeypatch,foreign_first):
    pid=create_project(client)['project_id'];other=create_project(client)['project_id'];a=client.app.state.agent
    foreign=create_record(client,other,'thermal')['thermal_id'];absent='operation_'+'9'*32
    ids=[foreign,absent] if foreign_first else [absent,foreign]
    history=scripted(a,monkeypatch,[tool('professional_read_many',{'record_ids':ids})])
    t=a.start(pid,Chat(message='Read '+', '.join(ids),mode='provider'),background=False)
    assert t['status']=='failed' and 'Cross-project' in t['error']
    assert len(history)==1 and not t['recovery_attempts']
    assert not any(e.get('recovery') or e.get('parent_event') is not None for e in t['events'])


def test_internal_read_key_error_is_not_evidence_of_absence(client,monkeypatch):
    pid=create_project(client)['project_id'];r=create_record(client,pid,'thermal');a=client.app.state.agent
    original=a.call
    def broken(pid,name,args,allow,**kw):
        if name=='thermal_read':raise KeyError('damaged internal field')
        return original(pid,name,args,allow,**kw)
    monkeypatch.setattr(a,'call',broken)
    history=scripted(a,monkeypatch,[tool('thermal_read',{'thermal_id':r['thermal_id']}),
        {'role':'assistant','content':'Unable to read current result.'}])
    t=a.start(pid,Chat(message='Read '+r['thermal_id'],mode='provider'),background=False)
    reply=tool_reply(history[1])
    assert 'error_code' not in reply and 'suggested_calls' not in reply
    assert not t['missing_deliveries'] and not any(e.get('recovery') for e in t['events'])
    assert len(a.store.list('thermal',pid))==1


def test_direct_missing_read_recovers_through_actual_missing_check(client,monkeypatch):
    pid=create_project(client)['project_id'];a=client.app.state.agent;ident='thermal_'+'a'*32
    history=scripted(a,monkeypatch,[tool('thermal_read',{'thermal_id':ident}),
        tool('professional_missing',{'missing':{'kinds':['thermal'],'record_id':ident,'finish':True}})])
    t=a.start(pid,Chat(message='Check '+ident,mode='provider'),background=False)
    assert tool_reply(history[1])['unavailable_record_ids']==[ident]
    assert t['status']=='succeeded' and t['answer']['checked_missing'][0]['record_id']==ident
    assert t['answer']['task_completion']=='incomplete' and not t['unresolved_selected_reads']


def test_unapproved_guessed_id_has_only_catalog_advice_even_in_mixed_batch(client,monkeypatch):
    pid=create_project(client)['project_id'];a=client.app.state.agent;r=create_record(client,pid,'thermal')
    guessed='operation_'+'b'*32
    history=scripted(a,monkeypatch,[tool('professional_read_many',{'record_ids':[guessed,r['thermal_id']]}),
        {'role':'assistant','content':'Unknown record.'}])
    t=a.start(pid,Chat(message='Inspect existing records',mode='provider'),background=False)
    reply=tool_reply(history[1])
    assert reply['selected_record_ids']==[] and reply['lookup_tool']=='professional_inventory'
    assert {c['tool'] for c in reply['suggested_calls']}=={'professional_read_many','professional_inventory'}
    assert not t['missing_deliveries'] and not t['unresolved_selected_reads']


def test_mixed_recovery_delivers_real_value_without_new_calculation(client,monkeypatch):
    pid=create_project(client)['project_id'];a=client.app.state.agent;r=create_record(client,pid,'thermal')
    absent='operation_'+'c'*32
    scripted(a,monkeypatch,[tool('professional_read_many',{'record_ids':[absent,r['thermal_id']]}),
        tool('professional_missing',{'missing':{'kinds':['operation'],'record_id':absent,'finish':False}}),
        tool('thermal_read',{'thermal_id':r['thermal_id']}),claim(r)])
    t=a.start(pid,Chat(message='Read '+absent+' and '+r['thermal_id'],mode='provider'),background=False)
    assert t['status']=='succeeded',t.get('error')
    assert not t['unresolved_selected_reads'] and len(t['answer']['checked_missing'])==1
    assert t['answer']['checked_statements'][0]['facts'][0]['value']=='1.97'
    assert not any(e['tool']=='calculation_execute' for e in t['events']) and len(t['events'])<=15


def test_final_and_history_keep_undelivered_selected_target(client,monkeypatch):
    pid=create_project(client)['project_id'];a=client.app.state.agent
    first='thermal_'+'d'*32;second='operation_'+'e'*32
    scripted(a,monkeypatch,[tool('professional_read_many',{'record_ids':[first,second]}),
        tool('professional_missing',{'missing':{'kinds':['thermal'],'record_id':first,'finish':True}}),
        *[{'role':'assistant','content':'All done.'}]*3])
    t=a.start(pid,Chat(message='Read '+first+' and '+second,mode='provider'),background=False)
    assert t['status']=='succeeded',t.get('error')
    assert t['answer']['task_completion']=='incomplete' and not t.get('model_finished_delivery')
    assert t['unresolved_selected_reads']==[second] and t['answer']['unresolved_selected_reads']==[second]
    original=a.store.get('agent',t['agent_id'])
    viewed=a.view(pid,t['agent_id'])
    assert viewed['answer']['unresolved_selected_reads']==[second]
    assert a.store.get('agent',t['agent_id'])==original


def test_repeated_read_errors_stop_at_original_recovery_budget(client,monkeypatch):
    pid=create_project(client)['project_id'];a=client.app.state.agent;ident='thermal_'+'f'*32
    history=scripted(a,monkeypatch,[tool('thermal_read',{'thermal_id':ident})]*5)
    t=a.start(pid,Chat(message='Read '+ident,mode='provider'),background=False)
    assert t['status']=='failed' and t['recovery_attempts']==2 and len(history)==3
    assert t['unresolved_selected_reads']==[ident] and len(t['events'])<=15
    assert not t['missing_deliveries']
