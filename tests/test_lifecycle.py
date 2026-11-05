from decimal import Decimal
import copy
import pytest
from pydantic import ValidationError
from backend.lifecycle import Inventory, calculate, STAGES
from test_api import create_project


def inventory():
    values = [('production',2,'t',.5,'kg','whole_period'), ('transport',200,'tkm',.1,'tkm','whole_period'),
        ('construction',100,'kWh',.5,'kWh','whole_period'), ('operation',1000,'kWh',.5,'kWh','annual'),
        ('end_of_life',10,'t',2,'t','whole_period')]
    return {'name':'Independent audit inventory', 'area_m2':927.2, 'study_years':20, 'region':'US-CO',
        'method':'Synthetic GWP test', 'functional_unit':'Same hypothetical office over twenty years',
        'boundaries':[{'stage':s,'included':True,'reason':'Independent arithmetic fixture'} for s in sorted(STAGES)],
        'activities':[{'activity_id':s,'name':s,'stage':s,'quantity':q,'unit':u,'period':p,'source':'Independent arithmetic input',
            'factor':{'factor_id':s+'-test','value':v,'denominator':d,'stage':s,'source':'Synthetic test factor; not official',
                'publisher':'Test author','version':'1','year':2025,'region':'*','method':'Synthetic GWP test'}} for s,q,u,v,d,p in values]}


def test_independent_decimal_oracle_and_functional_unit():
    r = calculate(Inventory(**inventory()))
    expected = Decimal(2)*1000*Decimal('.5')+Decimal(200)*Decimal('.1')+100*Decimal('.5')+1000*Decimal('.5')*20+10*2
    assert r['boundary_total_kgco2e'] == float(expected) == 11090
    assert r['kgco2e_m2_over_study_period'] == pytest.approx(float(expected/Decimal('927.2')))
    assert r['issued_credits_t'] is None and r['certification'] == 'NOT_ASSESSED'


@pytest.mark.parametrize('missing', ['factor','quantity','stage'])
def test_missing_does_not_become_zero(missing):
    b=inventory()
    if missing=='stage': b['activities'].pop()
    elif missing=='quantity': b['activities'][0]['quantity']=None
    else: b['activities'][0]['factor']['value']=None
    r=calculate(Inventory(**b))
    assert r['boundary_total_kgco2e'] is None and r['missing'] and r['status']=='incomplete'


@pytest.mark.parametrize('field,value', [('quantity',-1),('quantity',True),('quantity','2'),('quantity',float('nan')),('unit','m3')])
def test_invalid_activity_inputs(field,value):
    b=inventory(); b['activities'][0][field]=value
    with pytest.raises(ValidationError): Inventory(**b)


@pytest.mark.parametrize('field,value', [('numerator','kgCO2'),('stage','operation'),('method','Other assessment'),('region','CN-JX'),('year',True)])
def test_incompatible_factor_rejected(field,value):
    b=inventory(); b['activities'][0]['factor'][field]=value
    with pytest.raises(ValidationError): Inventory(**b)


def test_exclusions_conflicts_duplicates_and_zero_denominator():
    b=inventory(); b['area_m2']=0
    with pytest.raises(ValidationError): Inventory(**b)
    b=inventory(); b['activities'].append(b['activities'][0].copy())
    with pytest.raises(ValidationError): Inventory(**b)
    b=inventory(); b['boundaries'][0]['included']=False
    with pytest.raises(ValidationError): Inventory(**b)
    excluded=b['boundaries'][0]['stage']; b['activities']=[a for a in b['activities'] if a['stage']!=excluded]
    r=calculate(Inventory(**b))
    assert r['boundary_total_kgco2e'] is not None and not r['all_five_stages_entered']
    assert r['stages'][excluded]['kgco2e'] is None


def test_history_comparison_export_and_project_revision(client):
    p=create_project(client); base=f'/api/projects/{p["project_id"]}'
    b=inventory(); a=client.post(base+'/lifecycle',json=b)
    assert a.status_code==201, a.text
    a=a.json(); b['activities'][0]['factor']['value']=.4
    c=client.post(base+'/lifecycle',json=b).json()
    r=client.post(base+'/lifecycle-comparisons',json={'lifecycle_ids':[a['lifecycle_id'],c['lifecycle_id']]}).json()
    assert r['results'][1]['reduction_kgco2e']==200
    assert '11090' in client.get(base+'/lifecycle/'+a['lifecycle_id']+'/report.html').text
    other=create_project(client)['project_id']
    assert client.get(f'/api/projects/{other}/lifecycle/'+a['lifecycle_id']).status_code==409
    b['study_years']=30; d=client.post(base+'/lifecycle',json=b).json()
    assert client.post(base+'/lifecycle-comparisons',json={'lifecycle_ids':[a['lifecycle_id'],d['lifecycle_id']]}).status_code==409
    building=p['building']; building['area_m2']=1000
    assert client.put(base+'/building',json={'expected_revision':p['revision'],'building':building}).status_code==200
    old=client.get(base+'/lifecycle/'+a['lifecycle_id']).json()
    assert old['status']=='stale' and old['result'] is None
    assert client.post(base+'/lifecycle',json=b).status_code==409
    client.cookies.clear()
    assert client.get(base+'/lifecycle').status_code==401


def test_import_original_and_evidence_withdrawal(client):
    pid=create_project(client)['project_id']; base=f'/api/projects/{pid}'
    source=client.post(base+'/files',files={'file':('factor.json',b'{"synthetic":true}')}).json()
    ev=client.post(base+'/evidence',json={'type':'literature','name':'test source','source_file':source['file_id'],
        'source_locator':'page 1','authority':'Test author','permission':'synthetic','acquisition_method':'test',
        'responsible_person':'auditor','status':'IMPORTED'}).json()
    b=inventory(); b['activities'][0]['factor']['evidence_id']=ev['evidence_id']; b['import_file_id']=source['file_id']
    a=client.post(base+'/lifecycle',json=b).json()
    assert a['import_source']['hash']==source['hash']
    assert client.patch(base+'/evidence/'+ev['evidence_id'],json={'expected_revision':1,'review_state':'confirmed',
        'responsible_person':'auditor','review_note':'Test source inspected, not certification'}).status_code==200
    assert client.get(base+'/lifecycle/'+a['lifecycle_id']).json()['status']=='stale'
    fresh=client.post(base+'/lifecycle',json=b).json()
    _,path=client.app.state.domain.file_record(pid,source['file_id']);path.write_bytes(b'tamper')
    assert client.get(base+'/lifecycle/'+fresh['lifecycle_id']).json()['result'] is None
    assert client.post(base+'/lifecycle',json=b).status_code==409
    assert client.app.state.domain.store.get('lifecycle',a['lifecycle_id'])['result']['boundary_total_kgco2e']==11090


def test_factor_version_conflict_and_annual_scope():
    b=inventory(); extra=copy.deepcopy(b['activities'][0]);extra['activity_id']='second-material';extra['factor']['version']='2'
    b['activities'].append(extra)
    with pytest.raises(ValidationError,match='inconsistent'): Inventory(**b)
    b=inventory(); b['activities'][0]['period']='annual'
    with pytest.raises(ValidationError,match='Annual'): Inventory(**b)


def test_zero_baseline_extreme_ratio_and_report_escape(client):
    pid=create_project(client)['project_id'];base=f'/api/projects/{pid}'
    b=inventory();b['name']='<script>alert(1)</script>'
    for a in b['activities']: a['quantity']=0
    zero=client.post(base+'/lifecycle',json=b).json()
    normal=client.post(base+'/lifecycle',json=inventory()).json()
    def compare(a,c):
        return client.post(base+'/lifecycle-comparisons',json={'lifecycle_ids':[a['lifecycle_id'],c['lifecycle_id']]})
    assert compare(zero,normal).json()['results'][1]['reduction_pct'] is None
    text=client.get(base+'/lifecycle/'+zero['lifecycle_id']+'/report.html').text
    assert '<script>' not in text and '&lt;script&gt;' in text
    b['activities'][0]['quantity']=1e-300;b['activities'][0]['factor']['value']=1e-10
    tiny=client.post(base+'/lifecycle',json=b).json()
    assert compare(tiny,normal).status_code==409
    b=inventory();b['activities'][0]['factor']['value']=None
    incomplete=client.post(base+'/lifecycle',json=b).json()
    assert compare(incomplete,normal).status_code==409


def test_import_schema_rejects_unknown_fields_and_foreign_file(client):
    pid=create_project(client)['project_id']; other=create_project(client)['project_id']
    source=client.post(f'/api/projects/{other}/files',files={'file':('other.json',b'{}')}).json()
    b=inventory();b['import_file_id']=source['file_id']
    assert client.post(f'/api/projects/{pid}/lifecycle',json=b).status_code==409
    b=inventory();b['invented_field']=42
    assert client.post(f'/api/projects/{pid}/lifecycle-validation',json=b).status_code==422


def test_rejected_factor_evidence_cannot_support_new_inventory(client):
    pid=create_project(client)['project_id'];base='/api/projects/'+pid
    ev=client.post(base+'/evidence',json={'type':'literature','name':'Withdrawn factor source',
        'source_locator':'Independent test row 1','authority':'Synthetic source','permission':'test only',
        'acquisition_method':'Independent test','responsible_person':'auditor','status':'IMPORTED'}).json()
    b=inventory();b['activities'][0]['factor']['evidence_id']=ev['evidence_id']
    old=client.post(base+'/lifecycle',json=b).json()
    assert client.patch(base+'/evidence/'+ev['evidence_id'],json={'expected_revision':1,'review_state':'rejected',
        'responsible_person':'auditor','review_note':'Source rejected after independent review'}).status_code==200
    assert client.get(base+'/lifecycle/'+old['lifecycle_id']).json()['status']=='stale'
    response=client.post(base+'/lifecycle',json=b)
    assert response.status_code==409, response.text
