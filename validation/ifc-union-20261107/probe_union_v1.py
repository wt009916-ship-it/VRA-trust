"""Independent axis-box union gold; native IFC and candidate Boolean are separate paths."""
import hashlib,itertools,json,math,sys
from pathlib import Path
out=Path(__file__).resolve().parent;repo=out.parents[1]
sys.path[:0]=[str(out/'probe-installed'),str(repo),str(repo/'tests')]
import numpy as np
import ifcopenshell,ifcopenshell.geom
from ifcopenshell.util.shape import get_shape_matrix
import manifold3d as m
from test_ifc_measurements import make_box
from backend.ifc_geometry import mesh_measurements
def oracle(boxes):
 axes=[sorted(set(b[i] for b in boxes)|set(b[i+3] for b in boxes)) for i in range(3)]
 volume=0.
 for cell in itertools.product(*[list(zip(a,a[1:])) for a in axes]):
  point=[sum(pair)/2 for pair in cell]
  if any(all(b[i]<point[i]<b[i+3] for i in range(3)) for b in boxes):volume+=math.prod(hi-lo for lo,hi in cell)
 return volume
def model(boxes,angle=0.,offset=(0.,0.,0.)):
 doc,project,unused=make_box();doc.remove(unused)
 context=doc.by_type('IfcGeometricRepresentationContext')[0]
 basis=doc.create_entity('IfcAxis2Placement3D',Location=doc.create_entity('IfcCartesianPoint',Coordinates=offset),
  Axis=doc.create_entity('IfcDirection',DirectionRatios=(0.,0.,1.)),RefDirection=doc.create_entity('IfcDirection',DirectionRatios=(math.cos(angle),math.sin(angle),0.)))
 parent=doc.create_entity('IfcLocalPlacement',RelativePlacement=basis);products=[]
 for b in boxes:
  profile=doc.create_entity('IfcRectangleProfileDef',ProfileType='AREA',XDim=float(b[3]-b[0]),YDim=float(b[4]-b[1]))
  solid=doc.create_entity('IfcExtrudedAreaSolid',SweptArea=profile,
   Position=doc.create_entity('IfcAxis2Placement3D',Location=doc.create_entity('IfcCartesianPoint',Coordinates=(0.,0.,0.))),
   ExtrudedDirection=doc.create_entity('IfcDirection',DirectionRatios=(0.,0.,1.)),Depth=float(b[5]-b[2]))
  body=doc.create_entity('IfcShapeRepresentation',ContextOfItems=context,RepresentationIdentifier='Body',RepresentationType='SweptSolid',Items=[solid])
  place=doc.create_entity('IfcLocalPlacement',PlacementRelTo=parent,RelativePlacement=doc.create_entity('IfcAxis2Placement3D',
   Location=doc.create_entity('IfcCartesianPoint',Coordinates=(float((b[0]+b[3])/2),float((b[1]+b[4])/2),float(b[2])))))
  products.append(doc.create_entity('IfcWall',GlobalId=ifcopenshell.guid.new(),Name='Synthetic union operand',
   ObjectPlacement=place,Representation=doc.create_entity('IfcProductDefinitionShape',Representations=[body])))
 return doc,products
cases=[
 ('overlap',[(0,0,0,2,3,4),(1,0,0,3,3,4)],0.,(0.,0.,0.)),
 ('containment',[(0,0,0,2,3,4),(.5,.5,.5,1,2,3)],0.,(0.,0.,0.)),
 ('duplicate',[(0,0,0,2,3,4)]*2,0.,(0.,0.,0.)),
 ('face_touch',[(0,0,0,2,3,4),(2,0,0,4,3,4)],0.,(0.,0.,0.)),
 ('edge_touch',[(0,0,0,2,3,4),(2,3,0,4,6,4)],0.,(0.,0.,0.)),
 ('disjoint',[(0,0,0,2,3,4),(4,0,0,6,3,4)],0.,(0.,0.,0.)),
 ('triple',[(0,0,0,2,3,4),(1,0,0,3,3,4),(1,1,1,4,4,5)],0.,(0.,0.,0.)),
 ('rotated37',[(0,0,0,2,3,4),(1,0,0,3,3,4)],math.radians(37),(0.,0.,0.)),
 ('large_offset',[(0,0,0,2,3,4),(1,0,0,3,3,4)],0.,(5e8,3e9,0.)),
]
rows=[]
settings=ifcopenshell.geom.settings()
settings.set('boolean-attempt-2d',False)
for name,boxes,angle,offset in cases:
 doc,products=model(boxes,angle,offset);p=out/(name+'.ifc');doc.write(str(p));meshes=[]
 for product in products:
  shape=ifcopenshell.geom.create_shape(settings,product);v=np.array(shape.geometry.verts).reshape(-1,3);f=np.array(shape.geometry.faces).reshape(-1,3)
  assert mesh_measurements(v,f)['volume_m3'] is not None
  matrix=get_shape_matrix(shape);v=v@matrix[:3,:3].T+matrix[:3,3];meshes.append((v,f))
 origin=np.min(np.concatenate([v for v,f in meshes]),axis=0)
 operands=[m.Manifold(m.Mesh64(np.ascontiguousarray(v-origin,dtype=np.float64),np.ascontiguousarray(f,dtype=np.uint64))) for v,f in meshes]
 assert all(x.status()==m.Error.NoError for x in operands)
 result=m.Manifold.batch_boolean(operands,m.OpType.Add);mesh=result.to_mesh64();checked=mesh_measurements(mesh.vert_properties[:,:3],mesh.tri_verts)
 expected=oracle(boxes);actual=result.volume();row={'case':name,'ids':[p.id() for p in products],'source_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
 'expected_m3':expected,'actual_m3':actual,'absolute_error_m3':abs(actual-expected),'native_status':str(result.status()),
 'product_topology_status':checked['topology'],'product_volume_m3':checked['volume_m3'],'numeric_passed':abs(actual-expected)<=1e-8}
 rows.append(row)
(out/'prototype-windows-v1.json').write_text(json.dumps({'version':'3.5.4','tolerance_m3':1e-8,'cases':rows},indent=2))
print(json.dumps(rows))
assert all(r['numeric_passed'] for r in rows)
