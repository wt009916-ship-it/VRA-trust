"""Fixed raw STEP/Decimal reference; no application or native geometry imports."""
from pathlib import Path
from hashlib import sha256
import json,itertools
from decimal import Decimal as D

REPO=Path('C:/Users/18483/AppData/Local/Temp/vra-drawing-components-20261108')
SOURCE=Path('D:/稀土agent-稀土制暖全流程/outputs/vra-m2-intake-20261108/Duplex_A_20110907.ifc')
OUT=Path('C:/Users/18483/AppData/Local/Temp/vra-material-collection-public-20261108');OUT.mkdir(exist_ok=False)
# Reuse inspected independent raw-STEP field/matrix definitions, not IFC code.
original=REPO/'validation/ifc-union-20261107/public_oracle_v2.py'
code=original.read_text(encoding='utf-8').split("types={'IFCWALL'")[0]
code=code[code.index('def fields(s):'):]
raw=SOURCE.read_bytes()
assert sha256(raw).hexdigest()=='b347a2c8aa8fff6db896a4417a9c50c22ac0ccd7c5cfc22b99b8d29336c606ed'
import re
scope={'raw':raw,'re':re,'D':D};exec(compile(code,'independent-step-definitions','exec'),scope)
rows,ref,refs,vec,axis,mul,placement=[scope[k] for k in ('rows','ref','refs','vec','axis','mul','placement')]
hosts=scope['hosts']

def bounds(box,matrix):
    corners=[tuple(sum(matrix[i][j]*p[j] for j in range(4)) for i in range(3)) for p in
             ((x,y,z,D(1)) for x,y,z in itertools.product(*[(box[i],box[i+3]) for i in range(3)]))]
    return [min(c[i] for c in corners) for i in range(3)]+[max(c[i] for c in corners) for i in range(3)]

def volume(b):return (b[3]-b[0])*(b[4]-b[1])*(b[5]-b[2])

def union(boxes):
    cuts=[sorted({v for b in boxes for v in (b[i],b[i+3])}) for i in range(3)]
    total=D(0)
    for cell in itertools.product(*[list(zip(c,c[1:])) for c in cuts]):
        mid=[sum(pair)/2 for pair in cell]
        if any(all(b[i]<mid[i]<b[i+3] for i in range(3)) for b in boxes):
            total+=(cell[0][1]-cell[0][0])*(cell[1][1]-cell[1][0])*(cell[2][1]-cell[2][0])
    return total

eligible=[];excluded=[]
for ident,(kind,a) in sorted(rows.items()):
    if kind not in {'IFCWALL','IFCWALLSTANDARDCASE'}:continue
    try:
        assert '#'+str(ident) not in hosts
        _,p=ref(a[6]);representations=[ref(r)[1] for r in refs(p[2])]
        bodies=[r for r in representations if r[1]=="'Body'"];axes=[r for r in representations if r[1]=="'Axis'"]
        assert len(bodies)==len(axes)==1 and len(refs(bodies[0][3]))==len(refs(axes[0][3]))==1
        k,line=ref(refs(axes[0][3])[0]);assert k=='IFCPOLYLINE'
        ps=[vec(p) for p in refs(line[0])];assert len(ps)==2 and len(ps[0])==len(ps[1])==2 and ps[1][0]>ps[0][0] and ps[0][1]==ps[1][1]
        k,e=ref(refs(bodies[0][3])[0]);assert k=='IFCEXTRUDEDAREASOLID' and vec(e[2])==(0,0,1)
        k,profile=ref(e[0]);assert k=='IFCRECTANGLEPROFILEDEF'
        w,h,depth=D(profile[3]),D(profile[4]),D(e[3]);assert min(w,h,depth)>0
        box=bounds([-w/2,-h/2,D(0),w/2,h/2,depth],mul(axis(e[1]),axis(profile[2])))
        assert volume(box)==w*h*depth
        bindings=[v for k,v in rows.values() if k=='IFCRELASSOCIATESMATERIAL' and '#'+str(ident) in refs(v[4])]
        assert len(bindings)==1
        k,usage=ref(bindings[0][5]);assert k=='IFCMATERIALLAYERSETUSAGE' and usage[1]=='.AXIS2.' and usage[2] in ('.POSITIVE.','.NEGATIVE.')
        k,layer_set=ref(usage[0]);assert k=='IFCMATERIALLAYERSET'
        cursor=ps[0][1]+D(usage[3]);local=[]
        for lid in refs(layer_set[0]):
            k,layer=ref(lid);assert k=='IFCMATERIALLAYER' and D(layer[1])>0
            k,material=ref(layer[0]);assert k=='IFCMATERIAL'
            end=cursor+D(layer[1])*(1 if usage[2]=='.POSITIVE.' else -1);lo,hi=sorted((cursor,end));cursor=end
            clipped=[box[0],max(box[1],lo),box[2],box[3],min(box[4],hi),box[5]]
            assert volume(clipped)>0
            local.append({'product_id':ident,'layer_id':int(lid[1:]),'material_id':int(layer[0][1:]),'box':bounds(clipped,placement(a[5]))})
        assert sum(volume(r['box']) for r in local)==volume(box)
        eligible.append({'product_id':ident,'layers':local})
    except (AssertionError,KeyError,ValueError,IndexError):excluded.append(ident)
assert len(eligible)>=4
selected=eligible[:4]
cases=[]
for indices in ((0,1),(2,3),(0,1,2,3)):
    chosen=[selected[i] for i in indices];layers=[r for p in chosen for r in p['layers']]
    groups={m:[r['box'] for r in layers if r['material_id']==m] for m in sorted({r['material_id'] for r in layers})}
    expected=[{'material_id':m,'source_sum_m3':sum(volume(b) for b in boxes),'union_envelope_m3':union(boxes)} for m,boxes in groups.items()]
    whole=union([r['box'] for r in layers]);total=sum(volume(r['box']) for r in layers)
    cross=sum(r['union_envelope_m3'] for r in expected)-whole
    cases.append({'ids':[p['product_id'] for p in chosen],'source_layers':layers,'materials':expected,
                  'sum_layer_envelope_m3':total,'union_envelope_m3':whole,'same_material_overlap_deduction_m3':total-whole,
                  'cross_material_overlap_m3':cross,'expect_conflict':cross>max(D('1e-9'),whole*D('1e-8'))})
record={'source_sha256':sha256(raw).hexdigest(),'reference_definition_sha256':sha256(original.read_bytes()).hexdigest(),
        'selection':'First four wall entity IDs meeting independent raw STEP axis-aligned prism + material layer + no void eligibility; before running application on this selection.',
        'eligible_count':len(eligible),'excluded_wall_ids':excluded,'selected_ids':[r['product_id'] for r in selected],
        'cases':cases,'absolute_tolerance_m3':'1e-7','training':False,
        'limits':'Public reference, not actual site survey. This oracle covers orthogonal prisms without openings only; synthetic opening tests are separate. Selection is geometry eligibility, not application performance.'}
(OUT/'frozen-gold.json').write_text(json.dumps(record,default=str,indent=2),encoding='utf-8')
print(json.dumps({'selected':record['selected_ids'],'eligible':len(eligible),'cases':len(cases),'expected_conflicts':[c['expect_conflict'] for c in cases]}),flush=True)
