import copy
import pytest
from test_ifc_material_collection import collection_model
from test_ifc_union import prepare
from test_collection_scenarios import five_stage_payload
from test_api import create_project


def setup_collection(client,tmp_path,conflict=False):
    doc,products,_=collection_model(tmp_path,shift=(0.,1.,0.) if conflict else (1.,0.,0.))
    pid,base,fid,inspection,content=prepare(client,doc)
    response=client.post(base+'/ifc-material-collections',json={'cad_id':inspection['cad_id'],'product_ids':[p.id() for p in products]})
    assert response.status_code==201,response.text
    return pid,base,fid,response.json(),content


def test_actual_ifc_to_collection_cost_carbon_report_and_stale_source(client,tmp_path,monkeypatch):
    pid,base,fid,source,content=setup_collection(client,tmp_path)
    body=five_stage_payload(source)
    response=client.post(base+'/collection-scenarios',json=body)
    assert response.status_code==201,response.text
    record=response.json();assert record['status']=='calculated'
    assert record['result']['alternatives'][0]['cost']['material_total']=='1980.00'
    assert record['result']['alternatives'][0]['carbon']['boundary_total_kgco2e']==pytest.approx(45702.5)
    assert record['materialset_hash']==source['hash'] and 'takeoff_id' not in record
    path=base+'/collection-scenarios/'+record['collectionscenario_id']
    assert client.get(path).json()['hash']==record['hash']
    assert client.get(base+'/collection-scenarios').json()[0]['collectionscenario_id']==record['collectionscenario_id']
    assert client.get(base+'/material-scenarios').json()==[]
    assert '来源材料实体 / 拟用材料' in client.get(path+'/report.html').text
    assert client.get(base+'/files/'+fid).content==content
    store=client.app.state.collection_scenarios.store
    historical=copy.deepcopy(store.get('collectionscenario',record['collectionscenario_id']))
    other=create_project(client)['project_id']
    assert client.get(f'/api/projects/{other}/collection-scenarios/'+record['collectionscenario_id']).status_code==409
    assert client.post(f'/api/projects/{other}/collection-scenarios',json=body).status_code==409
    with monkeypatch.context() as patch:
        patch.setattr('backend.material_scenarios.calculator_version',lambda:'changed-material-rule')
        current=client.get(path).json();assert current['status']=='stale' and current['result'] is None
    _,copyfile=client.app.state.domain.file_record(pid,fid);copyfile.write_bytes(b'corrupted isolated source')
    current=client.get(path).json();assert current['status']=='stale' and current['result'] is None
    assert '1980.00' not in client.get(path+'/report.html').text
    assert store.get('collectionscenario',record['collectionscenario_id'])==historical
    assert client.post(base+'/collection-scenarios',json=body).status_code==409
    client.headers.pop('X-CSRF-Token')
    assert client.post(base+'/collection-scenarios',json=body).status_code==403
    client.cookies.clear()
    assert client.get(path).status_code==401 and client.get(path+'/report.html').status_code==401


def test_conflicted_material_collection_cannot_become_cost_or_carbon(client,tmp_path):
    from test_collection_scenarios import reference
    _,base,_,source,_=setup_collection(client,tmp_path,conflict=True)
    valid,_=reference();body=five_stage_payload(valid);body['materialset_id']=source['materialset_id']
    response=client.post(base+'/collection-scenarios',json=body)
    assert response.status_code==409,response.text
    assert client.get(base+'/collection-scenarios').json()==[]
