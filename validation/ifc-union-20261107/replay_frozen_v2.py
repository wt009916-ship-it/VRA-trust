import hashlib,json,os,sys
from pathlib import Path
out=Path(__file__).resolve().parent
platform='linux' if sys.platform=='linux' else 'windows'
plan=json.loads((out/('linux-source-v1.json' if platform=='linux' else 'candidate-source-v1.json')).read_text())
root=Path(plan['root']);sys.path.insert(0,str(root))
from backend.ifc_union import measure_union
for item in plan['files']:
 if item['path'].startswith('backend/'):assert hashlib.sha256((root/item['path']).read_bytes()).hexdigest()==item['sha256']
gold=json.loads((out/'prototype-windows-v1.json').read_text());rows=[]
for case in gold['cases']:
 p=out/(case['case']+'.ifc');assert hashlib.sha256(p.read_bytes()).hexdigest()==case['source_sha256']
 r=measure_union(p,case['ids']);value=r['union_volume_m3']
 passed=(r['reason']=='union_topology_unverified' and value is None) if case['case']=='edge_touch' else value is not None and abs(value-case['expected_m3'])<=1e-8
 rows.append({'case':case['case'],'source_sha256':case['source_sha256'],'expected_m3':case['expected_m3'],'criterion_passed':passed,'result':r})
record={'platform':platform,'uid':os.getuid() if hasattr(os,'getuid') else None,'source':str(root),'cases':rows}
with (out/('kernel-'+platform+'-v2.json')).open('x',encoding='utf-8') as f:json.dump(record,f,indent=2)
print(json.dumps({'platform':platform,'passed':sum(r['criterion_passed'] for r in rows),'cases':len(rows),'numeric':8,'refused':1}))
assert all(r['criterion_passed'] for r in rows)
