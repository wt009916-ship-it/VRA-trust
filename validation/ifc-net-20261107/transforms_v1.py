import hashlib,json,math,sys
from pathlib import Path
repo=Path.cwd();out=Path(__file__).resolve().parent
sys.path[:0]=[str(repo),str(repo/'tests')]
import ifcopenshell
from test_ifc_measurements import make_box
from backend.cad_worker import parse_ifc
rows=[]
for case in ['rotate_37','nested_rotation','nonuniform_mapping','overlapping_aggregate']:
    doc,project,wall=make_box(opening=True)
    if case=='rotate_37':
        angle=math.radians(37)
        wall.ObjectPlacement.RelativePlacement.RefDirection.DirectionRatios=(math.cos(angle),math.sin(angle),0.)
    elif case=='nested_rotation':
        a=doc.create_entity('IfcAxis2Placement3D',Location=doc.create_entity('IfcCartesianPoint',Coordinates=(100.,200.,300.)),
           Axis=doc.create_entity('IfcDirection',DirectionRatios=(0.,math.sqrt(.5),math.sqrt(.5))),
           RefDirection=doc.create_entity('IfcDirection',DirectionRatios=(1.,0.,0.)))
        wall.ObjectPlacement.PlacementRelTo=doc.create_entity('IfcLocalPlacement',RelativePlacement=a)
    elif case=='nonuniform_mapping':
        for element in [wall,doc.by_type('IfcOpeningElement')[0]]:
            body=element.Representation.Representations[0]
            origin=doc.create_entity('IfcAxis2Placement3D',Location=doc.create_entity('IfcCartesianPoint',Coordinates=(0.,0.,0.)))
            mapping=doc.create_entity('IfcRepresentationMap',MappingOrigin=origin,MappedRepresentation=body)
            operator=doc.create_entity('IfcCartesianTransformationOperator3DnonUniform',LocalOrigin=origin.Location,Scale=2.,Scale2=3.,Scale3=4.)
            item=doc.create_entity('IfcMappedItem',MappingSource=mapping,MappingTarget=operator)
            mapped=doc.create_entity('IfcShapeRepresentation',ContextOfItems=body.ContextOfItems,RepresentationIdentifier='Body',RepresentationType='MappedRepresentation',Items=[item])
            element.Representation.Representations=[mapped]
    else:
        other=doc.create_entity('IfcWall',GlobalId=ifcopenshell.guid.new(),Name='Overlapping full host',ObjectPlacement=wall.ObjectPlacement,Representation=wall.Representation)
        storey=doc.create_entity('IfcBuildingStorey',GlobalId=ifcopenshell.guid.new(),Name='Synthetic overlapping aggregate',ObjectPlacement=wall.ObjectPlacement)
        doc.create_entity('IfcRelAggregates',GlobalId=ifcopenshell.guid.new(),RelatingObject=storey,RelatedObjects=[wall,other])
    path=out/(case+'.ifc');doc.write(str(path))
    digest=hashlib.sha256(path.read_bytes()).hexdigest();result=parse_ifc(path)
    host=next(r for r in result['ifc_geometry']['objects'] if r['id']==wall.id())
    expected=528. if case=='nonuniform_mapping' else 22.
    row={'case':case,'sha256':digest,'file':path.name,'expected_host_volume_m3':expected,'actual_host_volume_m3':host['volume_m3'],
         'host_passed':host['volume_m3'] is not None and abs(host['volume_m3']-expected)<=1e-8,'source_preserved':hashlib.sha256(path.read_bytes()).hexdigest()==digest}
    if case=='overlapping_aggregate':
        parent=next(r for r in result['ifc_geometry']['objects'] if r['id']==storey.id())
        row.update(expected_geometric_union_m3=24.,aggregate_volume_m3=parent['volume_m3'],aggregate_status='not_implemented',
                   limitation='Individual host measures are not aggregate net quantities; no sum accepted as union.')
    rows.append(row)
with (out/'transform-gold-windows-v1.json').open('x',encoding='utf-8') as f:json.dump({'cases':rows},f,indent=2)
print(json.dumps(rows))
assert all(r['host_passed'] and r['source_preserved'] for r in rows)
