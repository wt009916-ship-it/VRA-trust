import hashlib,json,os,subprocess,sys
from pathlib import Path
repo=Path(__file__).resolve().parents[2];out=Path(__file__).parent
snapshot=json.loads((out/'integration-source-v1.json').read_text());root=Path(snapshot['root']);base=Path(snapshot['base'])
for item in snapshot['files']:
 assert hashlib.sha256((root/item['path']).read_bytes()).hexdigest()==item['sha256'],item['path']
 if item['path'].startswith(('backend/','frontend/','tests/')):
  assert hashlib.sha256((repo/item['path']).read_bytes()).hexdigest()==item['sha256'],item['path']
assert not (root/'validation/reference_comparison.json').exists()
env=dict(os.environ,ENERGYPLUS_EXE='F:/EnergyPlusV9-0-1/energyplus.exe',VRA_DATA_DIR=str(base/'full-bootstrap'),PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1')
for label,args in [('windows-reference-v1',['scripts/run_reference.py']),('windows-full-v1',['-m','pytest','-q','-rs'])]:
 with (out/(label+'.log')).open('xb') as log:
  result=subprocess.run([sys.executable,*args],cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=2400)
 print(json.dumps({'stage':label,'exit_code':result.returncode,'root':str(root)}),flush=True)
 if result.returncode:raise SystemExit(result.returncode)
