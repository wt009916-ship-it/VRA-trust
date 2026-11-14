"""Model wire selection before numeric observation, with actual source services."""
import json
import pytest
from backend import agent_actions, agent_metric_reads
from backend.agent import Chat
from backend.agent_semantics import model_projection
from test_api import create_project
from test_agent_professional import create_record


def selected_wire(agent, monkeypatch, steps):
    monkeypatch.setattr(agent.gateway, 'public', lambda: {'enabled': True, 'key_configured': True})
    responses = iter(steps)
    seen = []
    def complete(messages, tools, **options):
        seen.append(tools)
        name, arguments = next(responses)
        raw = {'role':'assistant','content':json.dumps({'actions':[{'tool':name,'arguments':arguments}]})}
        return agent_actions.decode(raw, tools)
    monkeypatch.setattr(agent.gateway, 'complete', complete)
    return seen


@pytest.mark.parametrize('kind,key', [('thermal','u_w_m2k'),('lifecycle','stage.production')])
def test_model_selects_only_requested_fact_before_reading_values(client,monkeypatch,kind,key):
    pid=create_project(client)['project_id']
    source=create_record(client,pid,kind)
    agent=client.app.state.agent
    ident=source[kind+'_id']
    seen=selected_wire(agent,monkeypatch,[
        (kind+'_read',{kind+'_id':ident,'fact_keys':[key]}),
        ('professional_deliver',{'delivery':{'kind':kind,'record_id':ident,
          'record_hash':source['hash'],'fact_keys':[key],'finish':True}})])
    task=agent.start(pid,Chat(message='Only '+key+' from '+ident,mode='provider'),background=False)
    assert task['status']=='succeeded',task.get('error')
    assert task['metric_read_selections']=={ident:[key]}
    assert [f['fact'] for f in task['answer']['checked_statements'][0]['facts']]==[key]
    read=next(e for e in task['events'] if e['tool']==kind+'_read' and e['origin']=='model')
    assert len(read['result']['explanation_facts'])>1
    assert [f['fact'] for f in model_projection(read['result'],kind)['explanation_facts']]==[key]
    schema=next(t['function']['parameters'] for t in seen[0] if t['function']['name']==kind+'_read')
    assert 'fact_keys' in schema['oneOf'][0]['required']


@pytest.mark.parametrize('next_tool', ['thermal_read','professional_deliver'])
def test_observed_values_cannot_expand_selected_metrics(client,monkeypatch,next_tool):
    pid=create_project(client)['project_id']
    source=create_record(client,pid,'thermal')
    agent=client.app.state.agent
    ident=source['thermal_id']
    args={'thermal_id':ident,'fact_keys':['total_resistance_m2k_w']} if next_tool=='thermal_read' else {
        'delivery':{'kind':'thermal','record_id':ident,'record_hash':source['hash'],
                    'fact_keys':['total_resistance_m2k_w'],'finish':True}}
    selected_wire(agent,monkeypatch,[
        ('thermal_read',{'thermal_id':ident,'fact_keys':['u_w_m2k']}),
        (next_tool,args),(next_tool,args),(next_tool,args)])
    task=agent.start(pid,Chat(message='Only U from '+ident,mode='provider'),background=False)
    assert task['status']=='failed'
    assert task['metric_read_selections']=={ident:['u_w_m2k']}
    assert not task['professional_deliveries']
    assert any(e.get('protocol_recovery') or e.get('raw_action_response') for e in task['events'])
    assert not any(e['tool']==next_tool and e['status']=='succeeded' and
        e.get('arguments',{}).get('fact_keys')==['total_resistance_m2k_w'] for e in task['events'])


def test_internal_inspection_read_preserves_existing_whole_record_behavior(client):
    pid=create_project(client)['project_id']
    source=create_record(client,pid,'thermal')
    read=client.app.state.agent.call(pid,'thermal_read',{'thermal_id':source['thermal_id']},False)
    assert len(model_projection(read,'thermal')['explanation_facts'])==3


def test_frozen_selection_cannot_be_expanded_by_later_read():
    record={}
    first=agent_metric_reads.ReadSelection(record_id='thermal_'+'a'*32,fact_keys=['u_w_m2k'])
    agent_metric_reads.freeze_selection(record,first)
    with pytest.raises(ValueError):
        agent_metric_reads.freeze_selection(record,first.model_copy(update={'fact_keys':['total_resistance_m2k_w']}))


@pytest.mark.parametrize('kind,key', [('engineering','max_deflection_m'),('schedule','planned_duration_days'),('operation','sample_count'),('cost','material_total'),('scenario','cost_difference')])
def test_other_professions_use_selected_wire_contract(client,monkeypatch,tmp_path,kind,key):
    from backend.agent_semantics import inspection
    from test_agent_engineering import make_plan
    from test_agent_calculations import plan
    from test_agent_scenarios import scenario
    agent=client.app.state.agent
    spec=inspection(kind)
    if kind=='scenario':
        pid,source=scenario(client,tmp_path)
    else:
        pid=create_project(client)['project_id']
        typed=Chat(message='Prepare reference',mode='provider',allow_compute=True,
                   calculation_plans=[plan('cost') if kind=='cost' else make_plan(client,pid,kind)]).calculation_plans[0]
        source=spec.service(agent.domain).save(pid,typed.input)
    ident=source[spec.record_key]
    selected_wire(agent,monkeypatch,[
        (spec.read_tool,{spec.argument:ident,'fact_keys':[key]}),
        ('professional_deliver',{'delivery':{'kind':kind,'record_id':ident,'record_hash':source['hash'],'fact_keys':[key],'finish':True}})])
    task=agent.start(pid,Chat(message='Only '+key+' from '+ident,mode='provider'),background=False)
    assert task['status']=='succeeded',task.get('error')
    assert task['metric_read_selections']=={ident:[key]}
    assert [f['fact'] for f in task['answer']['checked_statements'][0]['facts']]==[key]
