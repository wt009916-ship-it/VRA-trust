import hashlib,json,sys,time
from pathlib import Path
out=Path(__file__).resolve().parent;platform='linux' if sys.platform=='linux' else 'windows'
plan=json.loads((out/('linux-source-v2.json' if platform=='linux' else 'candidate-source-v2.json')).read_text());root=Path(plan['root']);sys.path.insert(0,str(root))
from backend.ifc_union import measure_union
source=Path(sys.argv[1]);gold=json.loads((out/'public-gold-v2.json').read_text());raw=source.read_bytes()
assert hashlib.sha256(raw).hexdigest()==gold['sha256']
rows=[];start=time.monotonic()
for group in gold['groups']:
 r=measure_union(source,group['ids']);value=r['union_volume_m3'];expected=float(group['union_m3'])
 rows.append({'ids':group['ids'],'expected_union_m3':group['union_m3'],'expected_sum_m3':group['sum_m3'],'expected_overlap_m3':group['overlap_m3'],
 'tolerance_m3':1e-8,'matched':value is not None and abs(value-expected)<=1e-8,'result':r})
record={'platform':platform,'source_sha256':gold['sha256'],'source_preserved':hashlib.sha256(source.read_bytes()).hexdigest()==gold['sha256'],
 'seconds':time.monotonic()-start,'cases':rows}
with (out/('public-'+platform+'-v1.json')).open('x',encoding='utf-8') as f:json.dump(record,f,indent=2)
print(json.dumps({'platform':platform,'matched':sum(r['matched'] for r in rows),'cases':len(rows),'seconds':record['seconds'],
 'outcomes':[{'ids':r['ids'],'reason':r['result']['reason'],'value':r['result']['union_volume_m3']} for r in rows]}))
assert record['source_preserved']
