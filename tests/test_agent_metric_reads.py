"""Actual read services and protocol fixtures; not live model acceptance."""
import copy
import pytest
from jsonschema import Draft202012Validator
from backend import core,agent_metric_reads as reads
from backend.agent import Chat,ToolArgs,tool_event_cost
from test_api import create_project
from test_agent_contract import scripted
from test_agent_capabilities import tool
from test_agent_professional import create_record
from test_agent_energy import create_utility
from test_utility_comparison import templates as templates,native as native


@pytest.mark.parametrize('prefix,suffix,expected',[
 ('墙体','的热阻',True),('读取','，',True),('(',')',True),(' ','.',True),
 ('a','',False),('','a',False),('_','',False),('','0',False),
])
def test_complete_record_id_boundaries(prefix,suffix,expected):
    ident='thermal_'+'a'*32
    assert (reads.identifiers(prefix+ident+suffix)==[ident]) is expected
    assert reads.identifiers(prefix+ident+suffix,'thermal')==([ident] if expected else [])


def test_chinese_adjacent_id_offers_direct_read_without_inventory(client,monkeypatch):
    pid=create_project(client)['project_id'];a=client.app.state.agent;r=create_record(client,pid,'thermal');seen=[]
    scripted(a,monkeypatch,[tool('thermal_read',{'thermal_id':r['thermal_id']}),tool('professional_deliver',{'delivery':{'kind':'thermal','record_id':r['thermal_id'],'record_hash':r['hash'],'fact_keys':['total_resistance_m2k_w'],'finish':True}})])
    original=a.gateway.complete
    def capture(messages,tools,**options):seen.append(copy.deepcopy(tools));return original(messages,tools,**options)
    monkeypatch.setattr(a.gateway,'complete',capture)
    t=a.start(pid,Chat(message='读取墙体'+r['thermal_id']+'的总热阻',mode='provider'),background=False)
    assert t['status']=='succeeded',t.get('error')
    definition=next(t['function'] for t in seen[0] if t['function']['name']=='thermal_read')
    assert definition['parameters']['oneOf'][0]['properties']['thermal_id']['const']==r['thermal_id']
    assert not any(e['tool']=='professional_inventory' for e in t['events'])


def test_recognized_foreign_id_still_refused_without_source_data(client,monkeypatch):
    pid=create_project(client)['project_id'];other=create_project(client)['project_id'];r=create_record(client,other,'thermal');a=client.app.state.agent
    scripted(a,monkeypatch,[tool('thermal_read',{'thermal_id':r['thermal_id']})])
    t=a.start(pid,Chat(message='读取'+r['thermal_id']+'的总热阻',mode='provider'),background=False)
    assert t['status']=='failed' and 'Cross-project' in t['error'] and t['answer'] is None
    assert not any(e.get('result',{}).get('explanation_facts') for e in t['events'])


def test_known_catalog_constrains_read_schema_and_rejects_repeated_discovery(client,native,monkeypatch):
    pid,r,_=create_utility(client,native,monkeypatch);a=client.app.state.agent;ident=r['utility_id']
    empty={'events':[]};base={'function':{'parameters':{},'name':'utility_comparison_read'}}
    first=reads.leaf_schema(base,empty,[ident],'utility_id')['function']['parameters']
    assert Draft202012Validator(first).is_valid({'utility_id':ident,'fact_keys':None})
    assert not Draft202012Validator(first).is_valid({'utility_id':ident,'fact_keys':['compared_hours']})
    catalog=a.call(pid,'utility_comparison_read',{'utility_id':ident},False)
    record={'events':[{'tool':'utility_comparison_read','status':'succeeded','result':catalog}]}
    schema=reads.leaf_schema(base,record,[ident],'utility_id')['function']['parameters'];validator=Draft202012Validator(schema)
    assert validator.is_valid({'utility_id':ident,'fact_keys':['compared_hours']})
    for keys in [None,['comparison_hours'],['compared_hours','compared_hours']]:assert not validator.is_valid({'utility_id':ident,'fact_keys':keys})
    with pytest.raises(core.ValidationError,match='catalog'):reads.validate(record,reads.ReadSelection(record_id=ident))


def test_mixed_batch_selects_numeric_energy_fields_and_preserves_real_leaf_reads(client,native,monkeypatch):
    pid,r,_=create_utility(client,native,monkeypatch);a=client.app.state.agent;wall=create_record(client,pid,'thermal')
    selected=[{'record_id':r['utility_id'],'fact_keys':['interval_count']},{'record_id':wall['thermal_id'],'fact_keys':None}]
    delivery=lambda kind,source,key:tool('professional_deliver',{'delivery':{'kind':kind,'record_id':source[kind+'_id'],'record_hash':source['hash'],'fact_keys':[key],'finish':True}})
    one=delivery('utility',r,'interval_count');two=delivery('thermal',wall,'u_w_m2k');two['tool_calls'][0]['id']='other'
    scripted(a,monkeypatch,[tool('utility_comparison_read',{'utility_id':r['utility_id']}),tool('professional_read_many',{'selections':selected}),{'role':'assistant','tool_calls':one['tool_calls']+two['tool_calls']}])
    t=a.start(pid,Chat(message='读取'+r['utility_id']+'的账期数和'+wall['thermal_id']+'的传热系数',mode='provider'),background=False)
    assert t['status']=='succeeded',t.get('error')
    event=next(e for e in t['events'] if e['tool']=='professional_read_many')
    projected=event['result']['records'][0]['current']
    assert [f['fact'] for f in projected['explanation_facts']]==['interval_count']
    assert len([e for e in t['events'] if e.get('parent_event') is not None])==2
    assert len(t['events'])<=15 and len(t['answer']['checked_statements'])==2
    assert tool_event_cost('professional_read_many',{'selections':selected})==3


def test_batch_selection_rejects_duplicate_or_dual_interface():
    ident='utility_'+'a'*32;selection={'record_id':ident,'fact_keys':['interval_count']}
    with pytest.raises(ValueError):ToolArgs(selections=[selection,selection])
    with pytest.raises(ValueError):ToolArgs(selections=[selection],record_ids=[ident])
    assert reads.ReadSelection(record_id='thermal_'+'b'*32,fact_keys=['u_w_m2k']).fact_keys==['u_w_m2k']


def test_successful_catalog_read_cannot_be_dropped_on_early_finish(client,native,monkeypatch):
    from backend import agent_recovery
    pid,r,_=create_utility(client,native,monkeypatch)
    agent=client.app.state.agent
    wall=create_record(client,pid,'thermal')
    numeric=lambda kind,source,key:tool('professional_deliver',{'delivery':{
        'kind':kind,'record_id':source[kind+'_id'],'record_hash':source['hash'],
        'fact_keys':[key],'finish':True}})
    history=scripted(agent,monkeypatch,[
        tool('utility_comparison_read',{'utility_id':r['utility_id']}),
        tool('thermal_read',{'thermal_id':wall['thermal_id']}),
        numeric('thermal',wall,'u_w_m2k'),
        tool('utility_comparison_read',{'utility_id':r['utility_id'],'fact_keys':['cvrmse_percent']}),
        numeric('utility',r,'cvrmse_percent')])
    task=agent.start(pid,Chat(message='Read CV and wall U '+r['utility_id']+' '+wall['thermal_id'],
        mode='provider'),background=False)
    assert task['status']=='succeeded',task.get('error')
    assert task['early_finish_with_unresolved_reads']==[r['utility_id']]
    assert len(history)==5
    assert {row['record_id'] for row in task['answer']['checked_statements']}=={r['utility_id'],wall['thermal_id']}
    assert not agent_recovery.unresolved(task)
    assert len(task['events'])<=15


def test_controller_recheck_does_not_create_an_extra_model_selected_target():
    from backend import agent_recovery
    ident='utility_'+'a'*32
    record={'objective':'open_ended','events':[{'tool':'utility_comparison_read','status':'succeeded',
        'origin':'controller','result':{'utility_id':ident}}]}
    assert agent_recovery.unresolved(record)==[]
    record['events'][0]['origin']='model'
    assert agent_recovery.unresolved(record)==[ident]

def test_inspection_read_is_already_its_delivery_without_open_task_obligations():
    from backend import agent_recovery
    record={'objective':'inspect_thermal','events':[
        {'tool':'thermal_read','status':'succeeded','origin':'model',
         'result':{'thermal_id':'thermal_'+'b'*32}}]}
    assert agent_recovery.unresolved(record)==[]
