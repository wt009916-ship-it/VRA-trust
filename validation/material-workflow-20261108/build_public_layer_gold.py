"""Reproduce the fixed public wall layer gold from independent raw-STEP receipts."""
import json,sys
from decimal import Decimal as D
from pathlib import Path
wall_file,material_file,target=map(Path,sys.argv[1:])
b=json.loads(wall_file.read_text(encoding='utf-8'));g=json.loads(material_file.read_text(encoding='utf-8'))
assert b['source_sha256']==g['source_sha256']
r=next(x for x in g['relations'] if 5903 in x['owner_ids'])
assert r['direction']=='AXIS2' and r['sense']=='NEGATIVE'
host=[tuple(map(D,x)) for x in b['host_bounds']];hole=[tuple(map(D,x)) for x in b['opening_bounds']]
cursor=D(r['offset']);rows=[]
for layer in r['layers']:
    end=cursor-D(layer['thickness_m']);lo,hi=sorted([cursor,end]);cursor=end
    clipped=[host[0],(max(host[1][0],lo),min(host[1][1],hi)),host[2]]
    gross=D(1);cut=D(1)
    for (a,z),(c,d) in zip(clipped,hole):
        gross*=max(D(0),z-a);cut*=max(D(0),min(z,d)-max(a,c))
    rows.append({'layer_id':layer['layer_id'],'material_id':layer['material_id'],'bounds_y_m':[str(lo),str(hi)],
                 'expected_volume_m3':str(gross-cut),'gross_volume_m3':str(gross),'opening_intersection_m3':str(cut)})
out={'source_sha256':g['source_sha256'],'product_id':5903,
     'method':'Raw STEP wall/opening orthogonal box oracle + declared material planes; Decimal independent of native clipping',
     'layers':rows,'tolerance_m3':'1e-9','quantity_kind':'layer envelope, not solid fraction or purchased material'}
with target.open('x',encoding='utf-8') as f:json.dump(out,f,indent=2)
