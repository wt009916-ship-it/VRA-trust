from pathlib import Path
s=Path('validation/ifc-union-20261107/probe_union_v1.py').read_text(encoding='utf-8')
model=s[s.index('def oracle('):s.index('cases=[')]
header='''"""Independent geometric gold and real isolated API acceptance for selected IFC union."""
import hashlib
import itertools
import math
from pathlib import Path
import pytest
import ifcopenshell
from backend import core
from backend.ifc_union import measure_union, validate_selection
from test_ifc_measurements import make_box
from test_api import create_project
from test_cad import upload

'''
tests='''

CASES = [
    ('overlap', [(0,0,0,2,3,4),(1,0,0,3,3,4)], 36.),
    ('contained', [(0,0,0,2,3,4),(.5,.5,.5,1,2,3)], 24.),
    ('same_shape', [(0,0,0,2,3,4)]*2, 24.),
    ('face_touch', [(0,0,0,2,3,4),(2,0,0,4,3,4)], 48.),
    ('separate', [(0,0,0,2,3,4),(4,0,0,6,3,4)], 48.),
    ('triple', [(0,0,0,2,3,4),(1,0,0,3,3,4),(1,1,1,4,4,5)], 60.),
]

@pytest.mark.parametrize('name,boxes,expected', CASES)
@pytest.mark.parametrize('angle,offset', [(0.,(0.,0.,0.)),(math.radians(37),(5e8,3e9,0.))])
def test_union_independent_geometry(tmp_path,name,boxes,expected,angle,offset):
    doc,products=model(boxes,angle,offset);path=tmp_path/(name+'.ifc');doc.write(str(path))
    before=hashlib.sha256(path.read_bytes()).hexdigest()
    value=measure_union(path,[p.id() for p in products])
    assert oracle(boxes)==pytest.approx(expected)
    assert value['status']=='measured', value
    assert value['union_volume_m3']==pytest.approx(expected,abs=1e-7)
    assert value['sum_operand_volume_m3']==pytest.approx(sum(math.prod(b[i+3]-b[i] for i in range(3)) for b in boxes))
    assert value['overlap_deduction_m3']==pytest.approx(value['sum_operand_volume_m3']-expected,abs=1e-7)
    assert hashlib.sha256(path.read_bytes()).hexdigest()==before

def test_edge_contact_does_not_bypass_output_topology(tmp_path):
    doc,products=model([(0,0,0,2,3,4),(2,3,0,4,6,4)]);p=tmp_path/'edge.ifc';doc.write(str(p))
    result=measure_union(p,[e.id() for e in products])
    assert result['reason']=='union_topology_unverified'
    assert result['union_volume_m3'] is result['overlap_deduction_m3'] is None

@pytest.mark.parametrize('ids', [[],[1],[True,2],[1,1],[-1,2],[1,2.0],['1',2],list(range(1,66)),[1,2147483648]])
def test_selection_strict_and_bounded(ids):
    with pytest.raises(ValueError):validate_selection(ids)

def prepare(client,doc):
    pid=create_project(client)['project_id'];base=f'/api/projects/{pid}'
    content=doc.to_string().encode();fid=upload(client,pid,'selected.ifc',content)
    response=client.post(base+'/cad-inspections',json={'file_id':fid})
    assert response.status_code==201,response.text
    return pid,base,fid,response.json(),content

@pytest.mark.parametrize('millimetres',[False,True])
def test_isolated_api_units_union_original_and_report(client,millimetres):
    factor=1000 if millimetres else 1
    boxes=[tuple(v*factor for v in b) for b in [(0,0,0,2,3,4),(1,0,0,3,3,4)]]
    doc,products=model(boxes)
    if millimetres:doc.by_type('IfcSIUnit')[0].Prefix='MILLI'
    pid,base,fid,inspection,content=prepare(client,doc)
    response=client.post(base+'/ifc-unions',json={'cad_id':inspection['cad_id'],'product_ids':[e.id() for e in products]})
    assert response.status_code==201,response.text
    record=response.json();result=record['result']
    assert record['status']=='measured',result
    assert result['union_volume_m3']==pytest.approx(36)
    assert result['sum_operand_volume_m3']==pytest.approx(48)
    assert result['overlap_deduction_m3']==pytest.approx(12)
    assert result['resource_limits']['enforced']
    path=base+'/ifc-unions/'+record['union_id']
    assert client.get(path).json()['hash']==record['hash']
    assert client.get(base+'/ifc-unions').json()[0]['union_id']==record['union_id']
    assert '36' in client.get(path+'/report.html').text
    assert client.get(base+'/files/'+fid).content==content
    other=create_project(client)['project_id']
    assert client.get(f'/api/projects/{other}/ifc-unions/'+record['union_id']).status_code==409
    assert client.post(f'/api/projects/{other}/ifc-unions',json={'cad_id':inspection['cad_id'],'product_ids':[e.id() for e in products]}).status_code==409
    _,original=client.app.state.domain.file_record(pid,fid);original.write_bytes(b'broken isolated source')
    assert client.get(path).json()['result'] is None
    assert '"union_volume_m3"' not in client.get(path+'/report.html').text
    assert client.post(base+'/ifc-unions',json={'cad_id':inspection['cad_id'],'product_ids':[e.id() for e in products]}).status_code==409

def test_opening_host_union_preserves_cut_and_counts_overlap_once(client):
    doc,_,wall=make_box(opening=True)
    second=doc.create_entity('IfcWall',GlobalId=ifcopenshell.guid.new(),Name='full overlapping host',
        ObjectPlacement=wall.ObjectPlacement,Representation=wall.Representation)
    _,base,_,inspection,_=prepare(client,doc)
    r=client.post(base+'/ifc-unions',json={'cad_id':inspection['cad_id'],'product_ids':[wall.id(),second.id()]})
    assert r.status_code==201,r.text
    values=r.json()['result']
    assert values['sum_operand_volume_m3']==pytest.approx(46)
    assert values['union_volume_m3']==pytest.approx(24)
    assert values['overlap_deduction_m3']==pytest.approx(22)

def test_reject_opening_and_unknown_entities_and_no_csrf(client):
    doc,_,wall=make_box(opening=True);hole=doc.by_type('IfcOpeningElement')[0]
    _,base,_,inspection,_=prepare(client,doc)
    body={'cad_id':inspection['cad_id'],'product_ids':[wall.id(),hole.id()]}
    assert client.post(base+'/ifc-unions',json=body).status_code==409
    body['product_ids']=[wall.id(),999999]
    assert client.post(base+'/ifc-unions',json=body).status_code==409
    body['product_ids']=[wall.id(),wall.id()]
    assert client.post(base+'/ifc-unions',json=body).status_code==422
    client.headers.pop('X-CSRF-Token')
    assert client.post(base+'/ifc-unions',json=body).status_code==403
    client.cookies.clear()
    assert client.get(base+'/ifc-unions').status_code==401
'''
Path('tests/test_ifc_union.py').write_text(header+model+tests,encoding='utf-8',newline='\n')
