"""Pre-implementation independent opening-union probes. No product mutation."""
import hashlib,itertools,json,sys,time
from pathlib import Path
repo=Path.cwd();out=Path(__file__).resolve().parent
sys.path[:0]=[str(repo),str(repo/'tests')]
import ifcopenshell
from test_ifc_measurements import make_box
from backend.cad_worker import parse_ifc
HOST=(-1.,1.,-1.5,1.5,0.,4.)
def axis(doc,xyz):
    return doc.create_entity('IfcAxis2Placement3D',Location=doc.create_entity('IfcCartesianPoint',Coordinates=tuple(map(float,xyz))))
def hole(doc,wall,bounds):
    x0,x1,y0,y1,z0,z1=bounds
    profile=doc.create_entity('IfcRectangleProfileDef',ProfileType='AREA',XDim=float(x1-x0),YDim=float(y1-y0))
    item=doc.create_entity('IfcExtrudedAreaSolid',SweptArea=profile,Position=axis(doc,((x0+x1)/2,(y0+y1)/2,z0)),
      ExtrudedDirection=doc.create_entity('IfcDirection',DirectionRatios=(0.,0.,1.)),Depth=float(z1-z0))
    body=doc.create_entity('IfcShapeRepresentation',ContextOfItems=wall.Representation.Representations[0].ContextOfItems,
      RepresentationIdentifier='Body',RepresentationType='SweptSolid',Items=[item])
    opening=doc.create_entity('IfcOpeningElement',GlobalId=ifcopenshell.guid.new(),ObjectPlacement=wall.ObjectPlacement,
      Representation=doc.create_entity('IfcProductDefinitionShape',Representations=[body]))
    doc.create_entity('IfcRelVoidsElement',GlobalId=ifcopenshell.guid.new(),RelatingBuildingElement=wall,RelatedOpeningElement=opening)
    return opening
def union_inside_host(boxes):
    axes=[sorted(set([HOST[2*i],HOST[2*i+1]]+[max(HOST[2*i],min(HOST[2*i+1],b[j])) for b in boxes for j in (2*i,2*i+1)])) for i in range(3)]
    volume=0.
    for x,y,z in itertools.product(*[list(zip(a,a[1:])) for a in axes]):
        mids=[(a+b)/2 for a,b in (x,y,z)]
        if any(all(b[2*i]<m<b[2*i+1] for i,m in enumerate(mids)) for b in boxes):
            volume+=(x[1]-x[0])*(y[1]-y[0])*(z[1]-z[0])
    return volume
cases={
 'single_through':[(-.25,.25,-.5,.5,-1.,5.)],
 'overlapping':[(-.5,.25,-.5,.5,0.,4.),(-.25,.5,-.5,.5,0.,4.)],
 'partly_outside':[(.5,1.5,-.5,.5,-1.,5.)],
 'fully_outside':[(2.,3.,-.5,.5,0.,4.)],
 'touching':[(-.5,0.,-.5,.5,0.,4.),(0.,.5,-.5,.5,0.,4.)],
 'identical_two_openings':[(-.25,.25,-.5,.5,0.,4.)]*2,
 'duplicate_void_relation':[(-.25,.25,-.5,.5,0.,4.)],
 'host_fully_removed':[(-2.,2.,-2.,2.,-1.,5.)],
}
rows=[]
for name,boxes in cases.items():
    doc,_,wall=make_box()
    openings=[hole(doc,wall,b) for b in boxes]
    if name=='duplicate_void_relation':
        doc.create_entity('IfcRelVoidsElement',GlobalId=ifcopenshell.guid.new(),RelatingBuildingElement=wall,RelatedOpeningElement=openings[0])
    path=out/(name+'.ifc');doc.write(str(path));digest=hashlib.sha256(path.read_bytes()).hexdigest()
    start=time.perf_counter()
    try:
        parsed=parse_ifc(path);row=next(r for r in parsed['ifc_geometry']['objects'] if r['id']==wall.id())
        actual=row.get('volume_m3');status=row['status'];error=None
    except Exception as exc:
        actual=None;status='exception';error=type(exc).__name__+': '+str(exc)
    expected=24.-union_inside_host(boxes)
    rows.append({'case':name,'file':path.name,'sha256':digest,'host_bounds':HOST,'openings':boxes,'independent_geometric_net_m3':expected,
      'actual_volume_m3':actual,'status':status,'error':error,'within_1e-9':actual is not None and abs(actual-expected)<=1e-9,
      'relationship_review_required':name in {'identical_two_openings','duplicate_void_relation'},
      'original_unchanged':hashlib.sha256(path.read_bytes()).hexdigest()==digest,'seconds':time.perf_counter()-start})
with (out/'probe-windows-v1.json').open('x',encoding='utf-8') as f:json.dump({'source_commit':'bf237af3b8d0ef9f0077b4a0614ffe2f397a83b1','cases':rows,
 'limits':'Synthetic trusted probes, direct native parser; not isolated API acceptance or certified professional net quantity.'},f,indent=2)
print(json.dumps([{'case':r['case'],'expected':r['independent_geometric_net_m3'],'actual':r['actual_volume_m3'],'status':r['status']} for r in rows]))
