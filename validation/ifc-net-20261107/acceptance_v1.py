import hashlib,json,sys,time
from pathlib import Path
repo,out,label=Path(sys.argv[1]),Path(sys.argv[2]),sys.argv[3]
sys.path.insert(0,str(repo))
from backend.cad_worker import parse_ifc
cases=[]
for old in json.loads((out/'probe-windows-v1.json').read_text())['cases']:
    path=out/old['file'];digest=hashlib.sha256(path.read_bytes()).hexdigest();assert digest==old['sha256']
    parsed=parse_ifc(path);wall=next(r for r in parsed['ifc_geometry']['objects'] if r['type']=='IfcWall')
    value=wall['volume_m3'];expected=old['independent_geometric_net_m3'];name=old['case']
    if name=='host_fully_removed':passed=value is None and wall.get('mesh_status')=='empty_mesh'
    elif name=='duplicate_void_relation':passed=value is None and wall['status']=='ambiguous_opening_relationships'
    else:passed=value is not None and abs(value-expected)<=1e-9
    cases.append({'case':name,'source_sha256':digest,'expected_geometric_net_m3':expected,'actual_volume_m3':value,
        'status':wall['status'],'mesh_status':wall.get('mesh_status'),'relationship_issues':wall['opening_relationships']['issues'],
        'passed':passed,'original_preserved':hashlib.sha256(path.read_bytes()).hexdigest()==digest})
record={'cases':cases,'all_cases_passed':all(c['passed'] and c['original_preserved'] for c in cases),
 'scope':'Six numeric golds, one empty-mesh refusal, one ambiguous-relation refusal; no professional net-quantity certification.'}
with (out/('acceptance-'+label+'-v1.json')).open('x',encoding='utf-8') as f:json.dump(record,f,indent=2)
print(json.dumps({'platform':label,'accepted':sum(c['passed'] for c in cases),'cases':len(cases)}))
assert record['all_cases_passed']
