from pathlib import Path
import json,hashlib,re
from decimal import Decimal as D
HERE=Path(__file__).parent;OUT=Path('C:/Users/18483/AppData/Local/Temp/vra-slab-layers-20261108')
R=Path('C:/Users/18483/AppData/Local/Temp/vra-drawing-components-20261108')
raw=Path('D:/稀土agent-稀土制暖全流程/outputs/vra-m2-intake-20261108/Duplex_A_20110907.ifc').read_bytes()
code=(R/'validation/ifc-union-20261107/public_oracle_v2.py').read_text(encoding='utf-8').split("types={'IFCWALL'")[0]
scope={'raw':raw,'D':D,'re':re};exec(code[code.index('def fields(s):'):],scope)
rows,ref,refs,vec,axis,mul,placement=[scope[k] for k in ['rows','ref','refs','vec','axis','mul','placement']]
gold=json.loads((OUT/'frozen-public-gold-v2.json').read_text());selected=gold['cases']
boxes=[]
for expected in selected:
    a=rows[expected['id']][1];e=rows[expected['solid_id']][1];pk,p=ref(e[0])
    if pk=='IFCARBITRARYCLOSEDPROFILEDEF':
        _,line=ref(p[2]);points=[vec(r) for r in refs(line[0])]
    else:
        assert pk=='IFCRECTANGLEPROFILEDEF'
        pm=axis(p[2]);points=[tuple(sum(pm[i][j]*v for j,v in enumerate([x,y,D(0),D(1)])) for i in range(2)) for x in [-D(p[3])/2,D(p[3])/2] for y in [-D(p[4])/2,D(p[4])/2]]
    matrix=mul(placement(a[5]),axis(e[1]));vertices=[]
    for x,y in points:
        for z in [D(0),D(e[3])]:vertices.append([sum(matrix[i][j]*v for j,v in enumerate([x,y,z,D(1)])) for i in range(3)])
    boxes.append([min(v[i] for v in vertices) for i in range(3)]+[max(v[i] for v in vertices) for i in range(3)])
import itertools
pairs=[(a,b) for a,b in itertools.combinations(range(len(boxes)),2) if any(min(boxes[a][i+3],boxes[b][i+3])<=max(boxes[a][i],boxes[b][i]) for i in range(3))]
assert pairs,'No disjoint pair established'
indices=pairs[0];selected=[selected[i] for i in indices];boxes=[boxes[i] for i in indices]
total=sum(D(r['host_volume_m3']) for r in selected)
browsergold={'source_sha256':hashlib.sha256(raw).hexdigest(),'selected_ids':[r['id'] for r in selected],
 'cases':[{'union_envelope_m3':str(total)}],'absolute_tolerance_m3':'1e-7','independent_world_boxes':boxes,'union_reason':'First pair whose raw STEP world axis-permutation boxes are disjoint; sum of independent profile volumes',
 'first_attempt':'First two IDs were not proved disjoint by bounding boxes; assertion stopped before starting service or computing union. Use declared geometric eligibility across catalog, not application outcomes.'}
(OUT/'browser-gold.json').write_text(json.dumps(browsergold,default=str,indent=2))
(OUT/'browser').mkdir(exist_ok=False)
s=(HERE/'collection_browser_runtime_v2.py').read_text(encoding='utf-8')
s=s.replace('vra-material-collection-public-20261108/browser-v2','vra-slab-layers-20261108/browser').replace("(OUT.parent/'frozen-gold.json')", "(OUT.parent/'browser-gold.json')")
s=s.replace("'material_collection_ui'", "'slab_collection_ui'").replace('公开IFC多墙计量验收','公开IFC楼板材料验收').replace('隔离多墙验收','隔离楼板验收')
(HERE/'slab_browser_runtime.py').write_text(s,encoding='utf-8')
print(json.dumps({'selected':browsergold['selected_ids'],'expected_union_m3':str(total),'boxes':boxes},default=str))
