import hashlib,json,os,subprocess,sys,tempfile,uuid
from pathlib import Path
repo=Path(__file__).resolve().parents[2];out=Path(__file__).parent
sys.path.insert(0,str(repo))
from backend.private_storage import private_mkdir
base=Path(tempfile.gettempdir())/('vra-designload-integration-'+uuid.uuid4().hex);private_mkdir(base)
root=base/'source';root.mkdir()
prior=json.loads((repo/'validation/climate-20261107/windows-source-v2.json').read_text())
names={r['path'] for r in prior['files']}|{'backend/design_loads.py','tests/test_design_loads.py',
 'fixtures/test/native_zone_sizing_projection.json','frontend/src/design-loads.js','frontend/src/design-loads.css',
 'frontend/tests/design-loads.test.js','scripts/verify_design_load_reference.py'}
records=[]
for name in sorted(names):
 path=repo/name
 if path.is_file():
  raw=path.read_bytes();target=root/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
  records.append({'path':name,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)})
with (out/'integration-source-v1.json').open('x') as f:json.dump({'base':str(base),'root':str(root),'files':records},f,indent=2)
env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',ENERGYPLUS_EXE='F:/EnergyPlusV9-0-1/energyplus.exe',VRA_DATA_DIR=str(base/'bootstrap'))
with (out/'integration-native-v1.log').open('xb') as log:
 result=subprocess.run([sys.executable,'scripts/verify_design_load_reference.py',str(base/'native')],cwd=root,env=env,
                       stdout=log,stderr=subprocess.STDOUT,timeout=900)
print(json.dumps({'stage':'native','exit_code':result.returncode,'base':str(base)}),flush=True)
if result.returncode:raise SystemExit(result.returncode)
with (out/'integration-summary-v1.json').open('x') as f:json.dump(json.loads((base/'native/summary.json').read_text()),f,indent=2)
with (out/'integration-regression-v1.log').open('xb') as log:
 result=subprocess.run([sys.executable,'-m','pytest','tests/test_design_loads.py','tests/test_weather_quality.py','tests/test_api.py','-q','-p','no:cacheprovider'],cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=300)
print(json.dumps({'stage':'regression','exit_code':result.returncode}),flush=True)
raise SystemExit(result.returncode)
