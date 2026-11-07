import copy

import pytest

from test_api import create_project
from test_cad import upload
from test_ifc_layer_quantities import layered_wall


def create_takeoff(client,tmp_path):
    doc,_,wall,_,_,path=layered_wall(tmp_path)
    pid=create_project(client)['project_id'];fid=upload(client,pid,'layers.ifc',path.read_bytes())
    cad=client.post(f'/api/projects/{pid}/cad-inspections',json={'file_id':fid}).json()
    response=client.post(f'/api/projects/{pid}/ifc-layer-takeoffs',json={'cad_id':cad['cad_id'],'product_id':wall.id()})
    assert response.status_code==201,response.text
    return pid,response.json()


def test_layer_api_persists_bound_result_and_report(client,tmp_path):
    pid,r=create_takeoff(client,tmp_path)
    assert r['status']=='measured'
    assert [x['envelope_volume_m3'] for x in r['result']['layers']]==pytest.approx([5.6,16.4])
    base=f"/api/projects/{pid}/ifc-layer-takeoffs/{r['takeoff_id']}"
    assert client.get(base).json()['hash']==r['hash']
    report=client.get(base+'/report.html')
    assert report.status_code==200 and '包络体积 m³' in report.text and '不是采购材料净量' in report.text
    client.cookies.clear()
    assert client.get(base).status_code==401
    assert client.get(base+'/report.html').status_code==401


def test_layer_api_withdraws_stale_values_without_rewriting_history(client,tmp_path,monkeypatch):
    pid,r=create_takeoff(client,tmp_path);service=client.app.state.layer_takeoffs
    stored=copy.deepcopy(service.store.get('takeoff',r['takeoff_id']))
    monkeypatch.setattr('backend.material_takeoff.calculator_version',lambda:'different-layer-rules')
    current=client.get(f"/api/projects/{pid}/ifc-layer-takeoffs/{r['takeoff_id']}").json()
    assert current['status']=='stale' and current['result'] is None
    assert service.store.get('takeoff',r['takeoff_id'])==stored
    assert '5.6' not in client.get(f"/api/projects/{pid}/ifc-layer-takeoffs/{r['takeoff_id']}/report.html").text


def test_layer_api_rejects_wrong_project_id_and_missing_csrf(client,tmp_path):
    pid,r=create_takeoff(client,tmp_path);other=create_project(client)['project_id']
    base=f'/api/projects/{other}/ifc-layer-takeoffs'
    response=client.post(base,json={'cad_id':r['cad_id'],'product_id':r['product_id']})
    assert response.status_code==409
    client.headers.pop('X-CSRF-Token')
    assert client.post(f'/api/projects/{pid}/ifc-layer-takeoffs',json={'cad_id':r['cad_id'],'product_id':r['product_id']}).status_code==403
