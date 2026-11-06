"""Independent contact witnesses: edge/triangle Cramer's rule, not product clipping.
Only diagnoses the reported first pair / vertex; not a whole-model validity oracle.
"""
import argparse,hashlib,json
from fractions import Fraction as F
from pathlib import Path
import ifcopenshell
import ifcopenshell.geom
import numpy as np

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('source',type=Path,help='Unmodified public Duplex IFC')
parser.add_argument('record',type=Path,help='Actual current cad-inspections JSON export')
parser.add_argument('output',type=Path,help='New output directory; existing directories are refused')
args=parser.parse_args();source=args.source;output=args.output
source_hash=hashlib.sha256(source.read_bytes()).hexdigest()
assert source_hash=='b347a2c8aa8fff6db896a4417a9c50c22ac0ccd7c5cfc22b99b8d29336c606ed','Unexpected reference bytes'
record=json.loads(args.record.read_text(encoding='utf-8'))
assert record['source']['hash']==source_hash,'Record refers to a different source'
assert record['status']=='parsed' and record['result']['format']=='IFC','Current parsed record required'
output.mkdir(parents=True,exist_ok=False)
doc=ifcopenshell.open(str(source));settings=ifcopenshell.geom.settings()
for k,v in record['result']['ifc_geometry']['settings'].items():settings.set(k,v)
def minus(a,b):return tuple(x-y for x,y in zip(a,b))
def determinant(a,b,c):return a[0]*(b[1]*c[2]-b[2]*c[1])-a[1]*(b[0]*c[2]-b[2]*c[0])+a[2]*(b[0]*c[1]-b[1]*c[0])
def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def o(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
def edges(t):return list(zip(t,t[1:]+t[:1]))
def interpolate(a,b,t):return tuple(x+t*(y-x) for x,y in zip(a,b))
def on_segment(p,a,b):return not any(cross(minus(p,a),minus(b,a))) and all(min(x,y)<=z<=max(x,y) for x,y,z in zip(a,b,p))
def contact_points(a,b):
 points=[]
 # Solve p + t(q-p) = b0 + u(b1-b0) + v(b2-b0) independently.
 for lhs,rhs in [(a,b),(b,a)]:
  for p,q in edges(lhs):
   columns=(minus(q,p),minus(rhs[0],rhs[1]),minus(rhs[0],rhs[2]));right=minus(rhs[0],p)
   det=determinant(*columns)
   if det:
    t=determinant(right,columns[1],columns[2])/det
    u=determinant(columns[0],right,columns[2])/det;v=determinant(columns[0],columns[1],right)/det
    if 0<=t<=1 and u>=0 and v>=0 and u+v<=1:points.append(interpolate(p,q,t))
 n=cross(minus(a[1],a[0]),minus(a[2],a[0]))
 if all(sum(x*y for x,y in zip(n,minus(p,a[0])))==0 for p in b):
  drop=max(range(3),key=lambda k:abs(n[k]));axes=[k for k in range(3) if k!=drop]
  project=lambda p:tuple(p[k] for k in axes)
  for lhs,rhs in [(a,b),(b,a)]:
   tri=list(map(project,rhs));sign=1 if o(*tri)>0 else -1
   for p in lhs:
    if all(sign*o(x,y,project(p))>=0 for x,y in edges(tri)):points.append(p)
  for p,q in edges(a):
   for r,s in edges(b):
    pp,qq,rr,ss=map(project,[p,q,r,s]);d=minus(qq,pp);e=minus(ss,rr);right=minus(rr,pp)
    den=d[0]*e[1]-d[1]*e[0]
    if den:
     t=(right[0]*e[1]-right[1]*e[0])/den;u=(right[0]*d[1]-right[1]*d[0])/den
     if 0<=t<=1 and 0<=u<=1:points.append(interpolate(p,q,t))
 return points

checks=[]
for row in record['result']['ifc_geometry']['objects']:
 topology=row.get('topology',{})
 if topology.get('status')!='rejected':continue
 element=doc.by_id(row['id']);body=doc.by_id(row['representation_ids'][0]);shape=ifcopenshell.geom.create_shape(settings,element,body)
 raw=np.asarray(shape.geometry.verts).reshape((-1,3));faces=np.asarray(shape.geometry.faces).reshape((-1,3))
 vertices,remap=np.unique(raw,axis=0,return_inverse=True);faces=remap[faces]
 result={'id':row['id'],'type':row['type'],'reason':topology['reason']}
 if topology['reason']=='triangle_intersection_or_nonlocal_contact':
  i,j=topology['triangle_indices'];v=lambda idx:tuple(F(float(x)) for x in vertices[idx])
  a,b=[list(map(v,faces[idx])) for idx in [i,j]];common=list(set(a)&set(b))
  points=contact_points(a,b)
  outside=lambda p:not common or (p!=common[0] if len(common)==1 else not on_segment(p,*common))
  witness=next((p for p in points if outside(p)),None)
  result.update(passed=witness is not None,triangle_indices=[i,j],common_vertices=len(common),
                witness=[str(x) for x in witness] if witness else None,triangles=[[[str(x) for x in p] for p in t] for t in [a,b]])
 elif topology['reason']=='non_manifold_vertex':
  vertex=topology['vertex_index'];link={}
  for triangle in faces:
   if vertex not in triangle:continue
   a,b=[int(v) for v in triangle if v!=vertex];link.setdefault(a,set()).add(b);link.setdefault(b,set()).add(a)
  unseen=set(link);components=0
  while unseen:
   components+=1;stack=[unseen.pop()]
   while stack:
    for neighbor in link[stack.pop()]:
     if neighbor in unseen:unseen.remove(neighbor);stack.append(neighbor)
  result.update(passed=components>1,vertex_index=vertex,link_components=components)
 else:result['passed']=False
 checks.append(result)
with (output/'independent-rejection-witnesses.json').open('x',encoding='utf-8') as stream:json.dump(checks,stream,indent=2)
summary={'count':len(checks),'passed':sum(r['passed'] for r in checks),'failures':[r['id'] for r in checks if not r['passed']],
 'method':'Exact rational edge/triangle Cramer solves and projected edge intersections; independent vertex-link graph. No product topology predicates imported.',
 'witnesses_sha256':hashlib.sha256((output/'independent-rejection-witnesses.json').read_bytes()).hexdigest()}
(output/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8');print(json.dumps(summary))
assert len(checks)==45 and all(r['passed'] for r in checks),'Rejection lacks independent witness; retain and investigate'
