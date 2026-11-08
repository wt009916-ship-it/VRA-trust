
import pytest
from fastapi.testclient import TestClient

from test_api import create_project
from test_cad import upload
from test_beam_profiles import example
from test_engineering import beam


def prepare(client, *, changed=None):
    pid=create_project(client)['project_id'];doc,_,element,_,solid,_=example('IfcIShapeProfileDef',OverallWidth=.22,OverallDepth=.6,WebThickness=.012,FlangeThickness=.019,FilletRadius=.024)
    if changed:changed(doc,element,solid)
    raw=doc.to_string().encode();fid=upload(client,pid,'independent-beam.ifc',raw)
    base=f'/api/projects/{pid}'
    response=client.post(base+'/cad-inspections',json={'file_id':fid});assert response.status_code==201,response.text
    cad=response.json()
    response=client.post(base+'/ifc-beam-profiles',json={'cad_id':cad['cad_id'],'product_id':element.id()});assert response.status_code==201,response.text
    record=response.json()
    return pid,base,fid,cad,record,raw


def review(record):
    body=beam();body.update(width=None,depth=None)
    return {'expected_profile_hash':record['hash'],'bending_axis':'x','geometry_reviewed':True,
            'review_basis':'Independent synthetic fixture; profile axes explicitly reviewed, support span declared separately.', 'analysis':body}


def post(client,base,record,body=None):
    return client.post(base+'/ifc-beam-profiles/'+record['beamprofile_id']+'/analyses',json=body or review(record))


def test_real_isolated_ifc_extraction_to_beam_report_and_stale(client):
    pid,base,fid,cad,r,raw=prepare(client)
    assert r['status']=='extracted' and r['result']['resource_limits']
    assert r['result']['engineering_span_m'] is None
    response=post(client,base,r);assert response.status_code==201,response.text
    calculation=response.json();assert calculation['status']=='calculated'
    assert calculation['result']['metrics']['inertia_m4']==pytest.approx(.0009208345717756825,rel=1e-10)
    assert calculation['ifc_profile_snapshot']['actor_user_id']==client.get('/api/auth/me').json()['user']['id']
    report=client.get(base+'/beam-analyses/'+calculation['engineering_id']+'/report.html')
    assert report.status_code==200 and r['beamprofile_id'] in report.text
    assert client.get(base+'/files/'+fid).content==raw
    _,path=client.app.state.domain.file_record(pid,fid);path.write_bytes(raw+b'corruption')
    assert client.get(base+'/ifc-beam-profiles/'+r['beamprofile_id']).json()['result'] is None
    view=client.get(base+'/beam-analyses/'+calculation['engineering_id']).json()
    assert view['status']=='stale' and view['result'] is None
    assert post(client,base,r).status_code==409
    assert client.app.state.domain.store.get('engineering',calculation['engineering_id'])['result']['metrics']


def test_review_cannot_override_geometry_forge_actor_or_stale_hash(client):
    _,base,_,_,r,_=prepare(client)
    for mutate,status in [(lambda b:b.update(geometry_reviewed=False),409),
                          (lambda b:b.update(expected_profile_hash='0'*64),409),
                          (lambda b:b.update(actor_user_id='attacker'),422),
                          (lambda b:b['analysis'].update(width=.2),409),
                          (lambda b:b.update(bending_axis='z'),422)]:
        body=review(r);mutate(body);response=post(client,base,r,body)
        assert response.status_code==status,response.text
    assert client.get(base+'/beam-analyses').json()==[]


def test_missing_mechanical_values_remain_incomplete_not_extrusion_defaults(client):
    _,base,_,_,r,_=prepare(client);body=review(r)
    body['analysis'].update(span=None,elastic_modulus=None)
    body['analysis']['loads'][0].update(magnitude=None)
    response=post(client,base,r,body);assert response.status_code==201,response.text
    result=response.json()['result']
    assert result['status']=='incomplete' and result['metrics'] is None
    assert result['normalized']['span_m'] is None and result['normalized']['e_pa'] is None


def test_axis_choice_changes_inertia_and_deflection_with_same_load(client):
    _,base,_,_,r,_=prepare(client)
    first=post(client,base,r).json();body=review(r);body['bending_axis']='y'
    response=post(client,base,r,body);assert response.status_code==201,response.text
    second=response.json();a=first['result']['metrics'];b=second['result']['metrics']
    assert b['inertia_m4']==pytest.approx(3.387342477398636e-5,rel=1e-10)
    assert b['max_deflection_m']/a['max_deflection_m']==pytest.approx(a['inertia_m4']/b['inertia_m4'])
    assert second['ifc_profile_snapshot']['bending_axis']=='y'


def test_unsupported_oblique_saved_as_gap_and_cannot_be_handed_off(client):
    _,base,_,_,r,_=prepare(client,changed=lambda d,e,s:setattr(s.ExtrudedDirection,'DirectionRatios',(1.,0.,1.)))
    assert r['status']=='unsupported' and r['result']['section_profile'] is None
    assert post(client,base,r).status_code==409


def test_project_change_invalidates_source_and_analysis(client):
    pid,base,_,_,r,_=prepare(client);calculation=post(client,base,r).json()
    store=client.app.state.domain.store;project=store.get('project',pid);revision=project['revision']
    project['name']='New declared scope';project.pop('revision');store.put('project',project,expected=revision)
    assert client.get(base+'/beam-analyses/'+calculation['engineering_id']).json()['result'] is None
    assert post(client,base,r).status_code==409


def test_cross_project_ownership_anonymous_csrf(client):
    _,base,_,cad,r,_=prepare(client);pid2=create_project(client)['project_id']
    bad=client.post(f'/api/projects/{pid2}/ifc-beam-profiles',json={'cad_id':cad['cad_id'],'product_id':r['result']['product_id']})
    assert bad.status_code==409
    csrf=client.headers.pop('X-CSRF-Token')
    try:assert post(client,base,r).status_code==403
    finally:client.headers['X-CSRF-Token']=csrf
    with TestClient(client.app) as other:
        assert other.get(base+'/ifc-beam-profiles/'+r['beamprofile_id']).status_code==401
        login=other.post('/api/auth/register',json={'username':'other_ifc_owner','display_name':'Other test','password':'Other-test-password-2026'}).json()
        other.headers['X-CSRF-Token']=login['csrf_token']
        assert other.get(base+'/ifc-beam-profiles/'+r['beamprofile_id']).status_code==404


def test_write_time_profile_change_prevents_persist(client,monkeypatch):
    pid,base,_,_,r,_=prepare(client)
    import backend.ifc_beam_handoff as module
    real=module.validate_snapshot
    def change(domain,pid,snapshot):
        _,path=domain.file_record(pid,snapshot['file_snapshot']['file_id']);path.write_bytes(path.read_bytes()+b' changed-before-write')
        return real(domain,pid,snapshot)
    monkeypatch.setattr(module,'validate_snapshot',change)
    response=post(client,base,r)
    assert response.status_code==409,response.text
    assert client.app.state.domain.store.list('engineering',pid)==[]
