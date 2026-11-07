import json,os,subprocess,sys,tempfile,uuid
from pathlib import Path
out=Path(__file__).parent;root=Path(tempfile.gettempdir())/('vra-designload-analytic-'+uuid.uuid4().hex)
env=dict(os.environ,ENERGYPLUS_EXE='F:/EnergyPlusV9-0-1/energyplus.exe',PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1')
with (out/'windows-analytic-v1.log').open('xb') as log:
 result=subprocess.run([sys.executable,'scripts/verify_design_load_analytic.py',str(root)],env=env,
                       stdout=log,stderr=subprocess.STDOUT,timeout=900)
with (out/'windows-analytic-location-v1.json').open('x') as f:json.dump({'root':str(root),'exit_code':result.returncode},f)
if result.returncode:raise SystemExit(result.returncode)
with (out/'windows-analytic-v1.json').open('x') as f:json.dump(json.loads((root/'summary.json').read_text()),f,indent=2)
print(json.dumps({'root':str(root),'exit_code':result.returncode,'new_native_cases':7}))
