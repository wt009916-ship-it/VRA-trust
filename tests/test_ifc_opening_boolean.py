"""Independent full-coverage opening regression through the isolated API."""
import hashlib
import pytest
from test_api import create_project
from test_cad import upload
from test_ifc_measurements import make_box

@pytest.mark.parametrize('prefix',[None,'MILLI'])
@pytest.mark.parametrize('full',[False,True])
def test_opening_never_returns_gross_fallback(client,prefix,full):
    doc,project,wall=make_box(prefix,opening=True)
    factor=1000. if prefix=='MILLI' else 1.
    angle=doc.create_entity('IfcSIUnit',UnitType='PLANEANGLEUNIT',Name='RADIAN')
    project.UnitsInContext.Units=list(project.UnitsInContext.Units)+[angle]
    for axis in doc.by_type('IfcAxis2Placement3D'):
        if axis.Axis is None:axis.Axis=doc.create_entity('IfcDirection',DirectionRatios=(0.,0.,1.))
        if axis.RefDirection is None:axis.RefDirection=doc.create_entity('IfcDirection',DirectionRatios=(1.,0.,0.))
    if full:
        solid=doc.by_type('IfcOpeningElement')[0].Representation.Representations[0].Items[0]
        solid.SweptArea.XDim=4.*factor
        solid.SweptArea.YDim=4.*factor
        solid.Depth=6.*factor
        solid.Position.Location.Coordinates=(0.,0.,-factor)
    raw=doc.to_string().encode();pid=create_project(client)['project_id']
    fid=upload(client,pid,'independent-opening.ifc',raw)
    route=f'/api/projects/{pid}/cad-inspections'
    response=client.post(route,json={'file_id':fid})
    assert response.status_code==201,response.text
    record=response.json();geometry=record['result']['ifc_geometry']
    assert geometry['settings']['boolean-attempt-2d'] is False
    host=next(r for r in geometry['objects'] if r['id']==wall.id())
    if full:
        # Mathematical net is zero. Empty mesh remains unknown, never invented zero.
        assert host['volume_m3'] is None
        assert host['mesh_status']=='empty_mesh'
        assert host['status']=='partial_mesh'
    else:
        assert host['volume_m3']==pytest.approx(24.-.5*1.*4.,abs=1e-9)
    assert client.get(route+'/'+record['cad_id']).json()['result']==record['result']
    original=client.get(f'/api/projects/{pid}/files/{fid}')
    assert original.status_code==200
    assert hashlib.sha256(original.content).hexdigest()==hashlib.sha256(raw).hexdigest()

@pytest.mark.parametrize('kind',['duplicate','multiple_hosts','orphan'])
def test_ambiguous_opening_relationships_block_geometry(client,kind):
    doc,_,wall=make_box(opening=True)
    opening=doc.by_type('IfcOpeningElement')[0]
    if kind=='orphan':
        doc.remove(doc.by_type('IfcRelVoidsElement')[0])
    else:
        import ifcopenshell
        host=wall
        if kind=='multiple_hosts':
            host=doc.create_entity('IfcWall',GlobalId=ifcopenshell.guid.new(),
                ObjectPlacement=wall.ObjectPlacement,Representation=wall.Representation)
        doc.create_entity('IfcRelVoidsElement',GlobalId=ifcopenshell.guid.new(),
            RelatingBuildingElement=host,RelatedOpeningElement=opening)
    pid=create_project(client)['project_id']
    raw=doc.to_string().encode()
    fid=upload(client,pid,'ambiguous-openings.ifc',raw)
    response=client.post(f'/api/projects/{pid}/cad-inspections',json={'file_id':fid})
    assert response.status_code==201,response.text
    rows=response.json()['result']['ifc_geometry']['objects']
    affected=[r for r in rows if kind!='orphan' or r['id']==opening.id()]
    expected={'duplicate':'duplicate_void_relationship','multiple_hosts':'multiple_hosts_for_opening','orphan':'missing_void_relationship'}[kind]
    assert affected
    for row in affected:
        assert row['status']=='ambiguous_opening_relationships'
        assert row['volume_m3'] is None and row['surface_area_m2'] is None
        assert expected in row['opening_relationships']['issues']
