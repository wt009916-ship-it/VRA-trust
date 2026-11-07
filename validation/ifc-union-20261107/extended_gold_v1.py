import hashlib,json,math,sys
from pathlib import Path
out=Path(__file__).resolve().parent
root=Path(json.loads((out/'candidate-source-v2.json').read_text())['root']);sys.path[:0]=[str(root),str(root/'tests')]
import ifcopenshell
from test_ifc_union import model
from backend.ifc_union import measure_union
cases=[]
for name in ['independent_axes','nested_3d','nonuniform_mapping','centimetres','mirrored_mapping','circular_overlap']:
 factor=100 if name=='centimetres' else 1
 boxes=[tuple(v*factor for v in b) for b in [(0,0,0,2,3,4),(1,0,0,3,3,4)]]
 doc,products=model(boxes);expected=36.;tol=1e-8
 if name=='independent_axes':
  products[1].ObjectPlacement.RelativePlacement.RefDirection=doc.create_entity('IfcDirection',DirectionRatios=(0.,1.,0.))
 elif name=='nested_3d':
  rootaxis=products[0].ObjectPlacement.PlacementRelTo.RelativePlacement
  rootaxis.Axis.DirectionRatios=(0.,-math.sqrt(.5),math.sqrt(.5))
 elif name in {'nonuniform_mapping','mirrored_mapping'}:
  for p in products:
   body=p.Representation.Representations[0]
   origin=doc.create_entity('IfcAxis2Placement3D',Location=doc.create_entity('IfcCartesianPoint',Coordinates=(0.,0.,0.)))
   mapping=doc.create_entity('IfcRepresentationMap',MappingOrigin=origin,MappedRepresentation=body)
   if name=='nonuniform_mapping':
    transform=doc.create_entity('IfcCartesianTransformationOperator3DnonUniform',LocalOrigin=origin.Location,Scale=2.,Scale2=3.,Scale3=4.)
   else:
    transform=doc.create_entity('IfcCartesianTransformationOperator3D',LocalOrigin=origin.Location,Scale=1.,
      Axis1=doc.create_entity('IfcDirection',DirectionRatios=(-1.,0.,0.)),
      Axis2=doc.create_entity('IfcDirection',DirectionRatios=(0.,1.,0.)),
      Axis3=doc.create_entity('IfcDirection',DirectionRatios=(0.,0.,1.)))
   item=doc.create_entity('IfcMappedItem',MappingSource=mapping,MappingTarget=transform)
   p.Representation.Representations=[doc.create_entity('IfcShapeRepresentation',ContextOfItems=body.ContextOfItems,
    RepresentationIdentifier='Body',RepresentationType='MappedRepresentation',Items=[item])]
  if name=='nonuniform_mapping':expected=720.
 elif name=='centimetres':
  doc.by_type('IfcSIUnit')[0].Prefix='CENTI'
 elif name=='circular_overlap':
  for p in products:p.Representation.Representations[0].Items[0].SweptArea=doc.create_entity('IfcCircleProfileDef',ProfileType='AREA',Radius=1.)
  expected=4*(4*math.pi/3+math.sqrt(3)/2);tol=.02
 path=out/(name+'.ifc');doc.write(str(path));r=measure_union(path,[p.id() for p in products])
 value=r['union_volume_m3'];cases.append({'case':name,'file':path.name,'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
 'ids':[p.id() for p in products],'expected_m3':expected,'tolerance_m3':tol,'actual_m3':value,
 'matched':value is not None and abs(value-expected)<=tol,'result':r})
with (out/'extended-windows-v1.json').open('x',encoding='utf-8') as f:json.dump({'cases':cases,'curve_oracle':'Two equal-radius cylinder lens formula; tolerance 0.02 m3 covers tessellation, not certified surface accuracy'},f,indent=2)
print(json.dumps([{'case':r['case'],'expected':r['expected_m3'],'actual':r['actual_m3'],'matched':r['matched'],'reason':r['result']['reason']} for r in cases]))
