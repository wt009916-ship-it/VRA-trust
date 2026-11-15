from pathlib import Path
ROOT=Path('C:/Users/18483/AppData/Local/Temp/vra-timestep-reliability-20261108')
(ROOT/'tests/test_agent_actions.py').write_text('''"""Wire/schema/controller tests only; live model acceptance is separate."""
import copy
import json
import httpx
import pytest
from jsonschema import Draft202012Validator
from backend import core, agent_actions, agent_selections
from backend.agent import Agent, Chat, TOOLS
from test_local_model import configured, reply
from test_api import create_project
from test_agent_professional import create_record
from test_agent_contract import scripted
from test_agent_capabilities import tool
from test_agent_outputs import scope, plan


def simple_tools():
    return [{'type':'function','function':{'name':'read','description':'Read selected fact','parameters':{
        'type':'object','properties':{'fact':{'type':'string','enum':['R','U']}},'required':['fact'],'additionalProperties':False}}}]


@pytest.mark.parametrize('text',[
 'Done. {"actions":[]}', '{"actions":[]}', '{"actions":[],"claim":"done"}',
 '{"actions":[{"tool":"write","arguments":{}}]}',
 '{"actions":[{"tool":"read","arguments":{"fact":"carbon_credit"}}]}',
 '{"actions":[{"tool":"read","arguments":{"fact":"R","value":1}}]}',
 '{"actions":[{"tool":"read","arguments":{"fact":"R","fact":"U"}}]}',
 '{"actions":[{"tool":"read","arguments":{"fact":NaN}}]}',
 '{"actions":[{"tool":"read","arguments":{"fact":1e9999}}]}',
])
def test_no_prose_extra_fields_unoffered_actions_or_numeric_invention(text):
    raw={'role':'assistant','content':text}
    with pytest.raises(agent_actions.ActionProtocolError) as error:agent_actions.decode(raw,simple_tools())
    assert error.value.response==raw


def test_complete_schema_keeps_references_and_constraints_for_all_tools():
    tools=Agent.tools(None,set(TOOLS));schema=agent_actions.schema(tools)
    Draft202012Validator.check_schema(schema)
    def refs(value):
        if isinstance(value,dict):
            if '$ref' in value:assert value['$ref'].removeprefix('#/$defs/') in schema['$defs']
            for item in value.values():refs(item)
        elif isinstance(value,list):
            for item in value:refs(item)
    refs(schema)
    assert len(schema['properties']['actions']['items']['oneOf'])==len(TOOLS)
    assert not Draft202012Validator(schema).is_valid({'actions':[{'tool':'professional_deliver','arguments':{'delivery':{}}}]})


def test_local_action_wire_has_strict_schema_and_preserves_raw_message(client,monkeypatch):
    gateway=configured(client,monkeypatch);seen=[]
    raw={'role':'assistant','content':json.dumps({'actions':[{'tool':'read','arguments':{'fact':'R'}}]})}
    def serve(request):
        seen.append(json.loads(request.content));response=reply();response['choices'][0]['message']=raw
        return httpx.Response(200,json=response)
    result=gateway.complete([{'role':'user','content':'R'}],simple_tools(),response_mode='actions',transport=httpx.MockTransport(serve))
    assert seen[0]['response_format']['type']=='json_schema' and 'tools' not in seen[0] and 'tool_choice' not in seen[0]
    assert result['_raw_action_response']==raw and result['content']==''
    assert json.loads(result['tool_calls'][0]['function']['arguments'])=={'fact':'R'}


def test_unsupported_action_format_never_retries_auto(client,monkeypatch):
    gateway=configured(client,monkeypatch);seen=[]
    def serve(request):seen.append(json.loads(request.content));return httpx.Response(400,json={'error':'unsupported schema'})
    with pytest.raises(core.ValidationError):gateway.complete([],simple_tools(),response_mode='actions',transport=httpx.MockTransport(serve))
    assert len(seen)==1 and seen[0]['response_format']['type']=='json_schema'


def test_malformed_action_raw_response_not_swallowed_by_gateway(client,monkeypatch):
    gateway=configured(client,monkeypatch);raw={'role':'assistant','content':'Already delivered R=999'}
    def serve(_):
        result=reply();result['choices'][0]['message']=raw;return httpx.Response(200,json=result)
    with pytest.raises(agent_actions.ActionProtocolError) as error:gateway.complete([],simple_tools(),response_mode='actions',transport=httpx.MockTransport(serve))
    assert error.value.response==raw


def selected(r,keys=None):
    return {'kind':'thermal','record_id':r['thermal_id'],'record_hash':r['hash'],'fact_keys':keys or ['total_resistance_m2k_w'],'finish':True}


def test_receipt_constructs_values_and_rejects_unknown_or_older_read(client):
    pid=create_project(client)['project_id'];a=client.app.state.agent;r=create_record(client,pid,'thermal')
    source=a.call(pid,'thermal_read',{'thermal_id':r['thermal_id']},False)
    record={'events':[{'tool':'thermal_read','status':'succeeded','result':source}]}
    numeric,receipt=agent_selections.materialize(record,selected(r))
    assert numeric['statements'][0]['value']=='1.97' and receipt['read_event_index']==0
    with pytest.raises(core.ValidationError):agent_selections.materialize(record,selected(r,['unknown']))
    with pytest.raises(ValueError):agent_selections.materialize(record,{**selected(r),'value':'999'})
    changed=copy.deepcopy(source);changed['hash']='a'*64
    record['events'].append({'tool':'thermal_read','status':'succeeded','result':changed})
    with pytest.raises(core.ValidationError,match='latest'):agent_selections.materialize(record,selected(r))


def test_model_selects_fact_without_copying_number_and_source_is_rechecked(client,monkeypatch):
    pid=create_project(client)['project_id'];a=client.app.state.agent;r=create_record(client,pid,'thermal')
    scripted(a,monkeypatch,[tool('requested_output_plan',{'output_plan':[plan()]}),
        tool('thermal_read',{'thermal_id':r['thermal_id']}),tool('professional_deliver',{'delivery':selected(r)})])
    t=a.start(pid,Chat(message='Give total R and explain area.',mode='provider',read_execution='model',read_requests=[scope(r)]),background=False)
    assert t['status']=='succeeded',t.get('error')
    assert t['answer']['output_contract_coverage']=='fulfilled'
    event=next(e for e in t['events'] if e['tool']=='professional_deliver')
    assert event['arguments']['delivery']['fact_keys']==['total_resistance_m2k_w'] and 'statements' not in event['arguments']['delivery']
    assert event['selection_receipt']['current_source_recheck_required']
    assert t['answer']['checked_statements'][0]['facts'][0]['value']=='1.97'


def test_unresolved_direct_scope_has_typed_exit_without_completion_claim(client,monkeypatch):
    pid=create_project(client)['project_id'];a=client.app.state.agent;r=create_record(client,pid,'thermal')
    scripted(a,monkeypatch,[tool('requested_defer',{'request_keys':['wall']})])
    t=a.start(pid,Chat(message='Unclear metric',mode='provider',infer_outputs=False,read_requests=[scope(r)]),background=False)
    assert t['status']=='succeeded',t.get('error')
    assert t['answer']['task_completion']=='incomplete' and not t['answer'].get('checked_statements')
    assert t['read_request_progress'][0]['state']=='needs_clarification'
    assert t['termination']['reason']=='read_scopes_deferred'


def test_explicit_user_metrics_cannot_be_discarded_via_defer(client,monkeypatch):
    pid=create_project(client)['project_id'];a=client.app.state.agent;r=create_record(client,pid,'thermal')
    request={**scope(r),'output_contract':{'fact_keys':['total_resistance_m2k_w'],'explanation_topics':['area']}}
    scripted(a,monkeypatch,[tool('requested_output_plan',{'output_plan':[plan()]}),tool('requested_defer',{'request_keys':['wall']})])
    t=a.start(pid,Chat(message='Give total R and explain area.',mode='provider',read_execution='model',read_requests=[request]),background=False)
    assert not t.get('read_deferrals')
    assert any(e['tool']=='requested_defer' and e['status']=='failed' for e in t['events'])
''',encoding='utf-8')
print('Action protocol, receipt and deferral tests written')
