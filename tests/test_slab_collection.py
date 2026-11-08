import hashlib
import pytest
from backend.ifc_material_collection import measure_collection
from backend.ifc_layer_quantities import measure_layers
from test_ifc_slab_layers import slab_model
from test_ifc_materials import associate, layers


def slab_pair(tmp_path,shift=1.,tilted=False,conflict=False):
    import ifcopenshell
    doc,_,slab,usage,_,path=slab_model(tmp_path,tilted=tilted,opening=False)
    pos=doc.create_entity('IfcAxis2Placement3D',Location=doc.create_entity('IfcCartesianPoint',Coordinates=(shift,0.,0.)))
    placement=doc.create_entity('IfcLocalPlacement',PlacementRelTo=slab.ObjectPlacement,RelativePlacement=pos)
    second=doc.create_entity('IfcSlab',GlobalId=ifcopenshell.guid.new(),Name='Second shared geometry slab',ObjectPlacement=placement,Representation=slab.Representation,PredefinedType='FLOOR')
    if conflict:
        other,_=layers(doc,[('different A',1.),('different B',3.)]);other.LayerSetDirection='AXIS3';other.OffsetFromReferenceLine=0.
        associate(doc,second,other)
    else:associate(doc,second,usage)
    doc.write(str(path));return doc,[slab,second],path


@pytest.mark.parametrize('tilted',[False,True])
@pytest.mark.parametrize('shift,length',[(0.,2.),(1.,3.),(2.,4.),(4.,4.)])
def test_slab_collection_material_overlap_and_shared_source_immutability(tmp_path,tilted,shift,length):
    doc,products,path=slab_pair(tmp_path,shift,tilted)
    before=hashlib.sha256(path.read_bytes()).hexdigest();serialized=doc.to_string()
    r=measure_collection(path,[p.id() for p in products]);assert r['status']=='measured',r
    assert [m['union_envelope_m3'] for m in r['materials']]==pytest.approx([length*3,length*9],abs=1e-7)
    assert r['sum_layer_envelope_m3']==pytest.approx(48.,abs=1e-7)
    assert r['union_envelope_m3']==pytest.approx(length*12,abs=1e-7)
    assert all(s['product_type']=='IfcSlab' for s in r['source_layers'])
    # Direct shared-document mode must not edit source solids/positions.
    measure_layers(path,products[0].id(),_document=doc)
    assert doc.to_string()==serialized and hashlib.sha256(path.read_bytes()).hexdigest()==before


def test_slab_overlap_with_unresolved_material_ownership_is_refused(tmp_path):
    _,products,path=slab_pair(tmp_path,conflict=True)
    r=measure_collection(path,[p.id() for p in products])
    assert r['status']=='unavailable' and r['reason']=='cross_material_overlap_ownership_unresolved'
    assert r['materials']==[] and r['union_envelope_m3'] is None


def test_clipped_slab_keeps_extruded_reference_plane(tmp_path):
    doc,_,slab,_,solid,path=slab_model(tmp_path,opening=False)
    # Base width2 (x6..8), cut x>=7 leaves a half width1 rectangular prism.
    pos=doc.create_entity('IfcAxis2Placement3D',Location=doc.create_entity('IfcCartesianPoint',Coordinates=(7.,-8.,9.)),
        Axis=doc.create_entity('IfcDirection',DirectionRatios=(1.,0.,0.)),RefDirection=doc.create_entity('IfcDirection',DirectionRatios=(0.,1.,0.)))
    plane=doc.create_entity('IfcPlane',Position=pos)
    half=doc.create_entity('IfcHalfSpaceSolid',BaseSurface=plane,AgreementFlag=False)
    cut=doc.create_entity('IfcBooleanClippingResult',Operator='DIFFERENCE',FirstOperand=solid,SecondOperand=half)
    slab.Representation.Representations[0].Items=[cut];slab.Representation.Representations[0].RepresentationType='Clipping'
    doc.write(str(path));r=measure_layers(path,slab.id());assert r['status']=='measured',r
    assert [v['envelope_volume_m3'] for v in r['layers']]==pytest.approx([3.,9.],abs=1e-8)


def test_no_invented_slab_layers_for_missing_material_usage(tmp_path):
    doc,_,slab,_,_,path=slab_model(tmp_path,opening=False)
    doc.remove(slab.HasAssociations[0]);doc.write(str(path))
    r=measure_layers(path,slab.id());assert r['status']=='unavailable'
    assert r['reason']=='material_assignment_missing_or_ambiguous' and r['layers']==[]
