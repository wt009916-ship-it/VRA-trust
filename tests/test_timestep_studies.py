import copy
import json
from pathlib import Path
import sqlite3
import pytest
from backend import core,timestep_check as check
from backend.timestep_studies import StudyInput,Studies
from test_api import create_project
from test_cad import upload

POLICY={'temperature_absolute_K':.01,'load_absolute_W':1.,'load_relative_pct':1.,'near_zero_W':1.}

@pytest.fixture
def native(tmp_path):
    records=json.loads((Path(__file__).parents[1]/'fixtures/test/native_timestep_projection.json').read_text())['cases'];out=[]
    for i,r in enumerate(records):
        rd=tmp_path/str(i);(rd/'input').mkdir(parents=True);(rd/'output').mkdir();sql=rd/'output/eplusout.sql';model=rd/'input/model.idf';model.write_text(r['model_idf'])
        with sqlite3.connect(sql) as con:
            for table,data in r['tables'].items():
                con.execute('CREATE TABLE '+table+' ('+','.join('"'+x+'"' for x in data['columns'])+')');con.executemany('INSERT INTO '+table+' VALUES ('+','.join('?' for _ in data['columns'])+')',data['rows'])
        out.append((sql,model,rd))
    return out


def loaded(native):return [check.source(sql,model,False,1) for sql,model,_ in native]


def test_real_projection_three_steps_exceed_with_retained_first_failures(native):
    r=check.compare(loaded(native),POLICY);assert r['verdict']=='exceeds_declared_threshold' and r['hours']==24 and len(r['pairs'])==3
    expected={(6,12):.04150138135131698,(6,60):.07641337251140179,(12,60):.03491199116008481}
    for pair in r['pairs']:
        row=next(x for x in pair['results'] if x['metric']=='temperature_C');assert row['maximum_absolute_difference']==pytest.approx(expected[(pair['coarse_steps_per_hour'],pair['fine_steps_per_hour'])],abs=1e-12)
        assert row['hours_exceeding_threshold']>0
        assert all(x['energy_difference_kWh']==0 for x in pair['results'] if x['metric']!='temperature_C')


def test_sql_row_ids_are_not_calendar_identity(native):
    before=check.compare(loaded(native),POLICY)
    with sqlite3.connect(native[1][0]) as con:
        con.execute('UPDATE Time SET TimeIndex=TimeIndex+100000');con.execute('UPDATE ReportData SET TimeIndex=TimeIndex+100000')
    assert check.compare(loaded(native),POLICY)==before


@pytest.mark.parametrize('replace',[('Material:NoMass,R2,Smooth,.7','Material:NoMass,R2,Smooth,.8'),('AnalyticalSolution','EulerMethod'),('Zone,Box_1,0','Zone,Box_1,1'),('Until:08:00,8','Until:08:00,9')])
def test_other_physics_changes_rejected(native,replace):
    p=native[1][1];text=p.read_text();assert replace[0] in text;p.write_text(text.replace(*replace))
    with pytest.raises(core.ValidationError,match='beyond Timestep'):check.compare(loaded(native),POLICY)


@pytest.mark.parametrize('query',["UPDATE Time SET DST=1 WHERE Hour=5","DELETE FROM ReportData WHERE rowid=(SELECT MAX(rowid) FROM ReportData)","UPDATE ReportDataDictionary SET Units='kW' WHERE Units='W'","UPDATE Time SET Month=2,Day=29 WHERE Hour=5"])
def test_calendar_missing_hour_and_units_rejected(native,query):
    with sqlite3.connect(native[1][0]) as con:con.execute(query)
    with pytest.raises(core.ValidationError):check.compare(loaded(native),POLICY)


def test_ideal_request_cannot_fall_back_to_sensible(native):
    with pytest.raises(core.ValidationError,match='ideal outputs unavailable'):check.source(*native[0][:2],True,1)


def test_same_steps_are_not_independent_refinement(native):
    s=loaded(native)
    with pytest.raises(core.ValidationError,match='Duplicate timestep'):check.compare([s[0],s[0]],POLICY)


def test_changed_input_after_validation_rejects_numeric_output(native):
    s=loaded(native);native[0][1].write_text(native[0][1].read_text()+'! changed')
    with pytest.raises(core.ValidationError,match='Source changed'):check.compare(s,POLICY)


def test_annual_energy_cancellation_does_not_hide_hourly_difference():
    r=check.series_difference([0,100,0,100],[100,0,100,0],[{'hour':x} for x in range(4)],'load',POLICY)
    assert r['energy_difference_kWh']==0 and r['hours_exceeding_threshold']==4 and r['maximum_absolute_difference']==100 and r['peak_sample_offset_hours']==1
    assert r['relative_evaluable_hours']==2 and r['max_relative_pct']==100
    zero=check.series_difference([0,0],[0,0],[{},{}],'load',POLICY)
    assert zero['max_relative_pct'] is None and zero['hours_exceeding_threshold']==0


def test_only_timestep_number_changes_preserve_bom_comments_and_unicode():
    raw='\ufeffVersion,9.0; ! Timestep,12; 注释\r\n Timestep, 6 ;\r\nZone,原始;'.encode()
    new,receipt=check.derivative(raw,60)
    assert new==raw.replace(b'Timestep, 6 ;',b'Timestep, 60 ;') and receipt['from_steps_per_hour']==6
    assert check.model_identity(raw)['physical_fields_sha256']==check.model_identity(new)['physical_fields_sha256']


@pytest.mark.parametrize('raw',[b'Version,9.0;',b'Version,9.6;Timestep,6;',b'Version,9.0;Timestep,6;Timestep,12;',b'Version,9.0;Timestep,7;',b'Version,9.0;Timestep,6',b'Version,9.0;Timestep,6,Extra;'])
def test_ambiguous_source_rejected(raw):
    with pytest.raises(core.ValidationError):check.derivative(raw,60)


@pytest.mark.parametrize('steps',[True,7,0,61,6])
def test_invalid_or_unchanged_derivative_rejected(steps):
    with pytest.raises(core.ValidationError):check.derivative(b'Version,9.0;Timestep,6;',steps)


def body(ids):return {'name':'Reference sensitivity','purpose':'Declared reference threshold, not compliance','run_ids':ids,'include_ideal':False,'thresholds':dict(POLICY)}


@pytest.mark.parametrize('key,value',[('temperature_absolute_K',True),('load_absolute_W',-1),('near_zero_W',0),('load_relative_pct',float('nan'))])
def test_thresholds_are_finite_explicit_not_bools(key,value):
    b=body(['run_'+'a'*32,'run_'+'b'*32]);b['thresholds'][key]=value
    with pytest.raises(ValueError):StudyInput(**b)


def test_authenticated_derivative_and_original_preservation(client,native):
    pid=create_project(client)['project_id'];raw=native[0][1].read_bytes();fid=upload(client,pid,'source.idf',raw);base=f'/api/projects/{pid}/files/{fid}';url=base+'/timestep.idf?steps=60&expected_source_hash='+core.sha(native[0][1]);before=client.app.state.domain.store.list('file',pid)
    r=client.get(url);assert r.status_code==200,r.text
    assert check.model_identity(r.content)['steps_per_hour']==60 and client.get(base).content==raw
    assert client.app.state.domain.store.list('file',pid)==before
    assert client.get(url.replace('steps=60','steps=7')).status_code==409
    assert client.get(url.replace(core.sha(native[0][1]),'0'*64)).status_code==409
    from fastapi.testclient import TestClient
    with TestClient(client.app) as other:
        assert other.get(url).status_code==401
        other.post('/api/auth/register',json={'username':'other_timestep_owner','display_name':'Other','password':'Isolated-other-timestep-2026'})
        assert other.get(url).status_code==404


def test_study_protocol_and_invalidated_results(client,native,monkeypatch):
    # Protocol-only source seam. Actual run authentication/binding is covered by real HTTP verifier.
    pid=create_project(client)['project_id'];service=client.app.state.timestep_studies;ids=['run_'+str(i)*32 for i in range(1,4)]
    snapshots={rid:{'run_id':rid,'scheme_id':str(i),'model_sha256':core.sha(native[i][1]),'sql_sha256':core.sha(native[i][0]),'weather_sha256':'weather','engine_sha256':'engine','idd_sha256':'idd','code_sha256':'code'} for i,rid in enumerate(ids)}
    def source(project,rid):
        if project!=pid:raise core.ValidationError('wrong project')
        return copy.deepcopy(snapshots[rid]),native[ids.index(rid)][2]
    # The retained unit projection is a design day, whereas project runs select annual output.
    # Explicitly select its day only at this test seam; real HTTP uses full annual runs.
    native_source=check.source
    monkeypatch.setattr(check,'source',lambda sql,model,include_ideal:native_source(sql,model,include_ideal,1))
    monkeypatch.setattr(service,'run_source',source);route=f'/api/projects/{pid}/timestep-studies'
    response=client.post(route,json=body(ids));assert response.status_code==201,response.text;r=response.json();assert r['status']=='assessed_model_sensitivity' and r['summary']['verdict']=='exceeds_declared_threshold'
    assert client.get(route+'/'+r['timestep_id']+'/report.html').status_code==200
    snapshots[ids[0]]['sql_sha256']='changed'
    stale=client.get(route+'/'+r['timestep_id']).json();assert stale['status']=='stale' and stale['summary'] is None
    assert 'maximum_absolute_difference' not in client.get(route+'/'+r['timestep_id']+'/report.html').text
    headers=dict(client.headers);client.headers.pop('X-CSRF-Token')
    assert client.post(route,json=body(ids)).status_code==403
    client.headers.update(headers)
    service.lock.acquire()
    try:assert client.post(route,json=body(ids)).status_code==429
    finally:service.lock.release()


def test_other_project_run_rejected_before_reading_results(client,monkeypatch):
    pid=create_project(client)['project_id'];service=Studies(client.app.state.domain)
    monkeypatch.setattr(service.store,'job',lambda _: {'project_id':'project_'+'f'*32})
    monkeypatch.setattr(service.domain,'view',lambda _:pytest.fail('Foreign run must not be read'))
    with pytest.raises(core.ValidationError,match='another project'):service.run_source(pid,'run_'+'c'*32)