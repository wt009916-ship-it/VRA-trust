import hashlib,json,os,subprocess
from pathlib import Path
os.umask(0o077)
repo=Path(__file__).resolve().parents[2];out=Path(__file__).parent
ctx=json.loads((repo/'validation/linux-isolation-20261105/linux-runtime-v2.json').read_text())
assert os.getuid()==ctx['uid']==65534
snapshot=json.loads((out/'linux-source-v1.json').read_text());root=Path(snapshot['root']);base=Path(snapshot['base'])
for item in snapshot['files']:
 assert hashlib.sha256((root/item['path']).read_bytes()).hexdigest()==item['sha256'],item['path']
 if item['path'].startswith(('backend/','frontend/','tests/')):
  assert hashlib.sha256((repo/item['path']).read_bytes()).hexdigest()==item['sha256'],item['path']
assert not (root/'validation/reference_comparison.json').exists()
env=dict(os.environ,ENERGYPLUS_EXE=ctx['engine'],VRA_DATA_DIR=str(base/'full-bootstrap'),PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1')
for label,args in [('linux-reference-v1',['scripts/run_reference.py']),('linux-full-v1',['-m','pytest','-q','-rs'])]:
 with (out/(label+'.log')).open('xb') as log:
  result=subprocess.run([ctx['python'],*args],cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=2400)
 print(json.dumps({'stage':label,'exit_code':result.returncode,'root':str(root)}),flush=True)
 if result.returncode:raise SystemExit(result.returncode)
