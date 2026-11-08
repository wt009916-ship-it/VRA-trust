from decimal import Decimal as D
import copy
import pytest
from pydantic import ValidationError
from backend import core
from backend.collection_scenarios import CollectionScenarioRequest
from backend.material_scenarios import calculate, report
from test_material_scenarios import payload as layer_payload, reference as layer_reference


def reference():
    return {'materialset_id':'materialset_'+'a'*32,'hash':'frozen-reference','product_ids':[100,200],
            'result':{'materials':[{'material_id':101,'material_name':'A','union_envelope_m3':8.4},
                                   {'material_id':102,'material_name':'B','union_envelope_m3':27.6}]}}, {'building':{'area_m2':100.}}


def payload(source):
    # Reuse explicit synthetic prices/factors; never adapt source quantity rows.
    old,_=layer_reference();body=layer_payload(old)
    body.pop('takeoff_id');body['materialset_id']=source['materialset_id'];body['excluded_materials']=[]
    body['functional_scope']='The same selected wall collection under declared functional conditions'
    template=copy.deepcopy(body['alternatives'])
    for i,alt in enumerate(body['alternatives']):
        alt.pop('layers');alt['materials']=[]
        for material in source['result']['materials']:
            row=copy.deepcopy(template[i]['layers'][0]);row.pop('layer_id')
            mid=material['material_id'];row['source_material_id']=mid;row['material_id']=f'proposed-{i}-{mid}'
            row['quote']['quote_id']=f'quote-{i}-{mid}';row['factor']['factor_id']=f'factor-{i}-{mid}'
            alt['materials'].append(row)
    return body


def test_independent_decimal_cost_carbon_uses_deduplicated_materials_only():
    source,project=reference();body=payload(source)
    result=calculate(CollectionScenarioRequest.model_validate(body),source,project,source_kind='collection')
    # Actual union: 36m3, not sum 48. Explicit half-solid x1.1 waste =19.8m3.
    purchase=D(36)*D('.5')*D('1.1')
    assert result['status']=='calculated'
    assert result['alternatives'][0]['cost']['material_total']=='1980.00'
    assert result['alternatives'][1]['cost']['material_total']=='1584.00'
    assert D(str(result['alternatives'][0]['carbon']['boundary_total_kgco2e']))==purchase*1000*2
    assert result['comparison']['cost_difference']=='-396.00'
    assert D(result['comparison']['carbon_reduction_kgco2e'])==9900
    rows=result['alternatives'][0]['derivations']
    assert all('layer_id' not in r for r in rows)
    assert [r['source_material_id'] for r in rows]==[101,102]
    assert all('materialset_' in r['source_locator'] and 'material #' in r['source_locator'] for r in rows)
    assert result['issued_credits_t'] is None and result['functional_equivalence']=='NOT_ASSESSED'
    html=report({'status':result['status'],'input':body,'result':result})
    assert '来源材料实体 / 拟用材料' in html and '1980.00' in html
    assert '来源层 / 拟用材料' not in html


@pytest.mark.parametrize('missing',['solid_fraction','waste_ratio','density_kg_m3'])
def test_unknown_material_conversion_has_no_complete_comparison(missing):
    source,project=reference();body=payload(source);row=body['alternatives'][0]['materials'][0]
    row[missing]=None
    if missing=='density_kg_m3':row['density_source']=None
    r=calculate(CollectionScenarioRequest.model_validate(body),source,project,source_kind='collection')
    assert r['status']=='incomplete' and r['comparison'] is None
    assert r['alternatives'][0]['cost']['material_total'] is None


@pytest.mark.parametrize('attack',['volume','layer_id','duplicate','conflicting_factor','conflicting_quote'])
def test_forged_quantity_or_identity_and_inconsistent_catalog_are_rejected(attack):
    source,_=reference();body=payload(source);a=body['alternatives'][0]['materials'];b=body['alternatives'][1]['materials']
    if attack=='volume':a[0]['union_envelope_m3']=999
    elif attack=='layer_id':a[0]['layer_id']=101
    elif attack=='duplicate':a.append(copy.deepcopy(a[0]))
    elif attack=='conflicting_factor':b[0]['factor']['factor_id']=a[0]['factor']['factor_id']
    elif attack=='conflicting_quote':b[0]['quote']['quote_id']=a[0]['quote']['quote_id']
    with pytest.raises(ValidationError):CollectionScenarioRequest.model_validate(body)


def test_both_alternatives_must_cover_same_materials_or_explicit_shared_exclusion():
    source,project=reference();body=payload(source)
    body['alternatives'][0]['materials'].pop()
    with pytest.raises(core.ValidationError):calculate(CollectionScenarioRequest.model_validate(body),source,project,source_kind='collection')
    body['alternatives'][1]['materials'].pop();body['excluded_materials']=[{'source_material_id':102,'reason':'Explicit shared excluded material in arithmetic reference'}]
    r=calculate(CollectionScenarioRequest.model_validate(body),source,project,source_kind='collection')
    assert r['status']=='calculated' and len(r['alternatives'][0]['derivations'])==1
    assert r['alternatives'][0]['cost']['material_total']=='462.00'


def five_stage_payload(source):
    body=payload(source)
    for boundary in body['boundaries']:boundary.update(included=True,reason='Declared reference activities, not a complete measured building inventory')
    for alt in body['alternatives']:
        def factor(ident,stage,value,unit):
            return {'factor_id':ident,'stage':stage,'value':value,'denominator':unit,'source':'Synthetic independent arithmetic reference',
                    'publisher':'QA reference','version':'v1','year':2026,'region':'US-CO','method':'QA arithmetic'}
        alt['transport_legs']=[{'leg_id':'haul','name':'Declared material haul','material_ids':[r['material_id'] for r in source['result']['materials']],
            'purchase_fraction':1.,'fraction_source':'All purchased material on one reference leg','distance_km':50.,'distance_source':'Synthetic fifty kilometre route',
            'additional_mass_kg':0.,'additional_mass_source':'Explicit no additional packaging mass in reference',
            'factor':factor('haul-factor','transport',.1,'tkm')}]
        alt['other_activities']=[{'activity_id':stage,'name':stage,'stage':stage,'quantity':quantity,'unit':unit,'period':period,
            'source':'Synthetic arithmetic reference, not building measurement','factor':factor(stage+'-factor',stage,value,unit)}
            for stage,quantity,unit,period,value in [('construction',10.,'kWh','whole_period',.2),('operation',500.,'kWh','annual',.4),('end_of_life',5.,'kg','whole_period',.3)]]
    return body


def test_five_stage_transport_uses_material_ids_and_exact_purchase_mass():
    source,project=reference();body=five_stage_payload(source)
    r=calculate(CollectionScenarioRequest.model_validate(body),source,project,source_kind='collection')
    a=r['alternatives'][0]
    assert r['status']=='calculated'
    assert D(a['transport'][0]['quantity_tkm'])==D('19.8')*50
    assert [p['source_material_id'] for p in a['transport'][0]['materials']]==[101,102]
    assert a['carbon']['boundary_total_kgco2e']==pytest.approx(39600+99+2+6000+1.5)
    assert '所选材料实体' in report({'status':r['status'],'input':body,'result':r})
    body['alternatives'][0]['transport_legs'][0]['material_ids']=[999]
    with pytest.raises(core.ValidationError):calculate(CollectionScenarioRequest.model_validate(body),source,project,source_kind='collection')
