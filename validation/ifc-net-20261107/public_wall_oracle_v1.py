"""Independent Decimal intersection for the one changed public rectangular wall."""
import hashlib,json,sys
from decimal import Decimal as D
from pathlib import Path
source,api,output=map(Path,sys.argv[1:])
raw=source.read_bytes();digest=hashlib.sha256(raw).hexdigest()
assert digest=='b347a2c8aa8fff6db896a4417a9c50c22ac0ccd7c5cfc22b99b8d29336c606ed'
import re
rows={int(n):(kind,line) for n,kind,line in re.findall(r'^#(\d+)=(\w+)\((.*)\);',raw.decode('utf-8-sig'),re.M)}
def fields(text):
    result=[];start=depth=0;quote=False
    for i,c in enumerate(text):
        if c=="'":quote=not quote
        if quote:continue
        if c=='(':depth+=1
        if c==')':depth-=1
        if c==',' and depth==0:result.append(text[start:i].strip());start=i+1
    return result+[text[start:].strip()]
def entity(n,kind):
    k,text=rows[n];assert k==kind;return fields(text)
def point(n):return tuple(map(D,entity(n,'IFCCARTESIANPOINT')[0][1:-1].split(',')))
def direction(n):return tuple(map(D,entity(n,'IFCDIRECTION')[0][1:-1].split(',')))
assert entity(15,'IFCSIUNIT')[1:]==['.LENGTHUNIT.','$','.METRE.']
assert entity(8371,'IFCLOCALPLACEMENT')==['#5890','#8370']
assert entity(8370,'IFCAXIS2PLACEMENT3D')==['#8369','$','$']
assert entity(5897,'IFCAXIS2PLACEMENT3D')==['#3','$','$']
assert entity(8365,'IFCAXIS2PLACEMENT3D')==['#3','#7','#9']
assert point(3)==(D(0),)*3
assert direction(7)==(0,1,0) and direction(9)==(0,0,1)
assert direction(12)==(-1,0) and direction(13)==(0,1)
assert entity(5895,'IFCAXIS2PLACEMENT2D')==['#5894','#12']
assert entity(8363,'IFCAXIS2PLACEMENT2D')==['#8362','#13']
host=entity(5898,'IFCEXTRUDEDAREASOLID');opening=entity(8366,'IFCEXTRUDEDAREASOLID')
assert host[:3]==['#5896','#5897','#9'] and opening[:3]==['#8364','#8365','#9']
hp=entity(5896,'IFCRECTANGLEPROFILEDEF');op=entity(8364,'IFCRECTANGLEPROFILEDEF')
assert hp[2]=='#5895' and op[2]=='#8363'
w,t,h=D(hp[3]),D(hp[4]),D(host[3]);ow,oh,od=D(op[3]),D(op[4]),D(opening[3])
hx,hy=point(5894);ox,oy,oz=point(8369);pcx,pcy=point(8362)
host_bounds=[(hx-w/2,hx+w/2),(hy-t/2,hy+t/2),(D(0),h)]
# Explicit orthonormal axes above: solid X -> host Z; solid Y -> host X;
# profile X -> solid Y; profile Y -> -solid X; extrusion -> host Y.
opening_bounds=[(ox+pcy-ow/2,ox+pcy+ow/2),(oy,oy+od),(oz+pcx-oh/2,oz+pcx+oh/2)]
intersection=D(1)
for (a,b),(c,d) in zip(host_bounds,opening_bounds):intersection*=max(D(0),min(b,d)-max(a,c))
expected=w*t*h-intersection
record=json.loads(api.read_text(encoding='utf-8'));assert record['source']['hash']==digest
actual=next(r for r in record['result']['ifc_geometry']['objects'] if r['id']==5903)['volume_m3']
error=abs(D(str(actual))-expected) if actual is not None else None
receipt={'source_sha256':digest,'entity':5903,'opening_entity':8372,'host_bounds':[[str(x) for x in r] for r in host_bounds],
'opening_bounds':[[str(x) for x in r] for r in opening_bounds],'gross_m3':str(w*t*h),'intersection_m3':str(intersection),
'expected_m3':str(expected),'actual_m3':actual,'absolute_error_m3':str(error),'tolerance_m3':'1e-10','passed':error is not None and error<=D('1e-10'),
'method':'Raw STEP fields, explicit orthonormal axis mapping, Decimal box intersection; no native geometry used to generate gold',
'limits':'One fixed rectangular host/opening pair only; not general complex net-quantity certification.'}
with output.open('x',encoding='utf-8') as f:json.dump(receipt,f,indent=2)
print(json.dumps(receipt))
assert receipt['passed']
