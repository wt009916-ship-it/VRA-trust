"""Real IFC-to-scenario-to-Agent flow; model selection here is explicitly scripted."""
import copy
from decimal import Decimal

import pytest
from backend.agent import Chat, ToolRefusal, WRITE_TOOLS
from pydantic import TypeAdapter
from backend.agent_calculations import CalculationPlan
from backend.agent_semantics import facts, current_answer
from backend.agent_scenarios import context
from backend.material_scenarios import ScenarioRequest, calculate
from test_agent_contract import scripted
from test_agent_capabilities import tool
from test_api import create_project
from test_material_takeoff import create_takeoff
from test_material_scenarios import payload, reference
from test_material_transport import full_payload


def scenario(client,tmp_path,*,incomplete=False):
    pid,takeoff=create_takeoff(client,tmp_path);body=full_payload(takeoff)
    if incomplete:body['alternatives'][0]['layers'][0]['solid_fraction']=None
    response=client.post(f'/api/projects/{pid}/material-scenarios',json=body)
    assert response.status_code==201,response.text
    return pid,response.json()


def model_read(client,monkeypatch,pid,record,keys):
    a=client.app.state.agent
    calls=scripted(a,monkeypatch,[tool('requested_output_plan',{'output_plan':[{
        'request_key':'compare','question_fragment_ids':['q1'],'fact_keys':keys,'explanation_topics':['period','scope']} ]})])
    task=a.start(pid,Chat(message='核对这份材料两方案对照，并说明评估期和适用范围。',mode='provider',
        read_requests=[{'request_key':'compare','kind':'scenario','purpose':'results','record_id':record['scenario_id']}]),background=False)
    assert task['status']=='succeeded',task.get('error')
    assert len(calls)==1 and len(task['events'])<=15
    assert not any(e['tool'] in WRITE_TOOLS for e in task['events'])
    return task


def test_real_ifc_five_stage_comparison_to_local_and_application_agent(client,tmp_path,monkeypatch):
    pid,r=scenario(client,tmp_path);a=client.app.state.agent
    local=a.start(pid,Chat(message='核验材料两方案',objective='inspect_material_scenarios',target_scenario_id=r['scenario_id']),background=False)
    assert local['answer']['artifact']['kind']=='scenario_review' and local['answer']['artifact']['verified']
    keys=['baseline.material_total','alternative.material_total','cost_difference','baseline.boundary_total_kgco2e',
        'alternative.boundary_total_kgco2e','carbon_reduction_kgco2e','baseline.stage.transport','alternative.stage.operation',
        'baseline.kgco2e_m2_over_study_period']
    task=model_read(client,monkeypatch,pid,r,keys)
    answer=task['answer'];actual={f['fact']:f for f in answer['checked_statements'][0]['facts']}
    # Independent geometry and declared scenario arithmetic; no calculator output as oracle.
    tonnes=(Decimal(24)-Decimal(2))*Decimal('.5')*Decimal('1.1')
    extra=(tonnes+Decimal('.2'))*100*Decimal('.1')+5+100*30*Decimal('.4')+10
    expected={'baseline.material_total':tonnes*100,'alternative.material_total':tonnes*80,
        'cost_difference':tonnes*(80-100),'baseline.boundary_total_kgco2e':tonnes*1000*2+extra,
        'alternative.boundary_total_kgco2e':tonnes*1000*Decimal('1.5')+extra,
        'carbon_reduction_kgco2e':tonnes*1000*Decimal('.5'),'baseline.stage.transport':Decimal(123),
        'alternative.stage.operation':Decimal(1200)}
    for key,value in expected.items():assert Decimal(actual[key]['value'])==value,(key,actual[key])
    area=Decimal(str(r['result']['alternatives'][0]['carbon_input']['area_m2']))
    assert float(actual['baseline.kgco2e_m2_over_study_period']['value'])==pytest.approx(float(expected['baseline.boundary_total_kgco2e']/area),rel=1e-11)
    assert actual['baseline.material_total']['period']=='quote_date' and actual['baseline.material_total']['unit']=='USD'
    assert actual['alternative.stage.operation']['study_years']==30 and actual['alternative.stage.operation']['area_m2'] is None
    assert answer['output_contract_coverage']=='fulfilled' and not answer['output_plan']['intent_verified']
    assert answer['artifacts'][0]['record_hash']==r['hash'] and not answer['can_recommend']
    assert '/material-scenarios/'+r['scenario_id']+'/report.html' in answer['artifacts'][0]['report_path']
    stored=copy.deepcopy(a.store.get('scenario',r['scenario_id']))
    # Change retained test source, not a cached hash; historical Agent delivery must withdraw.
    _,source=a.domain.file_record(pid,r['import_source']['file_id']);source.write_bytes(source.read_bytes()+b'\n')
    current=current_answer(a.domain,pid,task['professional_deliveries'])
    assert current['checked_statements']==[] and current['artifacts']==[]
    limited=model_read(client,monkeypatch,pid,r,['baseline.material_total'])
    assert limited['answer']['checked_statements']==[] and limited['answer']['checked_limitations'][0]['state']=='stale'
    assert a.store.get('scenario',r['scenario_id'])==stored


def test_incomplete_comparison_withholds_numbers_and_rejects_cross_project(client,tmp_path,monkeypatch):
    pid,r=scenario(client,tmp_path,incomplete=True);assert r['status']=='incomplete'
    assert facts(r,'scenario')==[]
    task=model_read(client,monkeypatch,pid,r,['cost_difference'])
    assert task['answer']['checked_statements']==[] and task['answer']['checked_limitations'][0]['state']=='incomplete'
    other=create_project(client)['project_id']
    with pytest.raises(ToolRefusal):client.app.state.agent.call(other,'material_scenarios_read',{'scenario_id':r['scenario_id']},False)
    assert client.app.state.agent.store.list('scenario',other)==[]


def test_excluded_stages_absent_and_zero_denominators_explicitly_undefined():
    takeoff,project=reference();body=payload(takeoff)
    for alt in body['alternatives']:
        for layer in alt['layers']:layer['quote']['unit_price']=0;layer['factor']['value']=0
    result=calculate(ScenarioRequest.model_validate(body),takeoff,project)
    record={'status':'calculated','input':body,'result':result,'takeoff_id':takeoff['takeoff_id']}
    actual={f['fact']:f for f in facts(record,'scenario')}
    for key in ['cost_reduction_pct','carbon_reduction_pct']:
        assert actual[key]['value'] is None and actual[key]['source_value'] is None
        assert actual[key]['value_policy']=='source_undefined' and '分母为零' in actual[key]['unavailable_reason']
    assert 'baseline.stage.transport' not in actual and actual['baseline.stage.production']['value']=='0'
    assert context(record)['excluded_stages']==['transport','construction','operation','end_of_life']


def test_scenario_read_scope_does_not_grant_computation_or_accept_wrong_kind():
    ident='scenario_'+'a'*32
    with pytest.raises(ValueError):Chat(message='x',mode='provider',allow_compute=True,read_requests=[{'request_key':'x','kind':'scenario','purpose':'results','record_id':ident}])
    with pytest.raises(ValueError):Chat(message='x',mode='provider',read_requests=[{'request_key':'x','kind':'cost','purpose':'results','record_id':ident}])
    with pytest.raises(ValueError):TypeAdapter(CalculationPlan).validate_python({'plan_key':'x','kind':'scenario','input':{}})


def test_undefined_percent_is_source_limited_and_cannot_be_forged_as_zero(client,tmp_path,monkeypatch):
    from backend.agent_semantics import Delivery, Statement, check, SemanticMismatch
    pid,takeoff=create_takeoff(client,tmp_path);body=payload(takeoff)
    for layer in body['alternatives'][0]['layers']:
        layer['quote']['unit_price']=0;layer['factor']['value']=0
    response=client.post(f'/api/projects/{pid}/material-scenarios',json=body)
    assert response.status_code==201,response.text
    record=response.json();keys=['cost_reduction_pct','carbon_reduction_pct']
    task=model_read(client,monkeypatch,pid,record,keys);answer=task['answer']
    assert answer['read_request_progress'][0]['state']=='fields_unavailable'
    assert answer['read_request_coverage']=='all_declared_scopes_checked'
    assert answer['output_contract_coverage']=='addressed_with_source_limits'
    output=answer['requested_outputs'][0]
    assert output['state']=='source_limited' and output['missing_fact_keys']==[]
    assert output['unknown_fact_keys']==sorted(keys)
    current=answer['checked_statements'][0]['facts']
    assert len(current)==2 and all(f['value'] is None and f['unavailable_reason'] for f in current)
    from backend.agent_outputs import explain
    assert '分母为零' in explain('status',{'kind':'scenario'},current,'fields_unavailable',{})
    assert 'None' not in explain('meaning',{'kind':'scenario'},current,'fields_unavailable',{})
    for value in ['0','1','100']:
        claimed={k:current[0][k] for k in Statement.model_fields};claimed['value']=value
        delivery=Delivery(kind='scenario',record_id=record['scenario_id'],record_hash=record['hash'],statements=[claimed])
        with pytest.raises(SemanticMismatch):check(record,delivery)
