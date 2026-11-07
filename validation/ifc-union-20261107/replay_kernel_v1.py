import json,sys,hashlib
from pathlib import Path
out=Path(__file__).resolve().parent;repo=out.parents[1];sys.path[:0]=[str(out/'probe-installed'),str(repo)]
from backend.ifc_union import measure_union
gold=json.loads((out/'prototype-windows-v1.json').read_text());rows=[]
for case in gold['cases']:
 p=out/(case['case']+'.ifc');assert hashlib.sha256(p.read_bytes()).hexdigest()==case['source_sha256']
 result=measure_union(p,case['ids']);expected=case['expected_m3'];value=result['union_volume_m3']
 accepted=(result['reason']=='union_topology_unverified' and value is None) if case['case']=='edge_touch' else value is not None and abs(value-expected)<=1e-8
 rows.append({'case':case['case'],'expected_m3':expected,'criterion_passed':accepted,'result':result})
(out/'kernel-windows-v1.json').write_text(json.dumps(rows,indent=2))
print(json.dumps([{'case':r['case'],'passed':r['criterion_passed'],'status':r['result']['status'],'reason':r['result']['reason'],'volume':r['result']['union_volume_m3']} for r in rows]))
assert all(r['criterion_passed'] for r in rows)
