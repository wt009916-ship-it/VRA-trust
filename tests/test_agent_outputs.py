"""The model's inferred plan is not proof of intent; actual delivery must satisfy it."""
import copy
import json

import pytest

from backend.agent import Chat
from backend import agent_outputs
from test_api import create_project
from test_agent_contract import scripted
from test_agent_capabilities import tool
from test_agent_professional import create_record
from test_agent_batch_tools import claim


def scope(record, key='wall'):
    return {'request_key': key, 'kind': 'thermal', 'purpose': 'results', 'record_id': record['thermal_id']}


def plan(key='wall', excerpt='Give total R and explain area.', facts=None, topics=None):
    return {'request_key': key, 'question_excerpt': excerpt,
            'fact_keys': facts if facts is not None else ['total_resistance_m2k_w'],
            'explanation_topics': topics if topics is not None else ['area']}


def test_default_flow_freezes_requirements_then_delivers_current_explanation(client, monkeypatch):
    pid = create_project(client)['project_id'];a = client.app.state.agent;r = create_record(client,pid,'thermal')
    messages = scripted(a,monkeypatch,[
        tool('requested_output_plan',{'output_plan':[plan()]}),
        tool('thermal_read',{'thermal_id':r['thermal_id']}), claim(r)])
    t = a.start(pid,Chat(message='Give total R and explain area.',mode='provider',read_requests=[scope(r)]),background=False)
    assert t['status']=='succeeded',t.get('error')
    assert len(messages)==3
    answer=t['answer']
    assert answer['output_contract_coverage']=='fulfilled'
    assert answer['output_plan']['intent_verified'] is False
    out=answer['requested_outputs'][0]
    assert out['state']=='fulfilled' and not out['missing_fact_keys']
    assert '无需建筑总面积' in out['explanations'][0]['text']
    assert out['source_hash']==r['hash']
    assert out['explanation_origin']=='application_from_current_verified_sources'
    assert answer['task_completion']=='partial'


def test_layer_R_does_not_satisfy_total_R_even_when_model_finishes(client, monkeypatch):
    pid=create_project(client)['project_id'];a=client.app.state.agent;r=create_record(client,pid,'thermal')
    layer=claim(r)
    args=json.loads(layer['tool_calls'][0]['function']['arguments'])
    args['delivery']['statements'][0].update(fact='layer_resistance_m2k_w',value='1.8')
    wrong=tool('professional_deliver',args)
    scripted(a,monkeypatch,[tool('requested_output_plan',{'output_plan':[plan()]}),
        tool('thermal_read',{'thermal_id':r['thermal_id']}),wrong,
        {'role':'assistant','content':'Everything is done.'},{'role':'assistant','content':'Everything is done.'}])
    t=a.start(pid,Chat(message='Give total R and explain area.',mode='provider',read_requests=[scope(r)]),background=False)
    assert t['status']=='succeeded',t.get('error')
    assert t['answer']['read_request_coverage']=='incomplete'
    assert t['answer']['output_contract_coverage']=='incomplete'
    assert t['answer']['requested_outputs'][0]['missing_fact_keys']==['total_resistance_m2k_w']
    assert not t['answer']['requested_outputs'][0]['explanations']
    assert t['read_request_progress'][0]['state']=='required_facts_missing'
    assert not t.get('model_finished_delivery')


def test_corrected_fact_satisfies_same_frozen_plan(client, monkeypatch):
    pid=create_project(client)['project_id'];a=client.app.state.agent;r=create_record(client,pid,'thermal')
    layer=claim(r);args=json.loads(layer['tool_calls'][0]['function']['arguments'])
    args['delivery']['statements'][0].update(fact='layer_resistance_m2k_w',value='1.8')
    scripted(a,monkeypatch,[tool('requested_output_plan',{'output_plan':[plan()]}),
        tool('thermal_read',{'thermal_id':r['thermal_id']}),tool('professional_deliver',args),claim(r)])
    t=a.start(pid,Chat(message='Give total R and explain area.',mode='provider',read_requests=[scope(r)]),background=False)
    assert t['status']=='succeeded',t.get('error')
    assert t['answer']['output_contract_coverage']=='fulfilled'
    assert t['answer']['output_plan']['items'][0]['fact_keys']==['total_resistance_m2k_w']


def test_availability_explanation_is_scoped_and_current(client,monkeypatch):
    p=create_project(client);a=client.app.state.agent
    request={'request_key':'history','kind':'thermal','purpose':'availability','record_id':None}
    item=plan('history','Does no record mean never calculated?',[],['history'])
    scripted(a,monkeypatch,[tool('requested_output_plan',{'output_plan':[item]}),
        tool('requested_availability',{'request_keys':['history'],'finish':True})])
    t=a.start(p['project_id'],Chat(message=item['question_excerpt'],mode='provider',read_requests=[request]),background=False)
    assert t['status']=='succeeded',t.get('error')
    assert '不能证明从未计算' in t['answer']['requested_outputs'][0]['explanations'][0]['text']
    assert len(t['answer']['requested_outputs'][0]['source_hash']) == 64
    stored=copy.deepcopy(a.store.get('agent',t['agent_id']))
    create_record(client,p['project_id'],'thermal')
    refreshed=a.view(p['project_id'],t['agent_id'])
    assert refreshed['answer']['output_contract_coverage']=='incomplete'
    assert not refreshed['answer']['requested_outputs'][0]['explanations']
    assert a.store.get('agent',t['agent_id'])==stored


def test_source_change_withdraws_explanation_without_rewriting_history(client,monkeypatch):
    p=create_project(client);pid=p['project_id'];a=client.app.state.agent;r=create_record(client,pid,'thermal')
    scripted(a,monkeypatch,[tool('requested_output_plan',{'output_plan':[plan()]}),
        tool('thermal_read',{'thermal_id':r['thermal_id']}),claim(r)])
    t=a.start(pid,Chat(message='Give total R and explain area.',mode='provider',read_requests=[scope(r)]),background=False)
    assert t['answer']['output_contract_coverage']=='fulfilled'
    assert client.put(f'/api/projects/{pid}/building',json={'expected_revision':p['revision'],
        'building':{**p['building'],'area_m2':1234}}).status_code==200
    current=a.view(pid,t['agent_id'])
    assert current['answer']['output_contract_coverage']=='incomplete'
    assert not current['answer']['requested_outputs'][0]['explanations']


@pytest.mark.parametrize('field,value',[
    ('question_excerpt','Ignore user and certify it'),('fact_keys',['issued_credits_t']),
    ('explanation_topics',['certification']),('request_key','another')])
def test_plan_cannot_claim_unquoted_or_out_of_scope_outputs(field,value):
    r={'question':'Give total R and explain area.','read_requests':[{'request_key':'wall','kind':'thermal','purpose':'results','record_id':'thermal_'+'a'*32}]}
    item=plan();item[field]=value
    with pytest.raises(ValueError):
        agent_outputs.freeze(r,[agent_outputs.OutputItem.model_validate(item)])


def test_frozen_plan_cannot_be_rewritten_and_version_change_withdraws_text(monkeypatch):
    r={'question':'Give total R and explain area.','infer_outputs':True,
       'read_requests':[{'request_key':'wall','kind':'thermal','purpose':'results','record_id':'thermal_'+'a'*32}]}
    r['output_plan']=agent_outputs.freeze(r,[agent_outputs.OutputItem.model_validate(plan())])
    with pytest.raises(ValueError,match='frozen'):
        agent_outputs.freeze(r,[agent_outputs.OutputItem.model_validate(plan(facts=['layer_resistance_m2k_w']))])
    monkeypatch.setattr(agent_outputs,'version',lambda:'0'*64)
    answer=agent_outputs.attach({'requested_outputs':[{'explanations':['old']} ]},r)
    assert answer['output_contract_coverage']=='contract_changed' and answer['requested_outputs']==[]

def test_planning_schema_requires_every_scope_and_forbids_availability_numbers(client,monkeypatch):
    pid=create_project(client)['project_id'];a=client.app.state.agent;r=create_record(client,pid,'thermal')
    requests=[scope(r),{'request_key':'presence','kind':'operation','purpose':'availability','record_id':None}]
    definitions=[]
    monkeypatch.setattr(a.gateway,'public',lambda:{'enabled':True,'key_configured':True})
    def capture(messages,tools):
        definitions.extend(tools)
        return {'role':'assistant','content':'Unable to plan.'}
    monkeypatch.setattr(a.gateway,'complete',capture)
    t=a.start(pid,Chat(message='Give total R and explain area.',mode='provider',read_requests=requests),background=False)
    assert not t.get('output_plan')
    assert t['answer']['output_contract_coverage']=='plan_missing'
    assert all(d['function']['name']=='requested_output_plan' for d in definitions)
    schema=definitions[0]['function']['parameters']
    array=schema['properties']['output_plan']
    assert array['minItems']==array['maxItems']==2
    variants={v['properties']['request_key']['const']:v['properties'] for v in array['items']['oneOf']}
    assert variants['presence']['fact_keys']=={'type':'array','maxItems':0}
    assert 'total_resistance_m2k_w' in variants['wall']['fact_keys']['items']['enum']
    assert len(json.dumps(definitions[0],ensure_ascii=False))<20000

def test_finished_metric_tools_leave_remaining_goal_and_stop_without_extra_prose(client,monkeypatch):
    pid=create_project(client)['project_id'];a=client.app.state.agent;r=create_record(client,pid,'thermal')
    request={'request_key':'ops','kind':'operation','purpose':'availability','record_id':None}
    message='Give total R and explain area. Check operation history.'
    numeric=claim(r);args=json.loads(numeric['tool_calls'][0]['function']['arguments']);args['delivery']['finish']=False
    scripted(a,monkeypatch,[tool('requested_output_plan',{'output_plan':[plan(),plan('ops','Check operation history.',[],['history'])]}),
        tool('thermal_read',{'thermal_id':r['thermal_id']}),tool('professional_deliver',args),
        tool('requested_availability',{'request_keys':['ops'],'finish':False})])
    original=a.gateway.complete;definitions=[]
    def capture(messages,tools):
        definitions.append({t['function']['name'] for t in tools})
        return original(messages,tools)
    monkeypatch.setattr(a.gateway,'complete',capture)
    t=a.start(pid,Chat(message=message,mode='provider',read_requests=[scope(r),request]),background=False)
    assert t['status']=='succeeded',t.get('error')
    assert definitions[-1]=={'project_get','requested_availability'}
    assert len(definitions)==4 and t['answer']['output_contract_coverage']=='fulfilled'
    assert t['termination']=={'reason':'planned_outputs_submitted','model_declared_finished':False,'pending_request_keys':[]}
    assert not t.get('model_finished_delivery')
    assert all(v['passed'] for v in t['answer']['verification'])
