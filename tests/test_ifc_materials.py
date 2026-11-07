"""Material source tests use actual IFC entities; amounts are intentionally not inferred."""
import hashlib

import ifcopenshell
import pytest

from backend.ifc_details import material_declarations, project_units
from test_ifc_measurements import make_box, result
from test_api import create_project
from test_cad import upload


def associate(doc, owner, material):
    return doc.create_entity('IfcRelAssociatesMaterial', GlobalId=ifcopenshell.guid.new(),
                             RelatedObjects=[owner], RelatingMaterial=material)


def layers(doc, values):
    items = [doc.create_entity('IfcMaterialLayer', Material=doc.create_entity('IfcMaterial', Name=name),
                              LayerThickness=value) for name, value in values]
    group = doc.create_entity('IfcMaterialLayerSet', MaterialLayers=items, LayerSetName='Declared assembly')
    return doc.create_entity('IfcMaterialLayerSetUsage', ForLayerSet=group, LayerSetDirection='AXIS2',
                             DirectionSense='POSITIVE', OffsetFromReferenceLine=-12.5), items


def assignment(wall, project):
    return material_declarations(wall, project_units(project))['material_assignment']


@pytest.mark.parametrize('schema', ['IFC2X3','IFC4'])
def test_instance_source_is_retained_without_name_based_quantity(schema):
    doc=ifcopenshell.file(schema=schema)
    wall=doc.create_entity('IfcWall',GlobalId=ifcopenshell.guid.new(),Name='Concrete 100m3')
    material=doc.create_entity('IfcMaterial',Name='<script>source only</script>')
    relation=associate(doc,wall,material)
    r=material_declarations(wall,{})['material_assignment']
    assert r['status']=='declared' and r['quantity_status']=='not_measured'
    row=r['associations'][0]
    assert row['relation_id']==relation.id() and row['owner_id']==wall.id()
    assert row['material']['name']==material.Name and row['material']['id']==material.id()
    assert row['scope']=='instance' and row['selection']=='effective_declaration'


def test_ordered_layers_keep_exact_source_and_convert_millimetres():
    doc,project,wall=make_box('MILLI');usage,items=layers(doc,[('Brick',92.),('Air',25.),('Insulation',50.)])
    associate(doc,wall,usage)
    r=assignment(wall,project)['associations'][0]['material']
    assert r['offset_raw']==-12.5 and r['direction']=='AXIS2'
    actual=r['layer_set']['layers']
    assert [x['id'] for x in actual]==[x.id() for x in items]
    assert [x['material']['name'] for x in actual]==['Brick','Air','Insulation']
    assert [x['thickness']['value_m'] for x in actual]==pytest.approx([.092,.025,.05])
    assert all(x['thickness']['unit_id']==project.UnitsInContext.Units[0].id() for x in actual)


@pytest.mark.parametrize('unit_mode', ['missing','duplicate'])
def test_layer_unit_gaps_keep_unknown_without_assuming_metres(unit_mode):
    doc,project,wall=make_box();usage,_=layers(doc,[('Board',16.)]);associate(doc,wall,usage)
    units={} if unit_mode=='missing' else {'LENGTHUNIT':list(project.UnitsInContext.Units)*2}
    layer=material_declarations(wall,units)['material_assignment']['associations'][0]['material']['layer_set']['layers'][0]
    assert layer['thickness']['raw']==16 and layer['thickness']['value_m'] is None
    assert layer['thickness']['status']==('missing_unit' if unit_mode=='missing' else 'conflicting_project_units')


def test_instance_override_keeps_type_source_and_duplicates_are_ambiguous():
    doc,project,wall=make_box()
    typ=doc.create_entity('IfcWallType',GlobalId=ifcopenshell.guid.new(),PredefinedType='STANDARD')
    doc.create_entity('IfcRelDefinesByType',GlobalId=ifcopenshell.guid.new(),RelatedObjects=[wall],RelatingType=typ)
    inherited=associate(doc,typ,doc.create_entity('IfcMaterial',Name='Type concrete'))
    assert assignment(wall,project)['associations'][0]['scope']=='type'
    direct=associate(doc,wall,doc.create_entity('IfcMaterial',Name='Instance masonry'))
    rows=assignment(wall,project)['associations']
    assert {r['relation_id']:r['selection'] for r in rows}=={inherited.id():'overridden_by_instance',direct.id():'effective_declaration'}
    associate(doc,wall,doc.create_entity('IfcMaterial',Name='Contradictory concrete'))
    r=assignment(wall,project)
    assert r['status']=='ambiguous'
    assert all(x['selection']=='ambiguous' for x in r['associations'] if x['scope']=='instance')


def test_material_list_has_no_invented_proportions():
    doc,project,wall=make_box()
    materials=[doc.create_entity('IfcMaterial',Name=name) for name in ['Steel','Concrete']]
    associate(doc,wall,doc.create_entity('IfcMaterialList',Materials=materials))
    r=assignment(wall,project)['associations'][0]['material']
    assert r['proportions_status']=='not_declared'
    assert [x['name'] for x in r['materials']]==['Steel','Concrete']
    assert all('quantity' not in x and 'fraction' not in x for x in r['materials'])


def test_missing_assignment_is_not_filled_from_wall_name():
    doc,project,wall=make_box();wall.Name='Solid steel wall 7.85 t'
    r=assignment(wall,project)
    assert r['status']=='missing' and not r['associations']


def test_actual_parser_exposes_material_without_changing_mesh_volume(tmp_path):
    doc,_,wall=make_box(opening=True)
    associate(doc,wall,doc.create_entity('IfcMaterial',Name='Declared concrete'))
    parsed=result(doc,tmp_path)
    row=next(x for x in parsed['objects'] if x['id']==wall.id())
    assert row['material_assignment']['associations'][0]['material']['name']=='Declared concrete'
    mesh=next(x for x in parsed['ifc_geometry']['objects'] if x['id']==wall.id())
    assert mesh['volume_m3']==pytest.approx(22)
    assert row['material_assignment']['quantity_status']=='not_measured'


def test_isolated_api_exposes_source_and_withdraws_after_parser_change(client,monkeypatch):
    doc,_,wall=make_box();associate(doc,wall,doc.create_entity('IfcMaterial',Name='Known material'))
    raw=doc.to_string().encode();pid=create_project(client)['project_id']
    fid=upload(client,pid,'material.ifc',raw)
    response=client.post(f'/api/projects/{pid}/cad-inspections',json={'file_id':fid})
    assert response.status_code==201,response.text
    record=response.json()
    assert record['source']['hash']==hashlib.sha256(raw).hexdigest()
    assert record['result']['objects'][0]['material_assignment']['status']=='declared'
    monkeypatch.setattr('backend.cad.parser_version',lambda:'changed-material-helper')
    current=client.get(f"/api/projects/{pid}/cad-inspections/{record['cad_id']}").json()
    assert current['status']=='stale' and current['result'] is None
