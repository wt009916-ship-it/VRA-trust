import ifcopenshell
import pytest
from test_ifc_slab_layers import slab_model
from test_ifc_materials import layers, associate
from test_ifc_union import prepare
from test_collection_scenarios import five_stage_payload


def mixed_wall_slab(tmp_path):
    doc,_,slab,usage,solid,path=slab_model(tmp_path,opening=False)
    origin=doc.create_entity('IfcAxis2Placement3D',Location=doc.create_entity('IfcCartesianPoint',Coordinates=(0.,0.,0.)))
    wallsolid=doc.create_entity('IfcExtrudedAreaSolid',SweptArea=solid.SweptArea,Position=origin,ExtrudedDirection=solid.ExtrudedDirection,Depth=4.)
    context=slab.Representation.Representations[0].ContextOfItems
    body=doc.create_entity('IfcShapeRepresentation',ContextOfItems=context,RepresentationIdentifier='Body',RepresentationType='SweptSolid',Items=[wallsolid])
    line=doc.create_entity('IfcPolyline',Points=[doc.create_entity('IfcCartesianPoint',Coordinates=(-1.,0.)),doc.create_entity('IfcCartesianPoint',Coordinates=(1.,0.))])
    axis=doc.create_entity('IfcShapeRepresentation',ContextOfItems=context,RepresentationIdentifier='Axis',RepresentationType='Curve2D',Items=[line])
    wall=doc.create_entity('IfcWall',GlobalId=ifcopenshell.guid.new(),ObjectPlacement=slab.ObjectPlacement,Representation=doc.create_entity('IfcProductDefinitionShape',Representations=[axis,body]))
    wallusage,_=layers(doc,[('A',.7),('B',2.3)]);wallusage.OffsetFromReferenceLine=-1.5
    for w,s in zip(wallusage.ForLayerSet.MaterialLayers,usage.ForLayerSet.MaterialLayers):w.Material=s.Material
    associate(doc,wall,wallusage);doc.write(str(path))
    return doc,[wall,slab],path


def test_actual_mixed_wall_slab_source_to_material_cost_and_five_stage_carbon(client,tmp_path):
    doc,products,path=mixed_wall_slab(tmp_path)
    pid,base,fid,inspection,content=prepare(client,doc)
    single=client.post(base+'/ifc-layer-takeoffs',json={'cad_id':inspection['cad_id'],'product_id':products[1].id()})
    assert single.status_code==201,single.text
    assert single.json()['status']=='measured'
    assert single.json()['result']['layer_reference']['axis']=='AXIS3'
    r=client.post(base+'/ifc-material-collections',json={'cad_id':inspection['cad_id'],'product_ids':[p.id() for p in products]})
    assert r.status_code==201,r.text
    source=r.json();assert source['status']=='measured'
    assert [m['union_envelope_m3'] for m in source['result']['materials']]==pytest.approx([11.6,36.4],abs=1e-7)
    assert {s['product_type'] for s in source['result']['source_layers']}=={'IfcWall','IfcSlab'}
    r=client.post(base+'/collection-scenarios',json=five_stage_payload(source));assert r.status_code==201,r.text
    record=r.json();assert record['status']=='calculated'
    # Distinct separated elements:24+24=48m3, half solid,10% waste =26.4m3.
    assert record['result']['alternatives'][0]['cost']['material_total']=='2640.00'
    assert record['result']['alternatives'][0]['carbon']['boundary_total_kgco2e']==pytest.approx(52800+132+2+6000+1.5,abs=1e-7)
    report=client.get(base+'/collection-scenarios/'+record['collectionscenario_id']+'/report.html')
    assert report.status_code==200 and '2640.00' in report.text and '分层构件' in report.text
    assert client.get(base+'/files/'+fid).content==content
