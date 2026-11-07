import copy
from decimal import Decimal

import pytest
from pydantic import ValidationError

from backend.material_scenarios import ScenarioRequest, calculate
from test_api import create_project
from test_material_takeoff import create_takeoff


def payload(takeoff):
    layers = takeoff['result']['layers']
    def alternative(name, price, factor):
        rows = []
        for row in layers:
            key = str(row['layer_id'])
            rows.append({'layer_id':row['layer_id'], 'material_id':name+key, 'name':name+' material '+key,
                'solid_fraction':0.5, 'fraction_source':'Synthetic reference: half of layer envelope',
                'waste_ratio':0.1, 'waste_basis':'Synthetic reference: ten percent procurement waste',
                'density_kg_m3':1000.0, 'density_source':'Synthetic reference density, not a manufacturer declaration',
                'quote':{'quote_id':name+key, 'unit_price':price, 'per_unit':'t', 'currency':'USD',
                    'tax_basis':'excluded', 'region':'US-CO', 'valid_from':'2026-01-01', 'valid_until':'2026-12-31',
                    'source':'Synthetic reference quote, not market data', 'version':'reference-v1'},
                'factor':{'factor_id':name+key, 'value':factor, 'denominator':'kg', 'stage':'production',
                    'source':'Synthetic reference factor, not an EPD', 'publisher':'QA reference',
                    'version':'reference-v1', 'year':2026, 'region':'US-CO', 'method':'QA arithmetic'}})
        return {'name':name, 'layers':rows}
    return {'takeoff_id':takeoff['takeoff_id'], 'functional_scope':'The same selected wall layers over one declared service period',
        'region':'US-CO', 'currency':'USD', 'tax_basis':'excluded', 'as_of':'2026-11-08',
        'exclusions':['Labour, machinery and taxes are not in material cost'], 'study_years':30,
        'method':'QA arithmetic', 'boundaries':[{'stage':s, 'included':s=='production',
            'reason':'Production only in this reference comparison' if s=='production' else 'Excluded explicitly in this reference comparison'}
            for s in ['production','transport','construction','operation','end_of_life']],
        'alternatives':[alternative('Baseline',100.0,2.0),alternative('Replacement',80.0,1.5)]}


def reference():
    takeoff={'takeoff_id':'takeoff_'+'a'*32, 'product_id':1, 'hash':'frozen-test-source',
        'result':{'layers':[{'layer_id':10,'material_id':20,'material_name':'Synthetic layer 1','envelope_volume_m3':5.6},
                            {'layer_id':11,'material_id':21,'material_name':'Synthetic layer 2','envelope_volume_m3':16.4}]}}
    return takeoff, {'building':{'area_m2':100.0}}


def test_two_alternatives_match_independent_decimal_quantity_cost_and_carbon():
    takeoff,project=reference()
    result=calculate(ScenarioRequest.model_validate(payload(takeoff)),takeoff,project)
    # Independent geometric truth: 24 m3 host - 2 m3 opening = 22 m3 envelope;
    # declared half-solid, 10% waste, 1000 kg/m3 -> 12.1 t procurement.
    purchase=(Decimal(24)-Decimal(2))*Decimal('.5')*Decimal('1.1')
    assert purchase == Decimal('12.1')
    assert result['status']=='calculated'
    assert result['alternatives'][0]['cost']['material_total']==str((purchase*100).quantize(Decimal('.01')))
    assert result['alternatives'][1]['cost']['material_total']=='968.00'
    assert result['alternatives'][0]['carbon']['boundary_total_kgco2e']==float(purchase*1000*2)
    assert result['alternatives'][1]['carbon']['boundary_total_kgco2e']==18150
    assert result['comparison']['cost_difference']=='-242.00'
    assert Decimal(result['comparison']['carbon_reduction_kgco2e'])==6050
    assert result['issued_credits_t'] is None


@pytest.mark.parametrize('field',['solid_fraction','waste_ratio','density_kg_m3'])
def test_unknown_conversion_does_not_invent_quantity(field):
    takeoff,project=reference();body=payload(takeoff)
    row=body['alternatives'][0]['layers'][0];row[field]=None
    if field=='density_kg_m3':row['density_source']=None
    result=calculate(ScenarioRequest.model_validate(body),takeoff,project)
    assert result['status']=='incomplete' and result['comparison'] is None
    assert result['alternatives'][0]['cost']['material_total'] is None
    assert result['alternatives'][0]['carbon']['boundary_total_kgco2e'] is None


@pytest.mark.parametrize('change',['quantity','negative','duplicate','factor_conflict','wrong_stage','missing_source'])
def test_rejects_forged_quantities_and_inconsistent_sources(change):
    takeoff,_=reference();body=payload(takeoff);row=body['alternatives'][0]['layers'][0]
    if change=='quantity':row['net_quantity']=999
    if change=='negative':row['solid_fraction']=-1
    if change=='duplicate':body['alternatives'][0]['layers'].append(copy.deepcopy(row))
    if change=='factor_conflict':
        other=body['alternatives'][1]['layers'][0]['factor'];other['factor_id']=row['factor']['factor_id']
    if change=='wrong_stage':row['factor']['stage']='operation'
    if change=='missing_source':row['fraction_source']=''
    with pytest.raises(ValidationError):ScenarioRequest.model_validate(body)


def test_layer_coverage_and_exclusion_are_shared_not_silently_dropped():
    takeoff,project=reference();body=payload(takeoff)
    body['alternatives'][0]['layers'].pop()
    with pytest.raises(ValueError,match='exactly once'):
        calculate(ScenarioRequest.model_validate(body),takeoff,project)
    body['excluded_layers']=[{'layer_id':11,'reason':'This layer is explicitly outside both alternatives'}]
    body['alternatives'][1]['layers'].pop()
    result=calculate(ScenarioRequest.model_validate(body),takeoff,project)
    assert result['alternatives'][0]['cost']['material_total']=='308.00'


def test_missing_included_stage_prevents_complete_carbon_comparison():
    takeoff,project=reference();body=payload(takeoff)
    body['boundaries'][1]['included']=True
    result=calculate(ScenarioRequest.model_validate(body),takeoff,project)
    assert result['status']=='incomplete' and result['comparison'] is None
    assert 'transport:no_activities' in result['alternatives'][0]['carbon']['missing']


def test_actual_ifc_to_two_scenarios_report_and_source_invalidation(client,tmp_path,monkeypatch):
    pid,takeoff=create_takeoff(client,tmp_path)
    body=payload(takeoff);base=f'/api/projects/{pid}/material-scenarios'
    invalid=copy.deepcopy(body)
    invalid['alternatives'][0]['layers'][0]['quote']['valid_until']='2026-01-31'
    rejected=client.post(base,json=invalid)
    assert rejected.status_code==409,rejected.text
    response=client.post(base,json=body)
    assert response.status_code==201,response.text
    record=response.json();service=client.app.state.material_scenarios
    assert record['status']=='calculated'
    assert record['result']['alternatives'][0]['cost']['material_total']=='1210.00'
    assert record['result']['alternatives'][0]['carbon']['boundary_total_kgco2e']==pytest.approx(24200,abs=1e-8)
    url=base+'/'+record['scenario_id']
    assert client.get(url).json()['hash']==record['hash']
    assert client.get(url+'/report.html').status_code==200
    assert '1210.00' in client.get(url+'/report.html').text
    assert client.get(base).json()[0]['scenario_id']==record['scenario_id']
    other=create_project(client)['project_id']
    assert client.get(f"/api/projects/{other}/material-scenarios/{record['scenario_id']}").status_code==409
    assert client.post(f'/api/projects/{other}/material-scenarios',json=body).status_code==409
    client.headers.pop('X-CSRF-Token')
    assert client.post(base,json=body).status_code==403
    stored=copy.deepcopy(service.store.get('scenario',record['scenario_id']))
    monkeypatch.setattr('backend.material_takeoff.calculator_version',lambda:'changed-layer-rules')
    current=client.get(url).json()
    assert current['status']=='stale' and current['result'] is None
    assert '1210.00' not in client.get(url+'/report.html').text
    assert service.store.get('scenario',record['scenario_id'])==stored
    client.cookies.clear()
    assert client.get(url).status_code==401
    assert client.get(url+'/report.html').status_code==401


def test_volume_factor_needs_no_density_and_zero_baseline_has_no_percentage():
    takeoff,project=reference();body=payload(takeoff)
    for alternative in body['alternatives']:
        for row in alternative['layers']:
            row['density_kg_m3']=None;row['density_source']=None
            row['quote']['per_unit']='m3';row['factor']['denominator']='m3'
    for row in body['alternatives'][0]['layers']:
        row['quote']['unit_price']=0.0;row['factor']['value']=0.0
    result=calculate(ScenarioRequest.model_validate(body),takeoff,project)
    assert result['status']=='calculated'
    assert result['comparison']['cost_reduction_pct'] is None
    assert result['comparison']['carbon_reduction_pct'] is None
    assert result['alternatives'][1]['carbon']['boundary_total_kgco2e']==pytest.approx(18.15)


def test_report_handles_unnamed_source_material():
    from backend.material_scenarios import report
    takeoff,project=reference();takeoff['result']['layers'][0]['material_name']=None
    body=ScenarioRequest.model_validate(payload(takeoff))
    result=calculate(body,takeoff,project)
    rendered=report({'status':'calculated','input':body.model_dump(mode='json'),'result':result})
    assert '未命名材料' in rendered
    assert result['alternatives'][0]['cost']['material_total']=='1210.00'
