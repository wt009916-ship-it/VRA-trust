"""Protocol tests, not evidence of autonomous model understanding."""
import copy
import json

import pytest
from pydantic import ValidationError

from backend import agent_outputs, core
from backend.agent import Chat, Agent
from backend.agent_requests import ReadRequest
from backend.agent_semantics import Statement, statement_instruction
from test_api import create_project
from test_agent_contract import scripted
from test_agent_capabilities import tool
from test_agent_professional import create_record
from test_agent_batch_tools import claim
from test_agent_outputs import scope, plan


def explicit(record):
    return {**scope(record), 'output_contract': {'fact_keys':['total_resistance_m2k_w'], 'explanation_topics':['area']}}


@pytest.mark.parametrize('kind', list(agent_outputs.FACTS))
def test_catalog_and_contract_share_one_authoritative_vocabulary(kind):
    catalog=agent_outputs.public_catalog()[kind]
    assert {f['key'] for f in catalog['facts']}==set(agent_outputs.FACTS[kind])
    assert all(f['label'] for f in catalog['facts'])
    request=ReadRequest(request_key='r',kind=kind,purpose='results',record_id=kind+'_'+'a'*32,
                        output_contract={'fact_keys':[catalog['facts'][0]['key']], 'explanation_topics':[]})
    assert request.output_contract.fact_keys


@pytest.mark.parametrize('contract',[
 {'fact_keys':['mbe_percent'],'explanation_topics':[]},
 {'fact_keys':['total_resistance_m2k_w']*2,'explanation_topics':[]},
 {'fact_keys':[],'explanation_topics':[]},
 {'fact_keys':[],'explanation_topics':['certification']},
 {'fact_keys':['certified_carbon_credits'],'explanation_topics':[]},
])
def test_contract_rejects_wrong_kind_unknown_duplicate_and_empty(contract):
    with pytest.raises(ValidationError):
        ReadRequest(request_key='r',kind='thermal',purpose='results',record_id='thermal_'+'a'*32,output_contract=contract)


def test_no_legacy_flag_bypass_and_availability_cannot_request_numbers():
    req=explicit({'thermal_id':'thermal_'+'a'*32})
    with pytest.raises(ValidationError):Chat(message='read',mode='provider',read_requests=[req],infer_outputs=False)
    req['purpose']='availability'
    with pytest.raises(ValidationError):ReadRequest.model_validate(req)


@pytest.mark.parametrize('change',[
 {'fact_keys':['u_w_m2k']}, {'fact_keys':[]},
 {'fact_keys':['total_resistance_m2k_w','u_w_m2k']},
 {'explanation_topics':[]}, {'explanation_topics':['area','scope']},
 {'fact_keys':[],'explanation_topics':[],'clarification_reason':'ambiguous_request','clarification_question':'Choose another metric?'},
])
def test_model_cannot_rewrite_user_outputs(change):
    req=explicit({'thermal_id':'thermal_'+'a'*32})
    record={'question':'Give total R and explain area.','read_requests':[req]}
    with pytest.raises(core.ValidationError,match='user-selected'):
        agent_outputs.freeze(record,[agent_outputs.OutputItem.model_validate({**plan(),**change})])
    assert 'output_plan' not in record


def test_current_selected_outputs_recheck_and_contract_mutation_invalidates(client,monkeypatch):
    pid=create_project(client)['project_id'];a=client.app.state.agent;r=create_record(client,pid,'thermal')
    scripted(a,monkeypatch,[tool('requested_output_plan',{'output_plan':[plan()]})])
    t=a.start(pid,Chat(message='Give total R and explain area.',mode='provider',read_requests=[explicit(r)]),background=False)
    assert t['status']=='succeeded',t.get('error')
    answer=t['answer'];assert answer['output_contract_coverage']=='fulfilled'
    assert answer['user_selected_output_keys']==['wall'] and answer['free_question_coverage']=='not_verified'
    assert answer['output_plan']['items'][0]['requirement_origin']=='user_selected'
    assert not answer['output_plan']['intent_verified'] and answer['task_completion']=='partial'
    record=copy.deepcopy(a.store.get('agent',t['agent_id']))
    record['read_requests'][0]['output_contract']['fact_keys']=['u_w_m2k']
    refreshed=agent_outputs.attach(copy.deepcopy(answer),record)
    assert refreshed['output_contract_coverage']=='contract_changed' and not refreshed['requested_outputs']


def test_wrong_numeric_delivery_refused_even_with_valid_source_and_false_completion(client,monkeypatch):
    pid=create_project(client)['project_id'];a=client.app.state.agent;r=create_record(client,pid,'thermal')
    args=json.loads(claim(r)['tool_calls'][0]['function']['arguments'])
    args['delivery']['statements'][0].update(fact='layer_resistance_m2k_w',value='1.8')
    done={'role':'assistant','content':'Everything is complete.'}
    scripted(a,monkeypatch,[tool('requested_output_plan',{'output_plan':[plan()]}),
        tool('thermal_read',{'thermal_id':r['thermal_id']}),tool('professional_deliver',args),done,done,done])
    t=a.start(pid,Chat(read_execution='model',message='Give total R and explain area.',mode='provider',read_requests=[explicit(r)]),background=False)
    failed=[e for e in t['events'] if e['tool']=='professional_deliver' and e['status']=='failed']
    assert failed and 'user-selected metric contract' in failed[0]['error']
    assert not (t.get('answer') or {}).get('checked_statements')
    assert t['status']=='failed' and t['answer'] is None
    assert not t.get('model_finished_delivery')


def test_tool_schema_locks_explicit_arrays_and_source_instructions_follow_fields():
    req=explicit({'thermal_id':'thermal_'+'a'*32})
    tool_schema=next(t for t in Agent.tools(None, {'requested_output_plan'}) if t['function']['name']=='requested_output_plan')
    selected=agent_outputs.constrain_tool(tool_schema,[req],'Give total R and explain area.')
    variant=selected['function']['parameters']['properties']['output_plan']['items']['oneOf'][0]['properties']
    assert variant['fact_keys']['const']==req['output_contract']['fact_keys']
    assert variant['explanation_topics']['const']==['area']
    assert all(field in statement_instruction() for field in Statement.model_fields)


def test_authenticated_catalog_and_bad_contract_api_validation(client):
    pid=create_project(client)['project_id']
    catalog=client.get('/api/agent/status');assert catalog.status_code==200
    assert 'bill_total_kwh' in {f['key'] for f in catalog.json()['output_catalog']['utility']['facts']}
    req=explicit({'thermal_id':'thermal_'+'a'*32});req['output_contract']['fact_keys']=['mbe_percent']
    response=client.post('/api/projects/'+pid+'/agent/chat',json={'message':'read','mode':'provider','read_requests':[req]})
    assert response.status_code==422
