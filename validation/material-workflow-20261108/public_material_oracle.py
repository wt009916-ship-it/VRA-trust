"""Frozen Duplex material declarations from raw STEP, independent of the IFC parser."""
import hashlib,json,re,sys
from decimal import Decimal
from pathlib import Path
source,target=map(Path,sys.argv[1:])
raw=source.read_bytes();digest=hashlib.sha256(raw).hexdigest()
assert digest=='b347a2c8aa8fff6db896a4417a9c50c22ac0ccd7c5cfc22b99b8d29336c606ed'
entities={int(n):(kind,body) for n,kind,body in re.findall(r'^#(\d+)=(\w+)\((.*)\);',raw.decode('utf-8-sig'),re.M)}
def fields(body):
    result=[];start=depth=0;quoted=False;i=0
    while i<len(body):
        c=body[i]
        if c=="'":
            if quoted and i+1<len(body) and body[i+1]=="'":i+=2;continue
            quoted=not quoted
        elif not quoted:
            if c=='(':depth+=1
            elif c==')':depth-=1
            elif c==',' and depth==0:result.append(body[start:i]);start=i+1
        i+=1
    assert not quoted and depth==0
    return result+[body[start:]]
def entity(ident,kind):
    actual,body=entities[ident];assert actual==kind
    return fields(body)
def refs(text):return [int(x) for x in re.findall(r'#(\d+)',text)]
def string(text):
    assert text.startswith("'") and text.endswith("'") and '\\' not in text
    return text[1:-1].replace("''", "'")
# Unit assertion is deliberately specific to the frozen source, no default unit.
assert entity(15,'IFCSIUNIT')[1:]==['.LENGTHUNIT.','$','.METRE.']
rows=[]
for rid,(kind,body) in entities.items():
    if kind!='IFCRELASSOCIATESMATERIAL':continue
    f=fields(body);mid=refs(f[5])[0];mk,mb=entities[mid]
    row={'relation_id':rid,'owner_ids':refs(f[4]),'material_id':mid,'material_type':mk,'layers':[]}
    if mk=='IFCMATERIALLAYERSETUSAGE':
        u=fields(mb);ls=refs(u[0])[0];lf=entity(ls,'IFCMATERIALLAYERSET')
        row.update(layer_set_id=ls,direction=u[1].strip('.'),sense=u[2].strip('.'),offset=str(Decimal(u[3])))
        for lid in refs(lf[0]):
            layer=entity(lid,'IFCMATERIALLAYER');material=refs(layer[0])[0]
            row['layers'].append({'layer_id':lid,'material_id':material,'name':string(entity(material,'IFCMATERIAL')[0]),'thickness_m':str(Decimal(layer[1]))})
    else:
        assert mk=='IFCMATERIAL';row['name']=string(fields(mb)[0])
    rows.append(row)
assert len(rows)==92
record={'source_sha256':digest,'method':'Raw STEP entity fields + Decimal; no IfcOpenShell or application code for expected material facts','unit_assertion':'#15 IFCSIUNIT LENGTHUNIT METRE','relations':rows,'quantity_truth':None,'scope':'Material source/ordered-layer declarations only; no net quantity validation'}
with target.open('x',encoding='utf-8') as f:json.dump(record,f,ensure_ascii=False,indent=2)
print(json.dumps({'relations':len(rows),'layer_rows':sum(len(r['layers']) for r in rows),'sha256':digest}))
