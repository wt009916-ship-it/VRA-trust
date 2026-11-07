import copy
import re
from decimal import Decimal

import pytest
from pydantic import ValidationError

from backend.material_scenarios import ScenarioRequest, calculate, report
from backend.material_transport import TransportLeg, derive
from test_material_scenarios import payload, reference
from test_material_takeoff import create_takeoff


def factor(stage, value, unit):
    return {'factor_id':'reference-'+stage, 'stage':stage,'value':value,'denominator':unit,
        'source':'Synthetic reference factor, not an EPD or measured input','publisher':'QA reference',
        'version':'reference-v1','year':2026,'region':'US-CO','method':'QA arithmetic'}


def full_payload(takeoff):
    body=payload(takeoff)
    for b in body['boundaries']:
        b['included']=True;b['reason']='Explicit reference boundary for '+b['stage']
    for alternative in body['alternatives']:
        alternative['transport_legs']=[{'leg_id':'road','name':'Reference road leg',
            'layer_ids':[r['layer_id'] for r in alternative['layers']], 'purchase_fraction':1.0,
            'fraction_source':'All material purchase mass is on this reference leg',
            'distance_km':100.0,'distance_source':'Declared synthetic route distance, not map measurement',
            'additional_mass_kg':200.0,'additional_mass_source':'Explicit synthetic packaging and pallet mass',
            'factor':factor('transport',0.1,'tkm')}]
        alternative['other_activities']=[]
        for stage,q,u,p,v in [('construction',10.0,'kWh','whole_period',0.5),
                             ('operation',100.0,'kWh','annual',0.4),('end_of_life',100.0,'kg','whole_period',0.1)]:
            alternative['other_activities'].append({'activity_id':stage,'name':'Reference '+stage,
                'stage':stage,'quantity':q,'unit':u,'period':p,'source':'Synthetic reference activity, not building observation',
                'factor':factor(stage,v,u)})
    return body


def test_five_stage_scenarios_crosscheck_independent_arithmetic():
    takeoff,project=reference();body=ScenarioRequest.model_validate(full_payload(takeoff))
    result=calculate(body,takeoff,project)
    assert result['status']=='calculated'
    for alt,production in zip(result['alternatives'],[24200,18150]):
        stages=alt['carbon']['stages']
        assert stages['production']['kgco2e']==production
        assert stages['transport']['kgco2e']==123  # (22*.5*1.1*1000 + 200)/1000*100*.1
        assert stages['construction']['kgco2e']==5
        assert stages['operation']['kgco2e']==1200  # annual, 30 years
        assert stages['end_of_life']['kgco2e']==10
        assert alt['carbon']['boundary_total_kgco2e']==production+1338
        assert alt['carbon']['all_five_stages_entered']
    assert result['comparison']['carbon_reduction_kgco2e']=='6050.0'
    rendered=report({'status':'calculated','input':body.model_dump(mode='json'),'result':result})
    visible = rendered.split('<details><summary>输入、逐层公式及来源回执</summary>')[0]
    assert '123' in visible
    assert '阶段边界与排放' in visible and '寿命末期' in visible
    assert '期间倍数 30' in visible and re.search(r'3000(?:\.0+)? kWh', visible)
    assert re.search(r'1230(?:\.0+)? tkm', visible) and 'reference-v1' in visible
    # Production rows must be bound by activity ID, not by their position after transport rows.
    assert '6160' in rendered and '18040' in rendered


def test_public_ghg_guidance_road_example_without_calling_its_answer_in_calculator():
    # GHG Protocol 2013 technical guidance p62 illustrative road example:
    # 2 tonnes * 2000 km * 0.2 kgCO2e/tkm = 800; not a real-world factor.
    takeoff,_=reference();body=full_payload(takeoff)
    leg=body['alternatives'][0]['transport_legs'][0]
    leg.update(layer_ids=[10],distance_km=2000.0,additional_mass_kg=0.0)
    leg['factor'].update(value=0.2,factor_id='ghg-guidance-road-example')
    mapping=ScenarioRequest.model_validate(body).alternatives[0].layers[0]
    activities,receipts=derive([TransportLeg.model_validate(leg)],[mapping],[{'layer_id':10,'purchase_volume_m3':'2'}],takeoff)
    assert activities[0].quantity==4000 and activities[0].quantity*activities[0].factor.value==800
    assert Decimal(receipts[0]['shipped_mass_kg'])==2000


@pytest.mark.parametrize('key',['purchase_fraction','distance_km','additional_mass_kg'])
def test_missing_transport_input_keeps_stage_and_comparison_incomplete(key):
    takeoff,project=reference();body=full_payload(takeoff)
    body['alternatives'][0]['transport_legs'][0][key]=None
    result=calculate(ScenarioRequest.model_validate(body),takeoff,project)
    assert result['status']=='incomplete' and result['comparison'] is None
    assert result['alternatives'][0]['carbon']['stages']['transport']['kgco2e'] is None
    assert key in result['alternatives'][0]['transport'][0]['missing']


def test_multiple_legs_partial_shipments_and_zero_explicit_extra_mass():
    takeoff,project=reference();body=full_payload(takeoff)
    for alternative in body['alternatives']:
        second=copy.deepcopy(alternative['transport_legs'][0]);second.update(leg_id='rail',name='Reference rail leg',purchase_fraction=0.5,distance_km=500.0,additional_mass_kg=0.0)
        second['factor'].update(factor_id='reference-rail',value=0.02)
        alternative['transport_legs'].append(second)
    result=calculate(ScenarioRequest.model_validate(body),takeoff,project)
    assert result['alternatives'][0]['carbon']['stages']['transport']['kgco2e']==183.5


@pytest.mark.parametrize('change',['negative_distance','duplicate_layers','duplicate_legs','wrong_factor_unit','factor_conflict'])
def test_contradictory_transport_contracts_rejected(change):
    takeoff,_=reference();body=full_payload(takeoff);leg=body['alternatives'][0]['transport_legs'][0]
    if change=='negative_distance':leg['distance_km']=-1
    if change=='duplicate_layers':leg['layer_ids']=[10,10]
    if change=='duplicate_legs':body['alternatives'][0]['transport_legs'].append(copy.deepcopy(leg))
    if change=='wrong_factor_unit':leg['factor']['denominator']='kg'
    if change=='factor_conflict':body['alternatives'][1]['transport_legs'][0]['factor']['version']='conflicting-version'
    with pytest.raises(ValidationError):ScenarioRequest.model_validate(body)


def test_transport_cannot_reference_excluded_layer_or_hide_missing_density():
    takeoff,project=reference();body=full_payload(takeoff)
    body['alternatives'][0]['transport_legs'][0]['layer_ids']=[999]
    with pytest.raises(ValueError,match='excluded or unknown'):
        calculate(ScenarioRequest.model_validate(body),takeoff,project)
    body=full_payload(takeoff)
    row=body['alternatives'][0]['layers'][0];row['density_kg_m3']=None;row['density_source']=None
    result=calculate(ScenarioRequest.model_validate(body),takeoff,project)
    assert result['alternatives'][0]['transport'][0]['quantity_tkm'] is None


def test_real_ifc_five_stage_api_and_declared_boundary_conflict(client,tmp_path):
    pid,takeoff=create_takeoff(client,tmp_path);body=full_payload(takeoff)
    base=f'/api/projects/{pid}/material-scenarios'
    response=client.post(base,json=body);assert response.status_code==201,response.text
    result=response.json()
    assert result['status']=='calculated'
    assert result['result']['alternatives'][0]['carbon']['boundary_total_kgco2e']==pytest.approx(25538,abs=1e-8)
    body['boundaries'][1]['included']=False
    rejected=client.post(base,json=body)
    assert rejected.status_code==409 and 'excluded boundary' in rejected.text


@pytest.mark.parametrize('binding', ['transport_source', 'activity_source', 'transport_factor', 'activity_factor'])
def test_bound_stage_evidence_revision_withdraws_report_without_rewriting_history(client, tmp_path, binding):
    pid,takeoff=create_takeoff(client,tmp_path)
    ev_response=client.post(f'/api/projects/{pid}/evidence',json={
        'type':'literature','name':'Stage source','source_locator':'Reference row 1','authority':'QA reference',
        'permission':'test only','acquisition_method':'test','responsible_person':'auditor','status':'IMPORTED'})
    assert ev_response.status_code==201
    ev=ev_response.json();body=full_payload(takeoff)
    for alt in body['alternatives']:
        if binding=='transport_source':alt['transport_legs'][0]['evidence_ids']=[ev['evidence_id']]
        if binding=='activity_source':alt['other_activities'][0]['source_evidence_ids']=[ev['evidence_id']]
        if binding=='transport_factor':alt['transport_legs'][0]['factor']['evidence_id']=ev['evidence_id']
        if binding=='activity_factor':alt['other_activities'][0]['factor']['evidence_id']=ev['evidence_id']
    base=f'/api/projects/{pid}/material-scenarios';response=client.post(base,json=body)
    assert response.status_code==201,response.text
    record=response.json();assert record['status']=='calculated'
    assert [e['evidence_id'] for e in record['source_snapshot']]==[ev['evidence_id']]
    service=client.app.state.material_scenarios;stored=copy.deepcopy(service.store.get('scenario',record['scenario_id']))
    updated=client.patch(f"/api/projects/{pid}/evidence/{ev['evidence_id']}",json={
        'expected_revision':ev['revision'],'review_state':'rejected','responsible_person':'auditor','review_note':'Source withdrawn for independent recheck'})
    assert updated.status_code==200,updated.text
    url=base+'/'+record['scenario_id'];current=client.get(url).json()
    assert current['status']=='stale' and current['result'] is None
    assert '25538' not in client.get(url+'/report.html').text
    assert service.store.get('scenario',record['scenario_id'])==stored
    assert client.post(base,json=body).status_code==409


def test_included_stage_without_activity_and_excluded_stage_are_distinct_in_report():
    takeoff,project=reference();body=full_payload(takeoff)
    body['alternatives'][0]['other_activities']=[a for a in body['alternatives'][0]['other_activities'] if a['stage']!='construction']
    parsed=ScenarioRequest.model_validate(body);result=calculate(parsed,takeoff,project)
    assert result['comparison'] is None
    rendered=report({'status':'incomplete','input':parsed.model_dump(mode='json'),'result':result})
    assert '<td>施工</td><td>资料不完整</td><td>缺数据</td>' in rendered
    body=payload(takeoff);parsed=ScenarioRequest.model_validate(body);result=calculate(parsed,takeoff,project)
    rendered=report({'status':'calculated','input':parsed.model_dump(mode='json'),'result':result})
    assert '<td>材料运输</td><td>未纳入（不等于零）</td><td>未纳入</td>' in rendered
