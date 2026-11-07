"""Independent rectangular layer/opening volumes; no proportional allocation oracle."""
import pytest

from backend.ifc_layer_quantities import measure_layers
from test_ifc_measurements import make_box
from test_ifc_materials import layers, associate


def layered_wall(tmp_path, prefix=None, sense='POSITIVE', opening=True):
    doc,project,wall=make_box(prefix,opening=opening)
    scale=1000 if prefix=='MILLI' else 1
    usage,items=layers(doc,[('A',.7*scale),('B',2.3*scale)])
    usage.OffsetFromReferenceLine=(-1.5 if sense=='POSITIVE' else 1.5)*scale
    usage.DirectionSense=sense;associate(doc,wall,usage)
    body=wall.Representation.Representations[0]
    points=[doc.create_entity('IfcCartesianPoint',Coordinates=(x*scale,0.)) for x in [-1.,1.]]
    axis=doc.create_entity('IfcShapeRepresentation',ContextOfItems=body.ContextOfItems,
          RepresentationIdentifier='Axis',RepresentationType='Curve2D',
          Items=[doc.create_entity('IfcPolyline',Points=points)])
    wall.Representation.Representations=[axis,body]
    path=tmp_path/'layers.ifc';doc.write(str(path))
    return doc,project,wall,usage,axis,path


@pytest.mark.parametrize('prefix', [None,'MILLI'])
@pytest.mark.parametrize('sense', ['POSITIVE','NEGATIVE'])
def test_partial_depth_opening_is_deducted_from_intersected_layer_only(tmp_path,prefix,sense):
    _,_,wall,_,_,path=layered_wall(tmp_path,prefix,sense)
    r=measure_layers(path,wall.id())
    assert r['status']=='measured',r['reason']
    # Host 2x3x4; void 0.5x1x4 lies in y=[-0.5,0.5].
    # First outer layer 0.7m never meets the void: 2*.7*4=5.6.
    # Remaining layer: 2*2.3*4 - .5*1*4=16.4. Ratio allocation is wrong.
    assert [x['envelope_volume_m3'] for x in r['layers']]==pytest.approx([5.6,16.4],abs=1e-9)
    assert r['total_layer_envelope_m3']==pytest.approx(22,abs=1e-9)
    assert r['layers'][0]['envelope_volume_m3']!=pytest.approx(22*.7/3)
    assert r['quantity_kind']=='model_layer_envelope_after_ifc_openings'


@pytest.mark.parametrize('problem,reason',[
    ('offset','layer_envelope_does_not_match_body'),('thickness','layer_envelope_does_not_match_body'),
    ('axis_missing','straight_reference_axis_required'),('curved_axis','two_point_planar_reference_axis_required'),
    ('negative_thickness','layer_thickness_or_material_unavailable'),('no_material','material_assignment_missing_or_ambiguous')])
def test_unverified_layer_mapping_has_no_partial_quantity(tmp_path,problem,reason):
    doc,_,wall,usage,axis,path=layered_wall(tmp_path)
    if problem=='offset':usage.OffsetFromReferenceLine=-1.4
    elif problem=='thickness':usage.ForLayerSet.MaterialLayers[0].LayerThickness=.9
    elif problem=='axis_missing':wall.Representation.Representations=wall.Representation.Representations[1:]
    elif problem=='curved_axis':axis.Items[0].Points+= (doc.create_entity('IfcCartesianPoint',Coordinates=(2.,1.)),)
    elif problem=='negative_thickness':usage.ForLayerSet.MaterialLayers[0].LayerThickness=-1.
    elif problem=='no_material':doc.remove(wall.HasAssociations[0])
    doc.write(str(path));r=measure_layers(path,wall.id())
    assert r['status']=='unavailable' and r['reason']==reason
    assert r['layers']==[] and r['total_layer_envelope_m3'] is None


def test_isolated_worker_uses_layer_operation_and_preserves_source(tmp_path):
    import hashlib,json
    from backend import parser_runtime
    _,_,wall,_,_,path=layered_wall(tmp_path)
    before=hashlib.sha256(path.read_bytes()).hexdigest()
    with parser_runtime.run('cad',path,options={'operation':'ifc_layers','product_id':wall.id()}) as scope:
        r=json.loads((scope['work']/'result.json').read_text(encoding='utf-8'))
    assert r['status']=='measured',r.get('reason')
    assert [x['envelope_volume_m3'] for x in r['layers']]==pytest.approx([5.6,16.4],abs=1e-9)
    assert hashlib.sha256(path.read_bytes()).hexdigest()==before
