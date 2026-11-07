import hashlib,json,sys
from pathlib import Path
out=Path(__file__).resolve().parent;plan=json.loads((out/'linux-source-v2.json').read_text());sys.path.insert(0,plan['root'])
from backend.ifc_union import measure_union
gold=json.loads((out/'extended-windows-v1.json').read_text());rows=[]
for case in gold['cases']:
 p=out/case['file'];assert hashlib.sha256(p.read_bytes()).hexdigest()==case['source_sha256']
 r=measure_union(p,case['ids']);value=r['union_volume_m3']
 rows.append({'case':case['case'],'source_sha256':case['source_sha256'],'expected_m3':case['expected_m3'],'tolerance_m3':case['tolerance_m3'],
 'actual_m3':value,'matched':value is not None and abs(value-case['expected_m3'])<=case['tolerance_m3'],'result':r})
with (out/'extended-linux-v1.json').open('x',encoding='utf-8') as f:json.dump({'cases':rows},f,indent=2)
print(json.dumps([{'case':r['case'],'matched':r['matched'],'actual_m3':r['actual_m3']} for r in rows]))
assert all(r['matched'] for r in rows)
