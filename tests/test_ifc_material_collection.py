"""Independent cuboid volumes and failure boundaries for material ownership."""
from fractions import Fraction
import hashlib
import json
import math
import pytest
from backend.ifc_material_collection import measure_collection
from test_ifc_union import model
from test_ifc_materials import layers, associate
from test_ifc_layer_quantities import layered_wall


def collection_model(tmp_path, shift=(1.,0.,0.), millimetres=False, separate_material_ids=False, rotation=False):
    f=1000 if millimetres else 1
    boxes=[(0,0,0,2,3,4),(shift[0],shift[1],shift[2],shift[0]+2,shift[1]+3,shift[2]+4)]
    doc,products=model([tuple(float(v*f) for v in box) for box in boxes],
                       angle=math.radians(37) if rotation else 0.,offset=(5e8,3e9,0.) if rotation else (0.,0.,0.))
    if millimetres:doc.by_type('IfcSIUnit')[0].Prefix='MILLI'
    usage,_=layers(doc,[('A',.7*f),('B',2.3*f)]);usage.OffsetFromReferenceLine=-1.5*f
    for index,p in enumerate(products):
        chosen=usage
        if index and separate_material_ids:
            chosen,_=layers(doc,[('A',.7*f),('B',2.3*f)]);chosen.OffsetFromReferenceLine=-1.5*f
        associate(doc,p,chosen)
        body=p.Representation.Representations[0]
        axis=doc.create_entity('IfcShapeRepresentation',ContextOfItems=body.ContextOfItems,
              RepresentationIdentifier='Axis',RepresentationType='Curve2D',Items=[doc.create_entity('IfcPolyline',Points=[
                  doc.create_entity('IfcCartesianPoint',Coordinates=(-1.*f,0.)),doc.create_entity('IfcCartesianPoint',Coordinates=(1.*f,0.))])])
        p.Representation.Representations=[axis,body]
    path=tmp_path/'material-collection.ifc';doc.write(str(path))
    return doc,products,path


@pytest.mark.parametrize('shift,net_length',[(0.,2),(1.,3),(2.,4),(4.,4)])
@pytest.mark.parametrize('millimetres,rotation',[(False,False),(True,False),(False,True)])
def test_same_material_overlap_is_counted_once_with_independent_fraction_volumes(tmp_path,shift,net_length,millimetres,rotation):
    _,products,path=collection_model(tmp_path,shift=(shift,0.,0.),millimetres=millimetres,rotation=rotation)
    before=hashlib.sha256(path.read_bytes()).hexdigest()
    r=measure_collection(path,[p.id() for p in reversed(products)])
    assert r['status']=='measured',r
    expected=[float(Fraction(net_length)*Fraction(7,10)*4),float(Fraction(net_length)*Fraction(23,10)*4)]
    assert [m['union_envelope_m3'] for m in r['materials']]==pytest.approx(expected,abs=1e-7)
    assert r['sum_layer_envelope_m3']==pytest.approx(48)
    assert r['union_envelope_m3']==pytest.approx(net_length*3*4,abs=1e-7)
    assert r['same_material_overlap_deduction_m3']==pytest.approx(48-net_length*12,abs=1e-7)
    assert len(r['source_layers'])==4 and all(len(m['sources'])==2 for m in r['materials'])
    assert r['cross_material_overlap_detected'] is False
    assert hashlib.sha256(path.read_bytes()).hexdigest()==before


@pytest.mark.parametrize('different_ids,shift',[(True,(0.,0.,0.)),(False,(0.,1.,0.))])
def test_material_ownership_conflict_never_becomes_priced_total(tmp_path,different_ids,shift):
    _,products,path=collection_model(tmp_path,shift=shift,separate_material_ids=different_ids)
    r=measure_collection(path,[p.id() for p in products])
    assert r['status']=='unavailable' and r['reason']=='cross_material_overlap_ownership_unresolved'
    assert r['cross_material_overlap_detected'] is True
    assert r['materials']==r['source_layers']==[]
    assert r['union_envelope_m3'] is r['sum_layer_envelope_m3'] is r['same_material_overlap_deduction_m3'] is None


def test_identical_names_in_separate_material_entities_are_not_merged(tmp_path):
    _,products,path=collection_model(tmp_path,shift=(4.,0.,0.),separate_material_ids=True)
    r=measure_collection(path,[p.id() for p in products])
    assert r['status']=='measured',r
    assert len(r['materials'])==4
    assert r['union_envelope_m3']==pytest.approx(48)


def test_actual_voided_layer_mesh_is_used_not_host_volume_proportions(tmp_path):
    import ifcopenshell
    doc,_,wall,usage,_,path=layered_wall(tmp_path)
    second=doc.create_entity('IfcWall',GlobalId=ifcopenshell.guid.new(),ObjectPlacement=wall.ObjectPlacement,Representation=wall.Representation)
    associate(doc,second,usage)
    doc.write(str(path));r=measure_collection(path,[wall.id(),second.id()])
    assert r['status']=='measured',r
    # One host has a 2m3 void, the other is full: union is full but not 46m3.
    assert r['sum_layer_envelope_m3']==pytest.approx(46)
    assert [m['union_envelope_m3'] for m in r['materials']]==pytest.approx([5.6,18.4])
    assert r['union_envelope_m3']==pytest.approx(24)


def test_missing_one_selected_material_cannot_return_partial_success(tmp_path):
    doc,products,path=collection_model(tmp_path)
    doc.remove(products[1].HasAssociations[0]);doc.write(str(path))
    r=measure_collection(path,[p.id() for p in products])
    assert r['reason']=='selected_layer_geometry_unavailable'
    assert r['materials']==[] and r['union_envelope_m3'] is None
    assert r['failed_products'][0]['product_id']==products[1].id()


@pytest.mark.parametrize('ids',[[],[1],[True,2],[1,1],[1.,2],[1,-2],list(range(1,18))])
def test_selection_rejected_before_file_open(ids):
    with pytest.raises(ValueError,match='Choose'):measure_collection('not-present.ifc',ids)


def test_cycle_rejected_before_native_geometry(tmp_path):
    doc,products,path=collection_model(tmp_path)
    products[0].ObjectPlacement.PlacementRelTo=products[0].ObjectPlacement;doc.write(str(path))
    with pytest.raises(ValueError,match='cyclic'):measure_collection(path,[p.id() for p in products])


def test_global_triangle_budget_does_not_fall_back_to_layer_sum(tmp_path,monkeypatch):
    import backend.ifc_material_collection as module
    _,products,path=collection_model(tmp_path);monkeypatch.setattr(module,'MAX_TRIANGLES',1)
    r=measure_collection(path,[p.id() for p in products])
    assert r['reason']=='input_triangle_budget_exceeded'
    assert r['materials']==[] and r['union_envelope_m3'] is None


def test_isolated_native_worker_returns_actual_material_union(tmp_path):
    from backend import parser_runtime
    _,products,path=collection_model(tmp_path)
    before=path.read_bytes()
    with parser_runtime.run('cad',path,options={'operation':'ifc_material_collection','product_ids':[p.id() for p in products]}) as scope:
        r=json.loads((scope['work']/'result.json').read_text(encoding='utf-8'))
        assert scope['resource_limits']['enforced']
    assert r['status']=='measured',r
    assert r['union_envelope_m3']==pytest.approx(36)
    assert path.read_bytes()==before
