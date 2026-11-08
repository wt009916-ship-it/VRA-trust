import pytest
from test_ifc_slab_layers import slab_model
from backend.ifc_layer_quantities import measure_layers


def test_shared_opening_representation_with_distinct_placements_is_not_overwritten(tmp_path):
    import ifcopenshell
    doc,_,slab,_,_,path=slab_model(tmp_path,tilted=True)
    first=slab.HasOpenings[0].RelatedOpeningElement
    delta=doc.create_entity('IfcAxis2Placement3D',Location=doc.create_entity('IfcCartesianPoint',Coordinates=(.7,0.,0.)))
    second=doc.create_entity('IfcOpeningElement',GlobalId=ifcopenshell.guid.new(),
        ObjectPlacement=doc.create_entity('IfcLocalPlacement',PlacementRelTo=slab.ObjectPlacement,RelativePlacement=delta),Representation=first.Representation)
    doc.create_entity('IfcRelVoidsElement',GlobalId=ifcopenshell.guid.new(),RelatingBuildingElement=slab,RelatedOpeningElement=second)
    doc.write(str(path));before=doc.to_string()
    result=measure_layers(path,slab.id(),_document=doc)
    assert result['status']=='measured',result['reason']
    # Two disjoint 0.5x1x2 cavity solids, each z=.5..2.5.
    assert result['total_layer_envelope_m3']==pytest.approx(24-2,abs=1e-8)
    assert [r['envelope_volume_m3'] for r in result['layers']]==pytest.approx([5.5,16.5],abs=1e-8)
    assert doc.to_string()==before and first.Representation==second.Representation
