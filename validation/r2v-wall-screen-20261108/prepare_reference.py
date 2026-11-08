from pathlib import Path
import json,hashlib,datetime,io,zipfile
root=Path(__file__).parent
repo=Path('C:/Users/18483/AppData/Local/Temp/vra-maintenance-recheck-20261108')
base=Path('C:/Users/18483/AppData/Local/Temp/vra-floorplan-feasibility-20261108')
splits=json.loads((base/'resplan-split.json').read_text())
prior=[]
for name in ['drawing-components-20261108','drawing-symbols-20261108']:
 prior+=json.loads((repo/'validation'/name/'selection-frozen.json').read_text())['ids']
ids=sorted(set(splits['test'])-set(prior),key=lambda x:hashlib.sha256(('VRA-R2V-wall-v1:'+str(x)).encode()).hexdigest())[:8]
selection={'source_commit':'e2b78fe069aee1ab1e1828a612743f308e3c32a7','split':'test','ids':ids,'excluded_prior_ids':prior,'selection':'first 8 SHA256(VRA-R2V-wall-v1:<id>) sorted canonical test IDs after excluding both prior screens','frozen_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'inference_yet':False,'nature':'rendered public geometry; not scans or surveyed truth'}
(root/'selection-frozen.json').write_text(json.dumps(selection,indent=2),encoding='utf-8')
# Reuse the reviewed restricted decoder definitions only; never upstream pickle constructors.
source=(repo/'validation/drawing-components-20261108/executed-sources/decode_resplan_reference.py').read_text(encoding='utf-8').split("archive=ROOT/")[0]
namespace={};exec(compile(source,'restricted-decoder-definitions','exec'),namespace)
archive=base/'ResPlan.zip'
assert hashlib.sha256(archive.read_bytes()).hexdigest()==json.loads((base/'resplan-download.json').read_text())['sha256']
with zipfile.ZipFile(archive) as z: raw=z.read('ResPlan.pkl')
data=namespace['GeometryOnlyUnpickler'](io.BytesIO(raw)).load()
lookup={row['id']:row for row in data}
assert len(lookup)==17000
(root/'selected-geometries.json').write_text(json.dumps({'selection':selection,'plans':[lookup[i] for i in ids]},allow_nan=False),encoding='utf-8')
print(json.dumps({'ids':ids,'prior_overlap':sorted(set(ids)&set(prior))}),flush=True)
