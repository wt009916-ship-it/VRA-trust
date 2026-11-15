import pytest

from test_api import create_project
from test_cad import upload
from test_ifc_composite_materials import composite
from test_material_scenarios import payload


def test_real_composite_api_keeps_distinct_quantities_in_cost_carbon_and_withdrawal(client,tmp_path):
    _,element,_,_,profiles,_,path=composite(tmp_path,'MILLI','one_sided_opening')
    pid=create_project(client)['project_id'];base='/api/projects/'+pid
    original=path.read_bytes();fid=upload(client,pid,'composite.ifc',original)
    response=client.post(base+'/cad-inspections',json={'file_id':fid})
    assert response.status_code==201,response.text
    request={'cad_id':response.json()['cad_id'],'product_id':element.id()}
    response=client.post(base+'/ifc-layer-takeoffs',json=request)
    assert response.status_code==201,response.text
    takeoff=response.json()
    assert takeoff['status']=='measured',takeoff
    assert [r['envelope_volume_m3'] for r in takeoff['result']['layers']]==pytest.approx([12,10],abs=1e-8)
    assert [r['layer_id'] for r in takeoff['result']['layers']]==[p.id() for p in profiles]
    evidence=client.post(base+'/evidence',json={'type':'manual_input','name':'Synthetic material assumptions',
        'source_locator':'Independent rectangular reference','authority':'QA','permission':'Test only',
        'acquisition_method':'Manual','responsible_person':'QA','status':'ASSUMED'}).json()
    body=payload(takeoff);body['functional_scope']='Same explicitly partitioned synthetic composite body'
    for alt in body['alternatives']:
        for row in alt['layers']:row['evidence_ids']=[evidence['evidence_id']]
        alt['layers'][1]['quote']['unit_price']*=2
        alt['layers'][1]['factor']['value']*=1.5
    response=client.post(base+'/material-scenarios',json=body)
    assert response.status_code==201,response.text
    scenario=response.json();assert scenario['status']=='calculated'
    # Independent Decimal reference: [12,10]*.5*1.1*1000 -> [6600,5500]kg.
    # [100,200]USD/t ->1760USD; [2,3]kgCO2e/kg ->29700kgCO2e.
    first,second=scenario['result']['alternatives']
    assert first['cost']['material_total']=='1760.00'
    assert first['carbon']['boundary_total_kgco2e']==pytest.approx(29700)
    assert second['cost']['material_total']=='1408.00'
    assert second['carbon']['boundary_total_kgco2e']==pytest.approx(22275)
    assert scenario['result']['issued_credits_t'] is None
    report=client.get(base+'/ifc-layer-takeoffs/'+takeoff['takeoff_id']+'/report.html')
    assert report.status_code==200 and '原材料轮廓实体' in report.text and '&lt;declared&gt;' in report.text
    assert client.get(base+'/files/'+fid).content==original
    other=create_project(client)['project_id']
    assert client.post('/api/projects/'+other+'/ifc-layer-takeoffs',json=request).status_code==409
    assert client.post(base+'/ifc-layer-takeoffs',json=request,headers={'X-CSRF-Token':''}).status_code==403
    client.patch(base+'/evidence/'+evidence['evidence_id'],json={'expected_revision':1,'review_state':'rejected',
        'responsible_person':'QA','review_note':'Withdraw declared factors'})
    current=client.get(base+'/material-scenarios/'+scenario['scenario_id']).json()
    assert current['status']=='stale' and current['result'] is None
    _,source=client.app.state.domain.file_record(pid,fid);source.write_bytes(b'broken isolated original')
    current=client.get(base+'/ifc-layer-takeoffs/'+takeoff['takeoff_id']).json()
    assert current['status']=='stale' and current['result'] is None
    assert client.app.state.domain.store.get('takeoff',takeoff['takeoff_id'])['result']==takeoff['result']
    client.cookies.clear()
    assert client.get(base+'/ifc-layer-takeoffs/'+takeoff['takeoff_id']+'/report.html').status_code==401
