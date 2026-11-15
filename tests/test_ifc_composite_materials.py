import hashlib
import json
from pathlib import Path
import ifcopenshell
import pytest
from backend.ifc_layer_quantities import measure_layers
from backend.ifc_material_collection import measure_collection
from test_ifc_member_quantities import member
from test_ifc_materials import associate

def composite(folder,prefix=None,case='cross_material_opening'):
    doc,project,element,material,path=member(folder,prefix=prefix,opening=case!='adjacent' and case!='overlap')
    scale=1000 if prefix=='MILLI' else 1
    doc.remove(element.HasAssociations[0])
    solid=element.Representation.Representations[0].Items[0]
    def rectangle(width,depth,x):
        pos=doc.create_entity('IfcAxis2Placement2D',Location=doc.create_entity('IfcCartesianPoint',Coordinates=(float(x*scale),0.)))
        return doc.create_entity('IfcRectangleProfileDef',ProfileType='AREA',Position=pos,XDim=width*scale,YDim=depth*scale)
    if case=='tube_core_opening':
        profiles=[doc.create_entity('IfcRectangleHollowProfileDef',ProfileType='AREA',XDim=2.*scale,YDim=3.*scale,WallThickness=.25*scale),rectangle(1.5,2.5,0.)]
    else:
        width,offset=(1.2,.4) if case=='overlap' else (1.,.5)
        profiles=[rectangle(width,3.,-offset),rectangle(width,3.,offset)]
    cp=doc.create_entity('IfcCompositeProfileDef',ProfileType='AREA',Profiles=profiles)
    solid.SweptArea=cp
    materials=[material,doc.create_entity('IfcMaterial',Name='Second material <declared>')]
    mp=[doc.create_entity('IfcMaterialProfile',Material=m,Profile=p) for m,p in zip(materials,profiles)]
    group=doc.create_entity('IfcMaterialProfileSet',MaterialProfiles=mp,CompositeProfile=cp)
    usage=doc.create_entity('IfcMaterialProfileSetUsage',ForProfileSet=group,CardinalPoint=5)
    associate(doc,element,usage)
    if case=='one_sided_opening':
        opening=element.HasOpenings[0].RelatedOpeningElement.Representation.Representations[0].Items[0]
        opening.Position.Location.Coordinates=(.5*scale,0.,0.)
    doc.write(str(path))
    return doc,element,profiles,materials,mp,solid,path

ORACLE=json.loads((Path(__file__).parents[1]/'validation/ifc-composite-materials-20261115/reference-frozen.json').read_text())


@pytest.mark.parametrize('case',['adjacent','one_sided_opening','cross_material_opening','tube_core_opening'])
@pytest.mark.parametrize('prefix',[None,'MILLI'])
def test_material_partitions_match_independent_rectangular_reference(tmp_path,case,prefix):
    doc,element,_,materials,profiles,_,path=composite(tmp_path,prefix,case)
    before=hashlib.sha256(path.read_bytes()).hexdigest()
    r=measure_layers(path,element.id())
    assert r['status']=='measured',r
    assert [x['material_id'] for x in r['layers']]==[m.id() for m in materials]
    assert [x['layer_id'] for x in r['layers']]==[p.id() for p in profiles]
    assert [x['envelope_volume_m3'] for x in r['layers']]==pytest.approx([float(x) for x in ORACLE[case]['material_m3']],abs=1e-8)
    assert r['host_volume_m3']==pytest.approx(float(ORACLE[case]['whole_m3']),abs=1e-8)
    assert not r['partition_overlap_detected']
    assert r['material_mapping']['host_volume_method'].startswith('verified_union')
    assert hashlib.sha256(path.read_bytes()).hexdigest()==before


@pytest.mark.parametrize('problem',['overlap','unbound','same_profile_twice','wrong_composite','missing_material','nested','extra_body'])
def test_conflicting_or_incomplete_partitions_keep_all_quantities_unknown(tmp_path,problem):
    doc,element,profiles,materials,mp,solid,path=composite(tmp_path,case='overlap' if problem=='overlap' else 'adjacent')
    group=element.HasAssociations[0].RelatingMaterial.ForProfileSet
    if problem=='unbound':group.MaterialProfiles=[mp[0]]
    elif problem=='same_profile_twice':mp[1].Profile=profiles[0]
    elif problem=='wrong_composite':group.CompositeProfile=None
    elif problem=='missing_material':mp[1].Material=None
    elif problem=='nested':solid.SweptArea.Profiles=[profiles[0],solid.SweptArea]
    elif problem=='extra_body':element.Representation.Representations*=2
    doc.write(str(path));sink=[]
    r=measure_layers(path,element.id(),mesh_sink=sink)
    assert r['status']=='unavailable' and r['layers']==[] and not sink,r
    assert r['host_volume_m3'] is r['total_layer_envelope_m3'] is None
    if problem=='overlap':assert r['reason']=='composite_profile_spatial_overlap'


def test_mapped_nonuniform_scale_preserves_actual_spatial_partitions(tmp_path):
    doc,element,_,_,_,_,path=composite(tmp_path,case='adjacent')
    body=element.Representation.Representations[0]
    origin=doc.create_entity('IfcAxis2Placement3D',Location=doc.create_entity('IfcCartesianPoint',Coordinates=(0.,0.,0.)))
    mapping=doc.create_entity('IfcRepresentationMap',MappingOrigin=origin,MappedRepresentation=body)
    transform=doc.create_entity('IfcCartesianTransformationOperator3DnonUniform',LocalOrigin=origin.Location,Scale=2.,Scale2=3.,Scale3=4.)
    item=doc.create_entity('IfcMappedItem',MappingSource=mapping,MappingTarget=transform)
    mapped=doc.create_entity('IfcShapeRepresentation',ContextOfItems=body.ContextOfItems,RepresentationIdentifier='Body',RepresentationType='MappedRepresentation',Items=[item])
    element.Representation.Representations=[mapped]
    doc.write(str(path));r=measure_layers(path,element.id())
    assert r['status']=='measured',r
    assert [p['envelope_volume_m3'] for p in r['layers']]==pytest.approx([288,288],abs=1e-8)


def test_shared_sweep_opening_is_not_mutated_by_private_partition(tmp_path):
    doc,element,_,_,_,solid,path=composite(tmp_path)
    hole=element.HasOpenings[0].RelatedOpeningElement
    hole.Representation=element.Representation
    doc.write(str(path))
    r=measure_layers(path,element.id())
    assert r['status']=='unavailable' and r['total_layer_envelope_m3'] is None,r


def test_composite_boolean_difference_retains_cut_for_each_material(tmp_path):
    doc,element,_,_,_,solid,path=composite(tmp_path)
    opening=element.HasOpenings[0].RelatedOpeningElement.Representation.Representations[0].Items[0]
    doc.remove(element.HasOpenings[0])
    body=element.Representation.Representations[0]
    body.Items=[doc.create_entity('IfcBooleanResult',Operator='DIFFERENCE',FirstOperand=solid,SecondOperand=opening)]
    body.RepresentationType='CSG'
    doc.write(str(path));r=measure_layers(path,element.id())
    assert r['status']=='measured',r
    assert [p['envelope_volume_m3'] for p in r['layers']]==pytest.approx([11,11],abs=1e-8)


def test_two_composites_preserve_material_groups_in_existing_collection(tmp_path):
    doc,element,_,_,_,_,path=composite(tmp_path)
    other=doc.create_entity('IfcColumn',GlobalId=ifcopenshell.guid.new(),Representation=element.Representation,
        ObjectPlacement=doc.create_entity('IfcLocalPlacement',PlacementRelTo=element.ObjectPlacement,
            RelativePlacement=doc.create_entity('IfcAxis2Placement3D',Location=doc.create_entity('IfcCartesianPoint',Coordinates=(5.,0.,0.)))))
    associate(doc,other,element.HasAssociations[0].RelatingMaterial)
    hole=element.HasOpenings[0].RelatedOpeningElement
    copy=doc.create_entity('IfcOpeningElement',GlobalId=ifcopenshell.guid.new(),Representation=hole.Representation,ObjectPlacement=other.ObjectPlacement)
    doc.create_entity('IfcRelVoidsElement',GlobalId=ifcopenshell.guid.new(),RelatingBuildingElement=other,RelatedOpeningElement=copy)
    doc.write(str(path));r=measure_collection(path,[element.id(),other.id()])
    assert r['status']=='measured',r
    assert [m['union_envelope_m3'] for m in r['materials']]==pytest.approx([22,22],abs=1e-8)
    assert r['union_envelope_m3']==pytest.approx(44,abs=1e-8)


def test_concentric_circular_materials_against_independent_pi_area(tmp_path):
    import math
    doc,element,_,_,mp,solid,path=composite(tmp_path,case='adjacent')
    outer=doc.create_entity('IfcCircleHollowProfileDef',ProfileType='AREA',Radius=.3,WallThickness=.03)
    inner=doc.create_entity('IfcCircleProfileDef',ProfileType='AREA',Radius=.27)
    solid.SweptArea.Profiles=[outer,inner]
    for row,profile in zip(mp,[outer,inner]):row.Profile=profile
    doc.write(str(path));r=measure_layers(path,element.id())
    expected=[math.pi*(.3**2-.27**2)*4,math.pi*.27**2*4]
    assert r['status']=='measured',r
    # Declared curved tessellation tolerance before this first execution: 0.5%.
    assert [row['envelope_volume_m3'] for row in r['layers']]==pytest.approx(expected,rel=.005,abs=1e-8)


def test_profile_count_budget_rejects_before_native_geometry(tmp_path):
    doc,element,profiles,materials,mp,solid,path=composite(tmp_path,case='adjacent')
    group=element.HasAssociations[0].RelatingMaterial.ForProfileSet
    for _ in range(15):
        profile=doc.create_entity('IfcRectangleProfileDef',ProfileType='AREA',XDim=1.,YDim=1.)
        solid.SweptArea.Profiles=(*solid.SweptArea.Profiles,profile)
        group.MaterialProfiles=(*group.MaterialProfiles,doc.create_entity('IfcMaterialProfile',Material=materials[0],Profile=profile))
    doc.write(str(path));r=measure_layers(path,element.id())
    assert r['status']=='unavailable' and r['reason']=='composite_profile_count_or_coverage',r


def test_existing_homogeneous_multiple_sweeps_remain_supported(tmp_path):
    doc,element,profiles,materials,mp,solid,path=composite(tmp_path,case='adjacent')
    group=element.HasAssociations[0].RelatingMaterial.ForProfileSet;group.CompositeProfile=None
    mp[1].Material=materials[0]
    profiles[1].Position.Location.Coordinates=(2.,0.)
    body=element.Representation.Representations[0]
    body.Items=[doc.create_entity('IfcExtrudedAreaSolid',SweptArea=profile,Position=solid.Position,
        ExtrudedDirection=solid.ExtrudedDirection,Depth=solid.Depth) for profile in profiles]
    doc.write(str(path));r=measure_layers(path,element.id())
    assert r['status']=='measured' and len(r['layers'])==1,r
    assert r['total_layer_envelope_m3']==pytest.approx(24,abs=1e-8)
