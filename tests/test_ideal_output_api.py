import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from backend.ideal_loads import diagnostic_model, HourlyEvidenceError, VARIABLES
from test_api import create_project
from test_cad import upload


def source():
    return json.loads((Path(__file__).parents[1]/'fixtures/test/native_ideal_loads_projection.json').read_text())['model_idf'].encode()


def prepare(client):
    pid=create_project(client)['project_id'];raw=source();fid=upload(client,pid,'moist-reference.idf',raw)
    base=f'/api/projects/{pid}/files/{fid}'
    return pid,raw,base,base+'/ideal-load-output.idf?expected_source_hash='+hashlib.sha256(raw).hexdigest()


def test_download_keeps_original_and_is_not_an_automatic_import(client):
    pid,raw,base,url=prepare(client);before=client.app.state.domain.store.list('file',pid)
    r=client.get(url);assert r.status_code==200,r.text
    assert r.content.startswith(raw) and client.get(base).content==raw
    assert r.headers['x-vra-source-sha256']==hashlib.sha256(raw).hexdigest()
    assert r.headers['x-vra-derivative-sha256']==hashlib.sha256(r.content).hexdigest()
    assert r.headers['x-vra-added-output-requests']=='0'
    assert client.app.state.domain.store.list('file',pid)==before
    assert client.app.state.domain.store.list('evidence',pid)==[]
    assert r.headers['cache-control']=='no-store'


def test_missing_outputs_are_appended_without_physical_model_edits():
    raw=b'\n'.join(line for line in source().splitlines() if not line.startswith(b'Output:Variable,'))
    result,count=diagnostic_model(raw)
    assert result[:len(raw)]==raw and count==len(VARIABLES)
    assert result.count(b'Output:Variable,')==len(VARIABLES)
    assert result.count(b'ZoneHVAC:IdealLoadsAirSystem,')==raw.count(b'ZoneHVAC:IdealLoadsAirSystem,')


@pytest.mark.parametrize('change',[
    lambda s:s.replace('Version,9.0','Version,9.6'),
    lambda s:s.replace('Output:SQLite,SimpleAndTabular','Output:SQLite,Simple'),
    lambda s:s.replace('Output:Variable,*,Zone Ideal Loads Zone Total Cooling Rate,Hourly','Output:Variable,IDEAL,Zone Ideal Loads Zone Total Cooling Rate,Hourly'),
    lambda s:s.replace('Zone Ideal Loads Zone Total Cooling Rate,Hourly','Zone Ideal Loads Zone Total Cooling Rate,Hourly,Conditional'),
])
def test_conflicting_request_is_not_silently_replaced(change):
    with pytest.raises(HourlyEvidenceError):diagnostic_model(change(source().decode()).encode())


def test_bad_hash_and_wrong_project_rejected(client):
    _,_,base,url=prepare(client)
    assert client.get(base+'/ideal-load-output.idf?expected_source_hash='+'0'*64).status_code==409
    assert client.get(base+'/ideal-load-output.idf').status_code==422
    pid2=create_project(client)['project_id'];assert client.get(url.replace(base.split('/')[3],pid2)).status_code==409


def test_anonymous_and_other_account_cannot_download(client):
    _,_,_,url=prepare(client)
    with TestClient(client.app) as other:
        assert other.get(url).status_code==401
        other.post('/api/auth/register',json={'username':'other_ideal_owner','display_name':'Isolated other','password':'Isolated-other-2026'})
        assert other.get(url).status_code==404


def test_source_mutation_between_checks_rejected(client,monkeypatch):
    _,_,_,url=prepare(client)
    import backend.ideal_loads as module
    real=module.model_systems
    def changed(path):
        result=real(path);path.write_bytes(path.read_bytes()+b'\n! changed');return result
    monkeypatch.setattr(module,'model_systems',changed)
    assert client.get(url).status_code==409
