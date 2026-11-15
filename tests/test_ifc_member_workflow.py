import pytest

from test_api import create_project
from test_cad import upload
from test_ifc_member_quantities import member
from test_material_scenarios import payload


def test_member_real_api_to_cost_carbon_then_source_withdrawal(client,tmp_path):
    _,_,element,_,path=member(tmp_path,'IfcColumn')
    pid=create_project(client)['project_id'];base='/api/projects/'+pid
    fid=upload(client,pid,'column.ifc',path.read_bytes())
    response=client.post(base+'/cad-inspections',json={'file_id':fid})
    assert response.status_code==201,response.text
    cad=response.json()
    request={'cad_id':cad['cad_id'],'product_id':element.id()}
    response=client.post(base+'/ifc-layer-takeoffs',json=request)
    assert response.status_code==201,response.text
    takeoff=response.json()
    assert takeoff['status']=='measured',takeoff
    assert takeoff['result']['total_layer_envelope_m3']==pytest.approx(22,abs=1e-8)
    ev=client.post(base+'/evidence',json={'type':'manual_input','name':'Explicit material assumptions',
        'source_locator':'Synthetic conditions','authority':'QA','permission':'Test only','acquisition_method':'Manual test',
        'responsible_person':'QA','status':'ASSUMED'}).json()
    body=payload(takeoff)
    body['functional_scope']='Same selected column body, declared material assumptions only'
    for alt in body['alternatives']:alt['layers'][0]['evidence_ids']=[ev['evidence_id']]
    response=client.post(base+'/material-scenarios',json=body)
    assert response.status_code==201,response.text
    scenario=response.json()
    assert scenario['status']=='calculated'
    # Independent frozen net geometry 22m3, declared fraction .5, waste .1,
    # density1000kg/m3, price100USD/t, factor2kgCO2e/kg ->1210USD/24200kgCO2e.
    first=scenario['result']['alternatives'][0]
    assert first['cost']['material_total']=='1210.00'
    assert first['carbon']['boundary_total_kgco2e']==pytest.approx(24200)
    assert scenario['result']['issued_credits_t'] is None
    report=client.get(base+'/ifc-layer-takeoffs/'+takeoff['takeoff_id']+'/report.html')
    assert report.status_code==200 and '不是实际分层' in report.text and '—' in report.text
    assert '&lt;not measured&gt;' in report.text
    other=create_project(client)['project_id']
    assert client.post('/api/projects/'+other+'/ifc-layer-takeoffs',json=request).status_code==409
    assert client.post(base+'/ifc-layer-takeoffs',json=request,headers={'X-CSRF-Token':''}).status_code==403
    client.patch(base+'/evidence/'+ev['evidence_id'],json={'expected_revision':1,'review_state':'rejected',
        'responsible_person':'QA','review_note':'Withdraw test material assumptions'})
    current=client.get(base+'/material-scenarios/'+scenario['scenario_id']).json()
    assert current['status']=='stale' and current['result'] is None
    _,source=client.app.state.domain.file_record(pid,fid)
    source.write_bytes(b'corrupt source')
    current=client.get(base+'/ifc-layer-takeoffs/'+takeoff['takeoff_id']).json()
    assert current['status']=='stale' and current['result'] is None
    assert client.app.state.domain.store.get('takeoff',takeoff['takeoff_id'])['result']==takeoff['result']
    client.cookies.clear()
    assert client.get(base+'/ifc-layer-takeoffs/'+takeoff['takeoff_id']+'/report.html').status_code==401
