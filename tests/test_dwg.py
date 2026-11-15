"""Application gates with stub conversion; actual native corpus lives in validation."""
from contextlib import contextmanager
import json
import pytest
from backend import core, dwg_runtime, backup
from test_api import create_project
from test_cad import upload, dxf_bytes


@pytest.fixture
def converted(client,monkeypatch,tmp_path):
    path=tmp_path/'output.dxf';path.write_bytes(dxf_bytes())
    result=tmp_path/'parsed';result.mkdir()
    (result/'result.json').write_text(json.dumps({'format':'DXF','counts':{'LINE':1},'objects':[], 'length_scale_to_m':.001}))
    monkeypatch.setattr(dwg_runtime,'current',lambda:'runtime-v1')
    @contextmanager
    def convert(source):
        yield path,{'engine':'ACadSharp 3.8.35','runtime_hash':'runtime-v1','source_sha256':core.sha(source),
                    'notifications':[{'phase':'write','type':'NotImplemented','message':'Unknown object <script>'}],
                    'coverage':'partial_not_lossless'}
    @contextmanager
    def parse(*args,**kwargs):
        yield {'work':result,'resource_limits':{'test_stub':True}}
    monkeypatch.setattr(dwg_runtime,'convert',convert)
    monkeypatch.setattr('backend.parser_runtime.run',parse)
    pid=create_project(client)['project_id']
    fid=upload(client,pid,'original.dwg',b'AC1015-independent-test')
    base=f'/api/projects/{pid}/cad-inspections'
    return pid,fid,base


def create(client,converted):
    pid,fid,base=converted
    r=client.post(base,json={'file_id':fid});assert r.status_code==201,r.text
    return r.json()


def test_original_preserved_warnings_retained_and_derived_download(client,converted):
    obj=create(client,converted);pid,fid,base=converted
    assert obj['source']['file_id']==fid and obj['status']=='parsed'
    assert obj['conversion']['coverage']=='partial_not_lossless'
    assert obj['conversion']['notifications'][0]['type']=='NotImplemented'
    output=client.get(base+'/'+obj['cad_id']+'/converted.dxf')
    assert output.status_code==200
    import hashlib
    assert hashlib.sha256(output.content).hexdigest()==obj['derivative']['sha256']
    original=client.get(f'/api/projects/{pid}/files/{fid}')
    assert original.content==b'AC1015-independent-test'


@pytest.mark.parametrize('mutation,reason',[('source','source_unavailable'),('derivative','converted_file_changed'),('missing','converted_file_unavailable'),('runtime','converter_changed'),('unavailable','converter_unavailable')])
def test_current_gate_withdraws_result_and_download(client,converted,monkeypatch,mutation,reason):
    obj=create(client,converted);pid,_,base=converted;root=client.app.state.domain.store.root
    if mutation=='source':(root/obj['source']['path']).write_bytes(b'changed')
    elif mutation=='derivative':(root/obj['derivative']['path']).write_bytes(b'changed')
    elif mutation=='missing':(root/obj['derivative']['path']).unlink()
    else:monkeypatch.setattr(dwg_runtime,'current',lambda:None if mutation=='unavailable' else 'runtime-v2')
    view=client.get(base+'/'+obj['cad_id']).json()
    assert view['status']=='stale' and view['result'] is None and reason in view['stale_reasons']
    assert client.get(base+'/'+obj['cad_id']+'/converted.dxf').status_code==409
    states=client.post(f'/api/projects/{pid}/cad-current-states',json={'cad_ids':[obj['cad_id']]}).json()
    assert states['states'][0]['status']=='stale'


def test_strict_parser_rejection_leaves_no_success_or_artifact(client,converted,monkeypatch):
    def reject(*a,**kw):raise core.ValidationError('DXF requires repair')
    monkeypatch.setattr('backend.parser_runtime.run',reject)
    _,fid,base=converted
    assert client.post(base,json={'file_id':fid}).status_code==409
    assert client.get(base).json()==[]
    assert not (client.app.state.domain.store.root/'conversions').exists()


def test_conversion_failure_releases_slot(client,converted,monkeypatch):
    def reject(*a,**kw):raise core.ValidationError('timeout')
    monkeypatch.setattr(dwg_runtime,'convert',reject)
    _,fid,base=converted
    for _ in range(2):assert client.post(base,json={'file_id':fid}).json()['detail']=='timeout'


def test_download_ownership_and_csrf(client,converted):
    obj=create(client,converted);pid,fid,base=converted
    other=create_project(client)['project_id']
    assert client.get(f'/api/projects/{other}/cad-inspections/{obj["cad_id"]}/converted.dxf').status_code==409
    assert client.post(f'/api/projects/{other}/cad-inspections',json={'file_id':fid}).status_code==409
    csrf=client.headers.pop('X-CSRF-Token')
    assert client.post(base,json={'file_id':fid}).status_code==403
    client.headers['X-CSRF-Token']=csrf
    client.cookies.clear()
    assert client.get(base+'/'+obj['cad_id']+'/converted.dxf').status_code==401
    registered=client.post('/api/auth/register',json={'username':'dwg_second_owner','display_name':'Second isolated user','password':'Isolated-test-only-password-2026'})
    assert registered.status_code==200
    assert client.get(base+'/'+obj['cad_id']+'/converted.dxf').status_code==404
    client.cookies.clear()
    assert client.get(f'/api/projects/{pid}/dwg-capability').status_code==401


def test_backup_checks_registered_derivative(client,converted):
    obj=create(client,converted);store=client.app.state.domain.store
    entries=backup.inventory(store.root)
    with backup.database(store.root/'vra.sqlite3') as con:
        backup.check_database(con,entries,lambda n:core.read_json(store.root/n))
        del entries[obj['derivative']['path']]
        with pytest.raises(ValueError,match='DWG derivative'):backup.check_database(con,entries,lambda n:core.read_json(store.root/n))


def test_unconfigured_converter_does_not_advertise_support(client,monkeypatch):
    monkeypatch.delenv('VRA_DWG_RUNTIME',raising=False)
    pid=create_project(client)['project_id'];fid=upload(client,pid,'source.dwg',b'AC1015')
    assert client.get(f'/api/projects/{pid}/dwg-capability').json()['available'] is False
    response=client.post(f'/api/projects/{pid}/cad-inspections',json={'file_id':fid})
    assert response.status_code==409 and 'unavailable' in response.json()['detail']


@pytest.mark.parametrize('rows',[
    [],[{'phase':'done','entities':True}],[{'phase':'read','type':'Error','message':'bad'}],
    [{'phase':'done','entities':1},{'phase':'done','entities':1}],
    [{'phase':'read','type':'Unexpected','message':'bad'},{'phase':'done','entities':1}],
    [{'phase':'done','entities':1},{'phase':'read','type':'Warning','message':'late'}],
])
def test_invalid_native_diagnostics_refused(tmp_path,rows):
    path=tmp_path/'stdout.log';path.write_text('\n'.join(json.dumps(r) for r in rows))
    with pytest.raises((ValueError,core.ValidationError)):dwg_runtime.notifications(path)
