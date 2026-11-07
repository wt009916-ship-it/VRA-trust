import hashlib,json,sys
from pathlib import Path
repo,out=map(Path,sys.argv[1:]);sys.path.insert(0,str(repo))
from backend.cad_worker import parse_ifc
import ifcopenshell
original=json.loads((out/'probe-windows-v1.json').read_text())
rows=[]
for old in original['cases']:
    path=out/old['file'];assert hashlib.sha256(path.read_bytes()).hexdigest()==old['sha256']
    ifcopenshell.get_log()
    parsed=parse_ifc(path);wall=next(r for r in parsed['ifc_geometry']['objects'] if r['type']=='IfcWall')
    log=ifcopenshell.get_log()
    rows.append({'case':old['case'],'sha256':old['sha256'],'actual_volume_m3':wall['volume_m3'],'independent_expected_m3':old['independent_geometric_net_m3'],
      'matches_windows':wall['volume_m3']==old['actual_volume_m3'],'native_log':log})
with (out/'probe-linux-v1.json').open('x',encoding='utf-8') as f:json.dump({'cases':rows},f,indent=2)
print(json.dumps([{'case':r['case'],'actual':r['actual_volume_m3'],'expected':r['independent_expected_m3'],'matches_windows':r['matches_windows'],'log_bytes':len(r['native_log'])} for r in rows]))
