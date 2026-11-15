"""Independent IDF field and immutable application-workflow checks; no engine mock claim."""
import copy
from decimal import Decimal
import hashlib
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from backend import core, idf_retrofit
from backend.retrofit_models import Assignment, Properties, ModelPlan, Retrofits
from backend.thermal import Assembly, calculate
from test_api import create_project
from test_thermal import body as thermal_input


RAW=('\ufeff! 中文原件; preserve punctuation, comments and CRLF\r\nVersion,9.0;\r\n'
     'Material,OldLayer,Rough,.1,.5,1000,800,.9,.7,.7;\r\n'
     'Construction,OldConstruction,OldLayer;\r\n'
     'BuildingSurface:Detailed,South,Wall, OldConstruction ! only this reference changes\r\n'
     ',Zone,Outdoors,,SunExposed,WindExposed,.5,4,0,0,0,1,0,0,1,0,1,0,0,1;\r\n'
     'BuildingSurface:Detailed,North,Wall,OldConstruction,Zone,Outdoors,,SunExposed,WindExposed,.5,4,0,1,0,0,1,1,1,1,1,1,1,0;\r\n'
     'Schedule:Constant,Keep Me,Any Number,1;\r\n').encode('utf-8')


def properties(**overrides):
    return dict(density_kg_m3=1200.,specific_heat_j_kg_k=900.,roughness='MediumRough',
        thermal_absorptance=.9,solar_absorptance=.65,visible_absorptance=.6,
        property_source='Explicit independent synthetic material properties',**overrides)


def assignment():
    return Assignment(thermal_id='thermal_'+'a'*32,surface_names=['south'],layer_order='inside_to_outside',
                      properties=[properties(),properties()])


def thermal_record():
    b=thermal_input();b['layers'][1]['correction_factor']=1.25
    return {'thermal_id':'thermal_'+'a'*32,'result':calculate(Assembly(**b))}


def test_only_selected_token_changes_preserving_original_utf8_comments_and_objects():
    output,trace=idf_retrofit.derive(RAW,[assignment()],[thermal_record()],'abc')
    # Independent whole-byte oracle, not writer offsets or its own parser.
    expected=RAW.replace(b'South,Wall, OldConstruction',b'South,Wall, VRA_abc_C1',1)
    preserved,added=output.split(b'\n\n! VRA derived',1)
    assert preserved==expected
    assert b'North,Wall,OldConstruction' in preserved
    assert added.count(b'Material, ')==2 and added.count(b'Construction, ')==1
    assert b'Construction, VRA_abc_C1, VRA_abc_C1_L2, VRA_abc_C1_L1;' in added
    rows=[l.split(', ') for l in added.decode().splitlines() if l.startswith('Material, ')]
    assert [r[1] for r in rows]==['VRA_abc_C1_L2','VRA_abc_C1_L1']
    # cm/mm/mW units and conductivity correction; no Rsi/Rse material.
    assert float(rows[0][3])==.08 and float(rows[0][4])==.05
    assert float(rows[1][3])==.2 and float(rows[1][4])==.8
    resistance=sum(Decimal(r[3])/Decimal(r[4]) for r in rows)
    assert float(resistance)==pytest.approx(1.85,abs=1e-14)
    assert trace['source_sha256']==hashlib.sha256(RAW).hexdigest()
    assert trace['changed_reference_count']==1 and trace['added_object_count']==3


@pytest.mark.parametrize('extra,reason',[
    ('MaterialProperty:PhaseChange,OldLayer,0,20,1;','special_material_or_construction_properties'),
    ('SurfaceProperty:HeatTransferAlgorithm:Construction,Override,ConductionFiniteDifference,OldConstruction;','special_material_or_construction_properties'),
    ('SurfaceControl:MovableInsulation,Outside,South,OldLayer,Always;','movable_insulation'),
    ('EnergyManagementSystem:ConstructionIndexVariable,Handle,OldConstruction;','dynamic_construction_or_external_control'),
    ('EnergyManagementSystem:Actuator,Control,South,Surface,Construction State;','dynamic_construction_or_external_control'),
    ('ExternalInterface,FunctionalMockupUnitImport;','dynamic_construction_or_external_control')])
def test_dependent_controls_are_not_silently_bypassed(extra,reason):
    raw=RAW+extra.encode();catalog=idf_retrofit.inspect(raw)['catalog']
    assert reason in next(r for r in catalog if r['name']=='South')['reasons']
    with pytest.raises(core.ValidationError,match='unsupported'):
        idf_retrofit.derive(raw,[assignment()],[thermal_record()],'abc')


@pytest.mark.parametrize('raw',[b'',b'Version,24.1;',b'Version,9.0;Version,9.0;',b'Version,9.0;\0',
    b'Version,9.0;Material,"bad",x;',b'Version,9.0;#include x',b'Version,9.0;Material,bad',
    b'Version,9.0;Material,\xff;',RAW+b'Construction,oldconstruction,OldLayer;',
    RAW+b'BuildingSurface:Detailed,SOUTH,Wall,OldConstruction,Zone,Outdoors,,x,x,0,4;'])
def test_ambiguous_corrupt_or_duplicate_model_refused(raw):
    with pytest.raises(core.ValidationError):idf_retrofit.inspect(raw)


@pytest.mark.parametrize('field,value',[('density_kg_m3',0),('specific_heat_j_kg_k',99),('thermal_absorptance',1),
    ('solar_absorptance',-1),('visible_absorptance',True),('density_kg_m3','1200'),('roughness','Guess'),
    ('specific_heat_j_kg_k',float('nan')),('property_source','')])
def test_material_properties_require_explicit_valid_values(field,value):
    b=properties();b[field]=value
    with pytest.raises(ValidationError):Properties(**b)


def test_missing_extra_duplicate_layers_and_unsupported_surfaces_refused():
    a=assignment();a.properties=a.properties[:1]
    with pytest.raises(core.ValidationError):idf_retrofit.derive(RAW,[a],[thermal_record()],'abc')
    a=assignment();a.surface_names=['South','SOUTH']
    with pytest.raises(core.ValidationError):idf_retrofit.derive(RAW,[a],[thermal_record()],'abc')
    a=assignment();a.surface_names=['Absent']
    with pytest.raises(core.ValidationError):idf_retrofit.derive(RAW,[a],[thermal_record()],'abc')
    for boundary in [b'Ground',b'Adiabatic',b'Surface']:
        with pytest.raises(core.ValidationError):idf_retrofit.derive(RAW.replace(b'Outdoors',boundary),[assignment()],[thermal_record()],'abc')


def setup(client):
    pid=create_project(client)['project_id'];base='/api/projects/'+pid
    r=client.post(base+'/files',files={'file':('input.idf',RAW)});assert r.status_code==201,r.text
    file=r.json()
    r=client.post(base+'/evidence',json={'type':'idf','name':'Synthetic baseline','scheme_id':'baseline',
        'source_file':file['file_id'],'source_locator':'Controlled original','authority':'Independent test',
        'permission':'Synthetic test data','acquisition_method':'Unit test','responsible_person':'Tester','status':'IMPORTED'})
    assert r.status_code==201,r.text;ev=r.json()
    r=client.patch(base+'/evidence/'+ev['evidence_id'],json={'expected_revision':1,'review_state':'confirmed',
        'responsible_person':'Tester','review_note':'Synthetic reference only, no field validation'})
    assert r.status_code==200,r.text;ev=r.json()
    r=client.post(base+'/thermal',json=thermal_input());assert r.status_code==201,r.text;thermal=r.json()
    plan=dict(name='Explicit retrofit',source_evidence_id=ev['evidence_id'],scheme_id='R1',
        assignments=[{**assignment().model_dump(),'thermal_id':thermal['thermal_id']}],
        responsible_person='Tester',basis='Controlled reference material scenario, not as-built')
    return pid,base,file,ev,thermal,plan


def generate(client,base,plan):
    r=client.post(base+'/retrofit-previews',json=plan);assert r.status_code==200,r.text
    request={**plan,'expected_preview_hash':r.json()['preview_hash'],'acknowledge_scope':True}
    r=client.post(base+'/retrofits',json=request);assert r.status_code==201,r.text
    return r.json(),request


def test_preview_generate_idempotency_pending_review_and_preserved_original(client):
    pid,base,file,ev,thermal,plan=setup(client)
    catalog=client.get(base+'/retrofit-models/'+ev['evidence_id']).json()
    assert len(catalog['surfaces'])==2
    record,request=generate(client,base,plan);rid=record['retrofit_id']
    assert record['status']=='generated' and record['evidence_review']['review_state']=='pending'
    assert record['evidence_review']['status']=='ASSUMED'
    assert record['annual_saving_rate_pct'] is None and not record['simulation_executed']
    original=client.get(base+'/files/'+file['file_id']);assert original.content==RAW
    d=client.get(base+'/retrofits/'+rid+'/model.idf');assert d.status_code==200
    assert hashlib.sha256(d.content).hexdigest()==record['derived_file']['hash']
    assert client.post(base+'/retrofits',json=request).json()['retrofit_id']==rid
    assert len(client.app.state.domain.store.list('file',pid))==2
    assert not client.get(base+'/gate?scheme_id=R1').json()['can_simulate']
    assert '未经工程适用性认证' in client.get(base+'/retrofits/'+rid+'/report.html').text
    assert 'South' in client.get(base+'/retrofits/'+rid+'/report.html').text


@pytest.mark.parametrize('change',['source_review','source_bytes','thermal_integrity','derived_bytes','builder','project'])
def test_dependency_change_withdraws_model_report_and_new_simulation(client,monkeypatch,change):
    pid,base,file,ev,thermal,plan=setup(client);record,request=generate(client,base,plan)
    domain=client.app.state.domain;service=Retrofits(domain);rid=record['retrofit_id']
    if change=='source_review':
        r=client.patch(base+'/evidence/'+ev['evidence_id'],json={'expected_revision':ev['revision'],
            'review_state':'pending','responsible_person':'Tester','review_note':'Source review withdrawn for test'})
        assert r.status_code==200
    elif change in {'source_bytes','derived_bytes'}:
        fid=file['file_id'] if change=='source_bytes' else record['derived_file']['file_id']
        _,path=domain.file_record(pid,fid);path.write_bytes(path.read_bytes()+b'! tampered')
    elif change=='thermal_integrity':
        t=domain.store.get('thermal',thermal['thermal_id']);t['input']['name']='tampered'
        domain.store.put('thermal',t,t['revision'])
    elif change=='builder':monkeypatch.setattr('backend.retrofit_models.version',lambda:'changed')
    else:
        p=domain.store.get('project',pid);p['name']='Updated project';domain.store.put('project',p,p['revision'])
    view=client.get(base+'/retrofits/'+rid).json()
    assert view['status']=='stale' and view['changes'] is None and view['stale_reasons']
    assert client.get(base+'/retrofits/'+rid+'/model.idf').status_code==409
    assert '来源失效，变更结果已撤下' in client.get(base+'/retrofits/'+rid+'/report.html').text
    with pytest.raises(core.ValidationError):service.require_file_current(pid,record['derived_file']['file_id'])
    assert domain.store.get('retrofit',rid)['changes']==record['changes']


def test_changed_preview_conflict_and_transaction_failure_leave_no_derivative(client,monkeypatch):
    pid,base,file,ev,thermal,plan=setup(client)
    preview=client.post(base+'/retrofit-previews',json=plan).json()
    request={**plan,'expected_preview_hash':preview['preview_hash'],'acknowledge_scope':True}
    changed=copy.deepcopy(request);changed['assignments'][0]['properties'][0]['density_kg_m3']=800.
    assert client.post(base+'/retrofits',json=changed).status_code==409
    changed=copy.deepcopy(request);changed['acknowledge_scope']=False
    assert client.post(base+'/retrofits',json=changed).status_code==422
    store=client.app.state.domain.store;put=store.put_in
    def fail(con,kind,obj,expected=0):
        if kind=='retrofit':raise core.ValidationError('Injected storage failure after pending evidence insertion')
        return put(con,kind,obj,expected)
    monkeypatch.setattr(store,'put_in',fail)
    assert client.post(base+'/retrofits',json=request).status_code==409
    assert len(store.list('file',pid))==1 and len(store.list('evidence',pid))==1 and not store.list('retrofit',pid)
    assert len(list((store.root/'files').iterdir()))==1


def test_scheme_conflict_requires_explicit_rejection(client):
    pid,base,file,ev,thermal,plan=setup(client);first,_=generate(client,base,plan)
    plan['name']='Different scenario'
    preview=client.post(base+'/retrofit-previews',json=plan).json()
    req={**plan,'expected_preview_hash':preview['preview_hash'],'acknowledge_scope':True}
    assert client.post(base+'/retrofits',json=req).status_code==409
    e=first['evidence_review'];r=client.patch(base+'/evidence/'+e['evidence_id'],json={'expected_revision':1,
        'review_state':'rejected','responsible_person':'Tester','review_note':'Explicitly superseded test scenario'})
    assert r.status_code==200
    assert client.get(base+'/retrofits/'+first['retrofit_id']+'/model.idf').status_code==409
    assert client.post(base+'/retrofits',json=req).status_code==201


def test_cross_project_and_account_csrf_anonymous_boundaries(client):
    pid,base,file,ev,thermal,plan=setup(client);record,request=generate(client,base,plan)
    other=create_project(client)['project_id']
    assert client.post('/api/projects/'+other+'/retrofit-previews',json=plan).status_code==409
    assert client.get('/api/projects/'+other+'/retrofits/'+record['retrofit_id']).status_code==409
    csrf=client.headers.pop('X-CSRF-Token')
    assert client.post(base+'/retrofits',json=request).status_code==403
    client.headers['X-CSRF-Token']=csrf
    with TestClient(client.app) as outsider:
        route=base+'/retrofits/'+record['retrofit_id']+'/model.idf'
        assert outsider.get(route).status_code==401
        r=outsider.post('/api/auth/register',json={'username':'other_retrofit','display_name':'Other','password':'Test-only-long-pass-2026'})
        assert r.status_code==200
        assert outsider.get(route).status_code==404


def test_duplicate_casefold_surface_plan_refused():
    a=assignment().model_dump()
    with pytest.raises(ValidationError):
        ModelPlan(name='x',source_evidence_id='evidence_'+'a'*32,scheme_id='R1',assignments=[a,a],
                  responsible_person='test',basis='Independent test declaration')


def test_multiple_assignments_keep_independent_order_and_materials():
    a=assignment();b=assignment();b.surface_names=['North'];b.layer_order='outside_to_inside'
    output,trace=idf_retrofit.derive(RAW,[a,b],[thermal_record(),thermal_record()],'multi')
    assert b'South,Wall, VRA_multi_C1' in output and b'North,Wall,VRA_multi_C2' in output
    assert b'Construction, VRA_multi_C1, VRA_multi_C1_L2, VRA_multi_C1_L1;' in output
    assert b'Construction, VRA_multi_C2, VRA_multi_C2_L1, VRA_multi_C2_L2;' in output
    assert trace['changed_reference_count']==2 and trace['added_object_count']==6


def test_retrofit_comparison_rejects_unbound_jobs_before_any_result(client,monkeypatch):
    from backend.schema import ComparisonRequest
    pid,base,file,ev,thermal,plan=setup(client);record,_=generate(client,base,plan)
    domain=client.app.state.domain;service=Retrofits(domain)
    jobs={'run_'+'a'*32:{'project_id':pid,'scheme_id':'baseline','evidence_snapshot':{'idf':{'source_file':file['file_id']}}},
          'run_'+'b'*32:{'project_id':pid,'scheme_id':'R1','evidence_snapshot':{'idf':{'source_file':'file_'+'f'*32}}}}
    monkeypatch.setattr(domain.store,'job',lambda rid:jobs[rid])
    monkeypatch.setattr(domain,'compare',lambda ids:pytest.fail('Unbound run must not reach comparison'))
    with pytest.raises(core.ValidationError,match='exactly the bound'):
        service.compare(pid,record['retrofit_id'],ComparisonRequest(run_ids=list(jobs)))
