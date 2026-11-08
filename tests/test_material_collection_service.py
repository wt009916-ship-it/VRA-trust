import copy
import pytest
from test_ifc_material_collection import collection_model
from test_ifc_union import prepare
from test_api import create_project


def test_collection_api_source_report_access_and_invalidation(client,tmp_path):
    doc,products,_=collection_model(tmp_path)
    pid,base,fid,inspection,content=prepare(client,doc)
    request={'cad_id':inspection['cad_id'],'product_ids':[p.id() for p in products]}
    response=client.post(base+'/ifc-material-collections',json=request)
    assert response.status_code==201,response.text
    record=response.json();assert record['status']=='measured'
    assert record['result']['union_envelope_m3']==pytest.approx(36)
    assert record['result']['same_material_overlap_deduction_m3']==pytest.approx(12)
    path=base+'/ifc-material-collections/'+record['materialset_id']
    assert client.get(path).json()['hash']==record['hash']
    assert client.get(base+'/ifc-material-collections').json()[0]['materialset_id']==record['materialset_id']
    assert '去重包络 m³' in client.get(path+'/report.html').text
    assert client.get(base+'/files/'+fid).content==content
    other=create_project(client)['project_id']
    assert client.get(f'/api/projects/{other}/ifc-material-collections/'+record['materialset_id']).status_code==409
    assert client.post(f'/api/projects/{other}/ifc-material-collections',json=request).status_code==409
    store=client.app.state.material_collections.store
    saved=copy.deepcopy(store.get('materialset',record['materialset_id']))
    _,original=client.app.state.domain.file_record(pid,fid);original.write_bytes(b'isolated deliberately corrupted copy')
    current=client.get(path).json()
    assert current['status']=='stale' and current['result'] is None
    assert '去重包络 m³' not in client.get(path+'/report.html').text
    assert store.get('materialset',record['materialset_id'])==saved
    assert client.post(base+'/ifc-material-collections',json=request).status_code==409
    client.headers.pop('X-CSRF-Token')
    assert client.post(base+'/ifc-material-collections',json=request).status_code==403
    client.cookies.clear()
    assert client.get(path).status_code==401
    assert client.get(path+'/report.html').status_code==401


def test_collection_api_persists_unresolved_material_conflict_without_numbers(client,tmp_path):
    doc,products,_=collection_model(tmp_path,shift=(0.,1.,0.))
    _,base,_,inspection,_=prepare(client,doc)
    response=client.post(base+'/ifc-material-collections',json={'cad_id':inspection['cad_id'],'product_ids':[p.id() for p in products]})
    assert response.status_code==201,response.text
    record=response.json()
    assert record['status']=='unavailable'
    assert record['result']['reason']=='cross_material_overlap_ownership_unresolved'
    assert record['result']['materials']==[] and record['result']['union_envelope_m3'] is None
    assert '数量 —' in client.get(base+'/ifc-material-collections/'+record['materialset_id']+'/report.html').text
    bad={'cad_id':inspection['cad_id'],'product_ids':[p.id() for p in products]*2}
    assert client.post(base+'/ifc-material-collections',json=bad).status_code==422
    bad['product_ids']=list(range(1,18))
    assert client.post(base+'/ifc-material-collections',json=bad).status_code==422
