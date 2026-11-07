"""Independent field conflicts and real authenticated provenance flows."""
import copy
import hashlib

import pytest

from backend import core
from backend.design_condition_parser import parse, compare
from backend.design_conditions import DesignConditions, CheckInput
from test_api import create_project

FIELDS = ['Winter','1','21','WinterDesignDay','-10','0','DefaultMultipliers','',
          'WetBulb','-10','','','','','101325','3','0','No','No','No','ASHRAEClearSky','','','','','0']


def document(fields=None, *, model=False, site='Station,0,0,0,0', extra=''):
    return ((('Version,9.0;\n' if model else '')+'! Synthetic independently declared conditions\n'
             +'Site:Location,'+site+';\nSizingPeriod:DesignDay,'+','.join(fields or FIELDS)+';\n'+extra).encode())


def pair():
    return [{'model_day':'Winter','source_day':'Winter'}]


def test_numeric_format_and_explicit_name_mapping_do_not_change_field_meaning():
    altered=FIELDS.copy();altered[0]='Different source label';altered[4]='-1e1';altered[15]='3.000'
    result=compare(parse(document(model=True),model=True),parse(document(altered)),
                   [{'model_day':'Winter','source_day':altered[0]}])
    assert result['status']=='matching_declared_fields'
    assert result['rows'][0]['source_locator']['line']==3
    assert result['rows'][0]['model_locator']['line']==4
    assert result['source_authority']=='not_independently_verified'
    assert result['project_applicability']=='not_assessed'


@pytest.mark.parametrize('index,value,field',[
    (4,'-9','maximum_dry_bulb'),(14,'100000','barometric_pressure'),(15,'4','wind_speed'),
    (16,'180','wind_direction'),(8,'DewPoint','humidity_type'),(17,'Yes','rain'),
    (18,'Yes','snow'),(19,'Yes','daylight_saving'),(20,'ZhangHuang','solar_model'),
    (25,'1','sky_clearness'),(1,'2','month'),(5,'2','daily_dry_bulb_range')])
def test_same_name_never_hides_parameter_conflict(index,value,field):
    source=FIELDS.copy();source[index]=value
    result=compare(parse(document(model=True),model=True),parse(document(source)),pair())
    assert result['status']=='differences_found'
    assert [f['field'] for f in result['rows'][0]['fields'] if not f['equal']]==[field]


@pytest.mark.parametrize('index,value',[(1,'1.5'),(2,'32'),(4,'NaN'),(4,'-91'),(9,'-9'),
    (14,'0'),(15,'-1'),(16,'361'),(3,'InventedDay'),(8,'RelativeHumidity'),(23,'2'),(25,'-1')])
def test_invalid_parameters_cannot_match(index,value):
    source=FIELDS.copy();source[index]=value
    with pytest.raises(core.ValidationError):
        parse(document(source))


def test_missing_default_and_identical_schedule_names_are_not_silently_equivalent():
    a=FIELDS.copy();a[6]='';a[17]=''
    result=compare(parse(document(model=True),model=True),parse(document(a)),pair())
    assert result['status']=='differences_found'
    a=FIELDS.copy();a[6]='MultiplierSchedule';a[7]='SameSchedule'
    result=compare(parse(document(a,model=True),model=True),parse(document(a)),pair())
    assert result['status']=='unverified_dependencies'


def test_missing_model_days_and_weather_file_sizing_remain_open():
    other=FIELDS.copy();other[0]='Other'
    model=document(model=True,extra='SizingPeriod:DesignDay,'+','.join(other)+';')
    assert compare(parse(model,model=True),parse(document()),pair())['status']=='incomplete_model_coverage'
    model=document(model=True,extra='SizingPeriod:WeatherFileDays,Other,1,1,1,2;')
    assert compare(parse(model,model=True),parse(document()),pair())['status']=='unverified_dependencies'


def test_wrong_encoding_duplicate_site_days_and_truncation_are_rejected():
    with pytest.raises(core.ValidationError):
        parse(b'! \xb0 degree\n'+document())
    assert len(parse(b'! \xb0 degree\n'+document(),'cp1252')['days'])==1
    for raw in [document().rstrip()[:-1],document()+b'Site:Location,Other,0,0,0,0;',
                document()+b'SizingPeriod:DesignDay,'+','.join(FIELDS).encode()+b';',
                document().replace(b'Winter,',b'"Winter",',1),document()+b'\x00;']:
        with pytest.raises(core.ValidationError):
            parse(raw)


def setup_records(client):
    pid=create_project(client)['project_id']
    def upload(name,raw):
        r=client.post(f'/api/projects/{pid}/files',files={'file':(name,raw,'application/octet-stream')})
        assert r.status_code==201,r.text
        return r.json()
    raw=document(model=True);model=upload('model.idf',raw);source=upload('source.ddy',document())
    ev=client.post(f'/api/projects/{pid}/evidence',json={'type':'idf','name':'Synthetic model',
        'source_file':model['file_id'],'source_locator':'Independent fixture','authority':'Test fixture',
        'permission':'Synthetic test data','acquisition_method':'Test','responsible_person':'Tester','scheme_id':'baseline'}).json()
    r=client.patch(f"/api/projects/{pid}/evidence/{ev['evidence_id']}",json={'expected_revision':1,
        'review_state':'confirmed','responsible_person':'Tester','review_note':'Synthetic fixture inspected'})
    assert r.status_code==200,r.text
    ev=r.json()
    r=client.post(f'/api/projects/{pid}/design-sources',json={'file_id':source['file_id'],'title':'Synthetic design conditions',
        'publisher':'Independent test','edition':'Test v1','source_url':'https://example.org/reference',
        'acquired_on':'2026-01-01','permission':'Synthetic authorized fixture','scope':'Controlled synthetic test'})
    assert r.status_code==201,r.text
    source=r.json()
    body={'source_id':source['designsource_id'],'source_revision':1,'model_evidence_id':ev['evidence_id'],
          'model_revision':ev['revision'],'pairs':pair()}
    return pid,source,ev,body,hashlib.sha256(raw).hexdigest()


def reviewed(client,pid,source):
    response=client.post(f"/api/projects/{pid}/design-sources/{source['designsource_id']}/review",
        json={'expected_revision':source['revision'],'state':'confirmed','basis':'Synthetic source reviewed for this test only'})
    assert response.status_code==200,response.text
    return response.json()


def test_source_review_required_and_real_report_withdrawal_preserve_original(client):
    pid,source,ev,body,digest=setup_records(client)
    route=f'/api/projects/{pid}/design-checks'
    assert client.post(route,json=body).status_code==409
    source=reviewed(client,pid,source);body['source_revision']=source['revision']
    r=client.post(route,json=body);assert r.status_code==201,r.text
    saved=r.json();cid=saved['designcheck_id']
    assert saved['result']['status']=='matching_declared_fields'
    assert saved['model_snapshot']['file']['hash']==digest
    assert 'maximum_dry_bulb' in client.get(route+'/'+cid+'/report.html').text
    r=client.post(f"/api/projects/{pid}/design-sources/{source['designsource_id']}/review",
        json={'expected_revision':source['revision'],'state':'pending','basis':'Withdraw previous source review for test'})
    assert r.status_code==200
    view=client.get(route+'/'+cid).json()
    assert view['status']=='stale' and view['result'] is None
    assert 'design_source_changed_or_withdrawn' in view['stale_reasons']
    domain=client.app.state.domain
    stored=domain.store.get('designcheck',cid)
    assert stored['result']==saved['result']
    assert core.sha(domain.file_record(pid,ev['source_file'])[1])==digest


def test_cross_project_ids_rejected_and_source_bytes_rechecked(client):
    pid,source,ev,body,_=setup_records(client)
    source=reviewed(client,pid,source);body['source_revision']=source['revision']
    other=create_project(client)['project_id']
    assert client.get(f"/api/projects/{other}/design-sources/{source['designsource_id']}").status_code==404
    assert client.post(f'/api/projects/{other}/design-checks',json=body).status_code==404
    domain=client.app.state.domain
    _,path=domain.file_record(pid,source['input']['file_id'])
    path.write_bytes(b'corrupted synthetic source')
    view=client.get(f"/api/projects/{pid}/design-sources/{source['designsource_id']}").json()
    assert view['source_status']=='stale' and view['catalog'] is None
    assert client.post(f'/api/projects/{pid}/design-checks',json=body).status_code==409


def test_changed_model_during_comparison_never_persists_current_result(client,monkeypatch):
    pid,source,ev,body,_=setup_records(client)
    source=reviewed(client,pid,source);body['source_revision']=source['revision']
    domain=client.app.state.domain
    from backend import design_conditions
    original=design_conditions.parser.compare
    def race(*args):
        result=original(*args)
        newer=copy.deepcopy(ev);newer['review_state']='pending'
        domain.store.put('evidence',newer,ev['revision'])
        return result
    monkeypatch.setattr(design_conditions.parser,'compare',race)
    with pytest.raises(core.ValidationError):
        DesignConditions(domain).check(pid,CheckInput(**body),'test_user')
    assert domain.store.list('designcheck',pid)==[]


def test_project_and_anonymous_boundaries(client):
    pid,source,_,_,_=setup_records(client)
    route=f"/api/projects/{pid}/design-sources/{source['designsource_id']}"
    cookie=client.cookies
    client.cookies.clear()
    assert client.get(route).status_code==401
    client.cookies=cookie
    r=client.post('/api/auth/register',json={'username':'design_other','display_name':'Other','password':'Design-test-password-2026'})
    assert r.status_code==200
    client.headers['X-CSRF-Token']=r.json()['csrf_token']
    assert client.get(route).status_code==404
