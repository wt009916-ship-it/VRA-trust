"""Independent area*layer-depth minus actual intersecting void slices."""
import math
import numpy as np
import pytest
from backend.ifc_layer_quantities import measure_layers
from test_ifc_measurements import make_box
from test_ifc_materials import layers, associate


def slab_model(tmp_path, *, kind='IfcSlab', prefix=None, sense='POSITIVE', tilted=False, slanted=False, opening=True):
    import ifcopenshell
    doc,project,unused=make_box(prefix,offset=(1000000.,-2000000.,30.))
    f=1000. if prefix=='MILLI' else 1.
    body=unused.Representation.Representations[0];solid=body.Items[0]
    normal=(0.,.6,.8) if tilted else (0.,0.,1.)
    solid.Position.Location.Coordinates=(7.*f,-8.*f,9.*f)
    solid.Position.Axis=doc.create_entity('IfcDirection',DirectionRatios=normal)
    solid.Position.RefDirection=doc.create_entity('IfcDirection',DirectionRatios=(1.,0.,0.))
    if slanted:
        solid.ExtrudedDirection.DirectionRatios=(3.,0.,4.);solid.Depth=5.*f
    slab=doc.create_entity(kind,GlobalId=ifcopenshell.guid.new(),Name='Independent translated slab reference',ObjectPlacement=unused.ObjectPlacement,Representation=unused.Representation)
    if kind=='IfcSlab':slab.PredefinedType='ROOF' if tilted else 'FLOOR'
    doc.remove(unused)
    usage,_=layers(doc,[('A',1.*f),('B',3.*f)])
    usage.LayerSetDirection='AXIS3';usage.DirectionSense=sense;usage.OffsetFromReferenceLine=0. if sense=='POSITIVE' else 4.*f
    associate(doc,slab,usage)
    if opening:
        pos=doc.create_entity('IfcAxis2Placement3D',Location=doc.create_entity('IfcCartesianPoint',Coordinates=tuple((a+.5*b)*f for a,b in zip((7.,-8.,9.),normal))),Axis=solid.Position.Axis,RefDirection=solid.Position.RefDirection)
        profile=doc.create_entity('IfcRectangleProfileDef',ProfileType='AREA',XDim=.5*f,YDim=1.*f)
        cut=doc.create_entity('IfcExtrudedAreaSolid',SweptArea=profile,Position=pos,ExtrudedDirection=doc.create_entity('IfcDirection',DirectionRatios=(0.,0.,1.)),Depth=2.*f)
        rep=doc.create_entity('IfcShapeRepresentation',ContextOfItems=body.ContextOfItems,RepresentationIdentifier='Body',RepresentationType='SweptSolid',Items=[cut])
        hole=doc.create_entity('IfcOpeningElement',GlobalId=ifcopenshell.guid.new(),ObjectPlacement=slab.ObjectPlacement,Representation=doc.create_entity('IfcProductDefinitionShape',Representations=[rep]))
        doc.create_entity('IfcRelVoidsElement',GlobalId=ifcopenshell.guid.new(),RelatingBuildingElement=slab,RelatedOpeningElement=hole)
    path=tmp_path/'slab.ifc';doc.write(str(path))
    return doc,project,slab,usage,solid,path


@pytest.mark.parametrize('kind',['IfcSlab','IfcPlate'])
@pytest.mark.parametrize('prefix',[None,'MILLI'])
@pytest.mark.parametrize('sense',['POSITIVE','NEGATIVE'])
@pytest.mark.parametrize('tilted',[False,True])
def test_solid_reference_plane_rotation_units_and_partial_depth_void(tmp_path,kind,prefix,sense,tilted):
    _,_,slab,_,_,path=slab_model(tmp_path,kind=kind,prefix=prefix,sense=sense,tilted=tilted)
    r=measure_layers(path,slab.id())
    assert r['status']=='measured',r['reason']
    # Profile 2x3, normal thickness4. Hole area .5, z=.5..2.5.
    expected=[6-.5*.5,18-.5*1.5] if sense=='POSITIVE' else [6,18-.5*2]
    assert [v['envelope_volume_m3'] for v in r['layers']]==pytest.approx(expected,abs=1e-8)
    assert r['total_layer_envelope_m3']==pytest.approx(23.,abs=1e-8)
    assert r['layer_reference']['coordinate_system']=='extruded_solid_position'
    assert r['layer_reference']['axis']=='AXIS3'
    assert all('bounds_local_y_m' not in v and 'bounds_reference_m' in v for v in r['layers'])
    # Positive case happens to equal proportional allocation; negative case distinguishes it.
    if sense=='NEGATIVE':assert r['layers'][0]['envelope_volume_m3']!=pytest.approx(23/4)


@pytest.mark.parametrize('tilted',[False,True])
def test_slanted_extrusion_uses_perpendicular_thickness_not_depth(tmp_path,tilted):
    _,_,slab,_,_,path=slab_model(tmp_path,tilted=tilted,slanted=True,opening=False)
    r=measure_layers(path,slab.id());assert r['status']=='measured',r['reason']
    assert [v['envelope_volume_m3'] for v in r['layers']]==pytest.approx([6.,18.],abs=1e-8)
    assert r['host_volume_m3']==pytest.approx(24.,abs=1e-8)


@pytest.mark.parametrize('problem',['axis2','wrong_offset','wrong_thickness','two_bodies','two_solids','parallel_reference_axes'])
def test_ambiguous_or_inconsistent_slab_reference_has_no_material_values(tmp_path,problem):
    doc,_,slab,usage,solid,path=slab_model(tmp_path,opening=False)
    if problem=='axis2':usage.LayerSetDirection='AXIS2'
    elif problem=='wrong_offset':usage.OffsetFromReferenceLine=.1
    elif problem=='wrong_thickness':usage.ForLayerSet.MaterialLayers[0].LayerThickness=1.1
    elif problem=='two_bodies':slab.Representation.Representations*=2
    elif problem=='two_solids':slab.Representation.Representations[0].Items*=2
    else:solid.Position.RefDirection.DirectionRatios=(0.,0.,1.)
    doc.write(str(path));r=measure_layers(path,slab.id())
    assert r['status']=='unavailable' and r['layers']==[] and r['total_layer_envelope_m3'] is None


def test_slab_mesh_sink_retains_product_local_coordinates(tmp_path):
    _,_,slab,_,_,path=slab_model(tmp_path,tilted=True,opening=False)
    meshes=[];r=measure_layers(path,slab.id(),mesh_sink=meshes)
    assert r['status']=='measured' and len(meshes)==2
    # Normal (0,.6,.8), solid origin(7,-8,9): n.dot(origin)=2.4.
    projection=meshes[0]['vertices']@np.array([0.,.6,.8])
    assert min(projection)==pytest.approx(2.4) and max(projection)==pytest.approx(3.4)
    assert math.isclose(sum(v['envelope_volume_m3'] for v in r['layers']),24.,abs_tol=1e-8)
