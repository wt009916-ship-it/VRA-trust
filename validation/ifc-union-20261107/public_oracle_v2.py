"""Independent raw STEP/Decimal axis-aligned prism union oracle; no geometry library."""
import hashlib,itertools,json,re,sys
from decimal import Decimal as D
from pathlib import Path
out=Path(__file__).resolve().parent
source=Path(sys.argv[1])
raw=source.read_bytes()
assert hashlib.sha256(raw).hexdigest()=='b347a2c8aa8fff6db896a4417a9c50c22ac0ccd7c5cfc22b99b8d29336c606ed'
def fields(s):
 items=[];start=depth=0;quote=False;i=0
 while i<len(s):
  c=s[i]
  if c=="'":
   if quote and i+1<len(s) and s[i+1]=="'":i+=2;continue
   quote=not quote
  elif not quote:
   if c=='(':depth+=1
   elif c==')':depth-=1
   elif c==',' and depth==0:items.append(s[start:i]);start=i+1
  i+=1
 return items+[s[start:]]
rows={int(i):(k,fields(s)) for i,k,s in re.findall(r'^#(\d+)=(\w+)\((.*)\);',raw.decode('utf-8-sig'),re.M)}
def ref(s):return rows[int(s[1:])]
def refs(s):return fields(s[1:-1])
def vec(s,default=None):
 if s=='$':return default
 k,a=ref(s);assert k in {'IFCCARTESIANPOINT','IFCDIRECTION'}
 return tuple(map(D,refs(a[0])))
def ident():return [[D(int(i==j)) for j in range(4)] for i in range(4)]
def mul(a,b):return [[sum(a[i][k]*b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]
def axis(s):
 if s=='$':return ident()
 k,a=ref(s);m=ident();t=vec(a[0])
 if k=='IFCAXIS2PLACEMENT2D':
  x=vec(a[1],(D(1),D(0)));assert sum(v*v for v in x)==1 and all(v in (-1,0,1) for v in x)
  x=(*x,D(0));z=(D(0),D(0),D(1));t=(*t,D(0))
 else:
  assert k=='IFCAXIS2PLACEMENT3D';z=vec(a[1],(D(0),D(0),D(1)));x=vec(a[2],(D(1),D(0),D(0)))
  assert sum(v*v for v in x)==sum(v*v for v in z)==1 and sum(a*b for a,b in zip(x,z))==0
  assert all(v in (-1,0,1) for v in x+z)
 y=(z[1]*x[2]-z[2]*x[1],z[2]*x[0]-z[0]*x[2],z[0]*x[1]-z[1]*x[0])
 for i in range(3):m[i]=[x[i],y[i],z[i],t[i]]
 return m
def placement(s,seen=()):
 if s=='$':return ident()
 assert s not in seen and len(seen)<128
 k,a=ref(s);assert k=='IFCLOCALPLACEMENT'
 return mul(placement(a[0],(*seen,s)),axis(a[1]))
assert rows[15][1][1:]==['.LENGTHUNIT.','$','.METRE.']
hosts={a[4] for k,a in rows.values() if k=='IFCRELVOIDSELEMENT'}
types={'IFCWALL','IFCWALLSTANDARDCASE','IFCBEAM','IFCCOLUMN','IFCSLAB','IFCFOOTING','IFCMEMBER','IFCCOVERING','IFCDOOR','IFCWINDOW'}
boxes=[];excluded=[]
for eid,(kind,a) in rows.items():
 if kind not in types or '#'+str(eid) in hosts:continue
 try:
  k,p=ref(a[6]);assert k=='IFCPRODUCTDEFINITIONSHAPE'
  bodies=[ref(b)[1] for b in refs(p[2]) if ref(b)[1][1]=="'Body'"];assert len(bodies)==1
  solids=refs(bodies[0][3]);assert len(solids)==1
  k,e=ref(solids[0]);assert k=='IFCEXTRUDEDAREASOLID' and vec(e[2])==(0,0,1)
  k,p=ref(e[0]);assert k=='IFCRECTANGLEPROFILEDEF'
  width,height,depth=D(p[3]),D(p[4]),D(e[3]);assert min(width,height,depth)>0
  matrix=mul(mul(placement(a[5]),axis(e[1])),axis(p[2]))
  corners=[tuple(sum(matrix[i][j]*point[j] for j in range(4)) for i in range(3)) for point in
   ((x,y,z,D(1)) for x,y,z in itertools.product((-width/2,width/2),(-height/2,height/2),(D(0),depth)))]
  box=[min(c[i] for c in corners) for i in range(3)]+[max(c[i] for c in corners) for i in range(3)]
  assert (box[3]-box[0])*(box[4]-box[1])*(box[5]-box[2])==width*height*depth
  boxes.append({'id':eid,'type':kind,'box':box,'volume':width*height*depth,'extrusion':int(solids[0][1:])})
 except (AssertionError,KeyError,ValueError,IndexError):excluded.append(eid)
def union(items):
 cuts=[sorted({v for b in items for v in (b['box'][i],b['box'][i+3])}) for i in range(3)];answer=D(0)
 for cell in itertools.product(*[list(zip(c,c[1:])) for c in cuts]):
  mid=[sum(pair)/2 for pair in cell]
  if any(all(b['box'][i]<mid[i]<b['box'][i+3] for i in range(3)) for b in items):
   answer+=(cell[0][1]-cell[0][0])*(cell[1][1]-cell[1][0])*(cell[2][1]-cell[2][0])
 return answer
groups=[];overlap=separate=near=0
for a,b in itertools.combinations(boxes,2):
 intersection=D(1)
 for i in range(3):intersection*=max(D(0),min(a['box'][i+3],b['box'][i+3])-max(a['box'][i],b['box'][i]))
 if intersection>D('1e-8') and overlap<6:overlap+=1
 elif D(0)<intersection<=D('1e-8') and near<3:near+=1
 elif intersection==0 and separate<3:separate+=1
 else:continue
 groups.append({'ids':[a['id'],b['id']],'operands':[a,b],'union_m3':union([a,b]),'sum_m3':a['volume']+b['volume'],'overlap_m3':intersection})
record={'sha256':hashlib.sha256(raw).hexdigest(),'method':'Decimal raw STEP axis permutation and interval partition; no native mesh oracle',
 'supported_prisms':len(boxes),'excluded_ids':excluded,'positive_overlap_pairs':overlap,'zero_overlap_pairs':separate,'sub_1e8_overlap_pairs':near,'groups':groups}
with (out/'public-gold-v2.json').open('x',encoding='utf-8') as f:json.dump(record,f,default=str,indent=2)
print(json.dumps({k:v for k,v in record.items() if k not in ('excluded_ids','groups')}))
