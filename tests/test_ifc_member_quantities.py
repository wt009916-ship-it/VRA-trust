import hashlib
import json
from pathlib import Path

import ifcopenshell
import pytest

from backend.ifc_layer_quantities import measure_layers
from backend.ifc_material_collection import measure_collection
from test_ifc_measurements import make_box
from test_ifc_materials import associate
from test_ifc_union import model
from test_beam_profiles import example

ORACLE=json.loads((Path(__file__).parents[1]/'validation/ifc-member-materials-20261115/reference-frozen.json').read_text())


def replace_type(doc,old,kind):
    replacement=doc.create_entity(kind,GlobalId=old.GlobalId,Name=old.Name,ObjectPlacement=old.ObjectPlacement,Representation=old.Representation)
    for rel in list(old.HasOpenings):rel.RelatingBuildingElement=replacement
    doc.remove(old)
    return replacement


def member(tmp_path,kind='IfcBeam',prefix=None,opening=True):
    doc,project,old=make_box(prefix,opening=opening)
    element=replace_type(doc,old,kind)
    material=doc.create_entity('IfcMaterial',Name='Declared material <not measured>')
    associate(doc,element,material)
    path=tmp_path/'member.ifc';doc.write(str(path))
    return doc,project,element,material,path


@pytest.mark.parametrize('kind',['IfcBeam','IfcColumn'])
@pytest.mark.parametrize('prefix',[None,'MILLI'])
def test_real_voided_member_matches_independent_frozen_geometry(tmp_path,kind,prefix):
    _,_,element,material,path=member(tmp_path,kind,prefix)
    before=hashlib.sha256(path.read_bytes()).hexdigest()
    r=measure_layers(path,element.id())
    assert r['status']=='measured',r
    assert r['host_volume_m3']==pytest.approx(float(ORACLE['box']['net_m3']),abs=1e-8)
    assert r['layers'][0]['material_id']==material.id()
    assert r['layers'][0]['thickness_m'] is None
    assert r['layers'][0]['source_slice_kind']=='whole_member_material'
    assert r['layer_reference']['source_scope']=='instance'
    assert hashlib.sha256(path.read_bytes()).hexdigest()==before


def assign_profile(doc,element,profile,material):
    mp=doc.create_entity('IfcMaterialProfile',Material=material,Profile=profile)
    ms=doc.create_entity('IfcMaterialProfileSet',MaterialProfiles=[mp])
    usage=doc.create_entity('IfcMaterialProfileSetUsage',ForProfileSet=ms,CardinalPoint=5)
    associate(doc,element,usage)
    return mp,ms,usage


def test_hollow_profile_geometry_is_not_bounding_box(tmp_path):
    doc,_,element,profile,_,_=example('IfcRectangleHollowProfileDef',XDim=.2,YDim=.3,WallThickness=.01)
    material=doc.create_entity('IfcMaterial',Name='Declared steel')
    assign_profile(doc,element,profile,material)
    path=tmp_path/'hollow.ifc';doc.write(str(path))
    r=measure_layers(path,element.id())
    assert r['status']=='measured',r
    assert r['host_volume_m3']==pytest.approx(float(ORACLE['rectangular_hollow']['volume_m3']),abs=1e-8)
    assert r['host_volume_m3']!=pytest.approx(.2*.3*6)


@pytest.mark.parametrize('problem',['missing','ambiguous','heterogeneous','profile_mismatch','no_unit'])
def test_unknown_or_ambiguous_material_never_yields_a_total(tmp_path,problem):
    doc,project,element,material,path=member(tmp_path,opening=False)
    if problem=='missing':doc.remove(element.HasAssociations[0])
    elif problem=='ambiguous':associate(doc,element,doc.create_entity('IfcMaterial',Name='Other material'))
    elif problem=='no_unit':project.UnitsInContext=None
    else:
        doc.remove(element.HasAssociations[0])
        profile=element.Representation.Representations[0].Items[0].SweptArea
        if problem=='profile_mismatch':profile=doc.create_entity('IfcRectangleProfileDef',ProfileType='AREA',XDim=1.,YDim=1.)
        _,ms,_=assign_profile(doc,element,profile,material)
        if problem=='heterogeneous':
            mp=doc.create_entity('IfcMaterialProfile',Profile=profile,Material=doc.create_entity('IfcMaterial',Name='Concrete'))
            ms.MaterialProfiles=(*ms.MaterialProfiles,mp)
    doc.write(str(path));r=measure_layers(path,element.id())
    assert r['status']=='unavailable' and r['layers']==[] and r['total_layer_envelope_m3'] is None,r


def test_instance_overrides_type_and_preserves_both_origins(tmp_path):
    doc,_,element,material,path=member(tmp_path)
    kind=doc.create_entity('IfcBeamType',GlobalId=ifcopenshell.guid.new(),PredefinedType='BEAM')
    doc.create_entity('IfcRelDefinesByType',GlobalId=ifcopenshell.guid.new(),RelatedObjects=[element],RelatingType=kind)
    other=doc.create_entity('IfcMaterial',Name='Type material')
    associate(doc,kind,other)
    doc.write(str(path));r=measure_layers(path,element.id())
    assert r['status']=='measured' and r['layers'][0]['material_id']==material.id()
    assert {b['selection'] for b in r['material_assignment']['associations']}=={'effective_declaration','overridden_by_instance'}
    doc.remove(element.HasAssociations[0]);doc.write(str(path));r=measure_layers(path,element.id())
    assert r['status']=='measured' and r['layers'][0]['material_id']==other.id()
    assert r['layer_reference']['source_scope']=='type'


@pytest.mark.parametrize('different_material',[False,True])
def test_beam_column_collection_checks_material_ownership_and_overlap(tmp_path,different_material):
    doc,products=model([(0.,0.,0.,2.,3.,4.),(1.,0.,0.,3.,3.,4.)])
    products=[replace_type(doc,p,kind) for p,kind in zip(products,['IfcBeam','IfcColumn'])]
    material=doc.create_entity('IfcMaterial',Name='Same name')
    for i,p in enumerate(products):associate(doc,p,doc.create_entity('IfcMaterial',Name='Same name') if i and different_material else material)
    path=tmp_path/'mixed-members.ifc';doc.write(str(path))
    r=measure_collection(path,[p.id() for p in products])
    if different_material:
        assert r['status']=='unavailable' and r['cross_material_overlap_detected'] and r['union_envelope_m3'] is None
    else:
        assert r['status']=='measured',r
        assert r['union_envelope_m3']==pytest.approx(float(ORACLE['two_overlapping_members']['union_m3']),abs=1e-8)
        assert r['same_material_overlap_deduction_m3']==pytest.approx(12,abs=1e-8)
        assert {x['product_type'] for x in r['source_layers']}=={'IfcBeam','IfcColumn'}


def test_isolated_worker_material_binding_and_source_preservation(tmp_path):
    from backend import parser_runtime
    _,_,element,_,path=member(tmp_path)
    before=hashlib.sha256(path.read_bytes()).hexdigest()
    with parser_runtime.run('cad',path,options={'operation':'ifc_layers','product_id':element.id()}) as scope:
        r=json.loads((scope['work']/'result.json').read_text(encoding='utf-8'))
    assert r['status']=='measured',r
    assert r['total_layer_envelope_m3']==pytest.approx(22,abs=1e-8)
    assert hashlib.sha256(path.read_bytes()).hexdigest()==before


def test_existing_wall_and_new_column_share_material_collection(tmp_path):
    from test_ifc_material_collection import collection_model
    doc,products,path=collection_model(tmp_path,shift=(4.,0.,0.))
    material=products[0].HasAssociations[0].RelatingMaterial.ForLayerSet.MaterialLayers[0].Material
    column=replace_type(doc,products[1],'IfcColumn')
    associate(doc,column,material)
    doc.write(str(path));r=measure_collection(path,[products[0].id(),column.id()])
    assert r['status']=='measured',r
    assert r['union_envelope_m3']==pytest.approx(48,abs=1e-8)
    values={m['material_id']:m['union_envelope_m3'] for m in r['materials']}
    assert values[material.id()]==pytest.approx(5.6+24,abs=1e-8)
    assert len(r['materials'])==2


def test_invalid_opening_ownership_and_missing_body_keep_quantity_unknown(tmp_path):
    doc,_,element,_,path=member(tmp_path)
    relation=element.HasOpenings[0]
    doc.create_entity('IfcRelVoidsElement',GlobalId=ifcopenshell.guid.new(),RelatingBuildingElement=element,RelatedOpeningElement=relation.RelatedOpeningElement)
    doc.write(str(path));r=measure_layers(path,element.id())
    assert r['status']=='unavailable' and r['host_volume_m3'] is None
    element.Representation=None;doc.write(str(path));r=measure_layers(path,element.id())
    assert r['status']=='unavailable' and not r['layers']
