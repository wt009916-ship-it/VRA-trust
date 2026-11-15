"""Frozen independent scenarios; all factors/lifetimes synthetic, not an EPD."""
import copy
import json
from decimal import Decimal
from pathlib import Path
import pytest
from pydantic import ValidationError
from backend.lifecycle import Inventory, calculate
from test_lifecycle import inventory
from test_api import create_project

ORACLE = json.loads((Path(__file__).parents[1]/'fixtures/test/replacement_oracle.json').read_text())


def replacement_inventory():
    b = inventory()
    b['study_years'] = 60
    b['replacement_scope'] = 'separate_ledger'
    for a in b['activities']:
        a['replacement_overlap'] = 'excluded'
    processes = []
    for key, stage, q, unit, v, denom in [('production','production',.12,'t',1.8,'kg'),
            ('transport','transport',7.2,'tkm',.09,'tkm'),
            ('installation','construction',8,'kWh',.42,'kWh'),
            ('removal','end_of_life',120,'kg',.08,'kg')]:
        a = copy.deepcopy(b['activities'][0])
        a.update(activity_id='replacement-'+key, name=key, stage=stage, quantity=q, unit=unit, period='whole_period')
        a['factor'].update(factor_id='replacement-'+key, stage=stage,value=v,denominator=denom)
        processes.append({'process':key,'included':True,'reason':'Synthetic replacement process only','activity':a})
    b['replacements'] = [{'component_id':'wall-1','name':'Synthetic wall assembly', 'condition':'new',
        'service_life_years':20,'remaining_life_years':None,'life_source':'Synthetic independent schedule, not a recommended lifetime',
        'endpoint':'strictly_before_horizon','scope':'same_function_replacements_only',
        'overlap_review':'Reviewed synthetic base inputs exclude every replacement event; initial and final disposal stay separate.',
        'processes':processes}]
    return b


@pytest.mark.parametrize('case', ORACLE['schedules'])
def test_frozen_schedules(case):
    b=replacement_inventory();b['study_years']=case['years']; c=b['replacements'][0]
    c.update(service_life_years=case['life'],remaining_life_years=case['remaining'],condition='new' if case['remaining'] is None else 'existing')
    r=calculate(Inventory(**b))['replacement']['components'][0]
    assert r['years']==case['events'] and r['count']==len(case['events'])
    # Independent repeated addition Decimal oracle (production uses Fraction + ceiling).
    year=Decimal(str(case['remaining'] if case['remaining'] is not None else case['life']))
    expected=[]
    while year < case['years']:
        expected.append(float(year));year+=Decimal(str(case['life']))
    assert r['years']==expected


def test_independent_carbon_and_stage_sum():
    b=replacement_inventory(); r=calculate(Inventory(**b)); ledger=r['replacement']
    expected=Decimal('120')*Decimal('1.8')+Decimal('120')/1000*60*Decimal('.09')+8*Decimal('.42')+120*Decimal('.08')
    assert expected == Decimal(ORACLE['per_event']['total'])
    assert ledger['total_kgco2e']==pytest.approx(float(expected*2))
    c=ledger['components'][0]
    assert [p['kgco2e_per_event'] for p in c['processes']]==pytest.approx([216,.648,3.36,9.6])
    assert sum(e['kgco2e'] for e in c['events'])==pytest.approx(459.216)
    assert r['stages']['operation']['base_activity_kgco2e']==30000
    assert r['stages']['operation']['replacement_kgco2e']==pytest.approx(459.216)
    assert r['boundary_total_kgco2e']==pytest.approx(31549.216)
    assert sum(s['kgco2e'] for s in r['stages'].values())==pytest.approx(r['boundary_total_kgco2e'])
    assert r['certification']=='NOT_ASSESSED' and r['issued_credits_t'] is None


@pytest.mark.parametrize('life',[0,-1,True,'20',float('inf'),float('nan'),.00001])
def test_invalid_and_excessive_life(life):
    b=replacement_inventory();b['replacements'][0]['service_life_years']=life
    with pytest.raises(ValidationError): Inventory(**b)


@pytest.mark.parametrize('gap',['life','remaining','activity','quantity','factor'])
def test_unknown_data_never_zero(gap):
    b=replacement_inventory();c=b['replacements'][0];p=c['processes'][0]
    if gap=='life':c['service_life_years']=None
    elif gap=='remaining':c.update(condition='existing',remaining_life_years=None)
    elif gap=='activity':p['activity']=None
    elif gap=='quantity':p['activity']['quantity']=None
    else:p['activity']['factor']['value']=None
    r=calculate(Inventory(**b))
    assert r['status']=='incomplete' and r['boundary_total_kgco2e'] is None
    assert r['replacement']['missing'] and r['replacement']['total_kgco2e'] is None


@pytest.mark.parametrize('fault',['overlap_unknown','overlap_included','scope','duplicate','annual','units','version','endpoint','initial','remaining_new','process_duplicate','all_excluded','boundary','total_budget'])
def test_refusals(fault):
    b=replacement_inventory();c=b['replacements'][0];p=c['processes'][0]
    if fault.startswith('overlap_'):b['activities'][0]['replacement_overlap']=fault.split('_')[1]
    elif fault=='scope':b['replacement_scope']='included_in_activities'
    elif fault=='duplicate':b['replacements'].append(copy.deepcopy(c))
    elif fault=='annual':p['activity']['period']='annual'
    elif fault=='units':p['activity']['unit']='m2'
    elif fault=='version':p['activity']['factor'].update(factor_id=b['activities'][0]['factor']['factor_id'],version='other')
    elif fault=='endpoint':c['endpoint']='include_horizon'
    elif fault=='initial':c['scope']='include_initial_installation'
    elif fault=='remaining_new':c['remaining_life_years']=8
    elif fault=='process_duplicate':c['processes'][1]['process']='production'
    elif fault=='all_excluded':
        for x in c['processes']: x.update(included=False,activity=None)
    elif fault=='boundary':
        for x in b['boundaries']:
            if x['stage']=='operation':x['included']=False
        b['activities']=[a for a in b['activities'] if a['stage']!='operation']
    elif fault=='total_budget':
        c['service_life_years']=.1
        b['replacements']=[dict(copy.deepcopy(c),component_id=str(i)) for i in range(10)]
    with pytest.raises(ValidationError): Inventory(**b)


def test_excluded_process_is_visible_and_comparisons_refuse_boundary_change(client):
    pid=create_project(client)['project_id'];base=f'/api/projects/{pid}'
    b=replacement_inventory();a=client.post(base+'/lifecycle',json=b).json()
    b['replacements'][0]['processes'][3].update(included=False,activity=None,reason='Explicitly excluded synthetic removal process')
    r=client.post(base+'/lifecycle',json=b).json();c=r['result']['replacement']['components'][0]
    assert not c['all_four_processes_included'] and c['processes'][3]['kgco2e_per_event'] is None
    assert c['kgco2e']==pytest.approx(440.016)
    assert client.post(base+'/lifecycle-comparisons',json={'lifecycle_ids':[a['lifecycle_id'],r['lifecycle_id']]}).status_code==409


def test_api_lifetime_source_revision_report_and_history(client):
    pid=create_project(client)['project_id'];base=f'/api/projects/{pid}'
    source=client.post(base+'/files',files={'file':('life.json',b'{"synthetic_life_years":20}')}).json()
    ev=client.post(base+'/evidence',json={'type':'literature','name':'Lifetime basis','source_file':source['file_id'],
        'source_locator':'line 1','authority':'Synthetic author','permission':'test only','acquisition_method':'synthetic',
        'responsible_person':'auditor','status':'ASSUMED'}).json()
    b=replacement_inventory();b['replacements'][0]['life_evidence_id']=ev['evidence_id']
    response=client.post(base+'/lifecycle',json=b); assert response.status_code==201,response.text
    a=response.json();route=base+'/lifecycle/'+a['lifecycle_id']
    assert a['source_snapshot'][0]['hash']==ev['hash']
    report=client.get(route+'/report.html');assert report.status_code==200 and '459.216' in report.text
    assert '替换事件账' in report.text
    assert client.patch(base+'/evidence/'+ev['evidence_id'],json={'expected_revision':1,'review_state':'rejected',
        'responsible_person':'auditor','review_note':'Lifetime basis withdrawn after test review'}).status_code==200
    assert client.get(route).json()['result'] is None
    assert client.post(base+'/lifecycle',json=b).status_code==409
    assert client.app.state.domain.store.get('lifecycle',a['lifecycle_id'])['result']['replacement']['total_kgco2e']==pytest.approx(459.216)
    other=create_project(client)['project_id']
    assert client.post(f'/api/projects/{other}/lifecycle',json=b).status_code==409


def test_agent_plan_binds_lifetime_and_replacement_factor(client):
    from backend.agent_calculations import LifecyclePlan, bindings, snapshot, resolve
    from backend import core
    pid=create_project(client)['project_id'];base=f'/api/projects/{pid}'
    ev=client.post(base+'/evidence',json={'type':'literature','name':'Replacement source','source_locator':'row 1',
        'authority':'Test author','permission':'test','acquisition_method':'synthetic','responsible_person':'auditor','status':'ASSUMED'}).json()
    b=replacement_inventory();b['replacements'][0]['life_evidence_id']=ev['evidence_id']
    b['replacements'][0]['processes'][0]['activity']['factor']['evidence_id']=ev['evidence_id']
    plan=LifecyclePlan(plan_key='replace',kind='lifecycle',input=b)
    domain=client.app.state.domain;frozen=snapshot(domain,pid,[plan])
    assert bindings(domain,pid,plan)['sources'][0]['evidence_id']==ev['evidence_id']
    client.patch(base+'/evidence/'+ev['evidence_id'],json={'expected_revision':1,'review_state':'confirmed',
        'responsible_person':'auditor','review_note':'Updated source review without verifying lifetime'})
    with pytest.raises(core.ValidationError):resolve(domain,pid,'replace',[plan],frozen)


@pytest.mark.parametrize('binding',['life','factor'])
def test_bound_original_corruption_revokes_current_result(client,binding):
    pid=create_project(client)['project_id'];base=f'/api/projects/{pid}'
    f=client.post(base+'/files',files={'file':('basis.json',b'{"synthetic":true}')}).json()
    ev=client.post(base+'/evidence',json={'type':'literature','name':'Original source','source_file':f['file_id'],
        'source_locator':'test row','authority':'Test author','permission':'test','acquisition_method':'synthetic',
        'responsible_person':'auditor','status':'ASSUMED'}).json()
    b=replacement_inventory()
    if binding=='life':b['replacements'][0]['life_evidence_id']=ev['evidence_id']
    else:b['replacements'][0]['processes'][0]['activity']['factor']['evidence_id']=ev['evidence_id']
    saved=client.post(base+'/lifecycle',json=b);assert saved.status_code==201,saved.text
    record=saved.json();_,path=client.app.state.domain.file_record(pid,f['file_id']);path.write_bytes(b'corrupted original')
    stale=client.get(base+'/lifecycle/'+record['lifecycle_id']).json()
    assert stale['status']=='stale' and stale['result'] is None
    assert any(d['code']=='source_file_unavailable' for d in stale['stale_details'])
    assert client.post(base+'/lifecycle',json=b).status_code==409


def test_unassessed_replacement_is_not_zero_and_excluded_base_is_not_zero():
    b=inventory();r=calculate(Inventory(**b))
    assert r['replacement']['total_kgco2e'] is None
    b['boundaries'][0]['included']=False;excluded=b['boundaries'][0]['stage']
    b['activities']=[a for a in b['activities'] if a['stage']!=excluded]
    assert calculate(Inventory(**b))['stages'][excluded]['base_activity_kgco2e'] is None
