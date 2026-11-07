import hashlib,json,os,subprocess,sys,uuid
from pathlib import Path
os.umask(0o077)
repo=Path(__file__).resolve().parents[2];out=Path(__file__).parent
ctx=json.loads((repo/'validation/linux-isolation-20261105/linux-runtime-v2.json').read_text())
assert os.getuid()==ctx['uid']==65534
base=Path(ctx['root'])/('designload-v1-'+uuid.uuid4().hex);base.mkdir();root=base/'source';root.mkdir()
frozen=json.loads((out/'integration-source-v1.json').read_text());records=[]
for item in frozen['files']+[{'path':'scripts/verify_design_load_analytic.py'}]:
 name=item['path'];raw=(repo/name).read_bytes();digest=hashlib.sha256(raw).hexdigest()
 if 'sha256' in item:assert digest==item['sha256'],name
 target=root/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
 records.append({'path':name,'sha256':digest,'bytes':len(raw)})
with (out/'linux-source-v1.json').open('x') as f:json.dump({'base':str(base),'root':str(root),'files':records,'uid':os.getuid()},f,indent=2)
env=dict(os.environ,ENERGYPLUS_EXE=ctx['engine'],VRA_DATA_DIR=str(base/'bootstrap'),PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1')
for label,args in [('analytic',['scripts/verify_design_load_analytic.py',str(base/'analytic')]),
                   ('native',['scripts/verify_design_load_reference.py',str(base/'native')]),
                   ('regression',['-m','pytest','tests/test_design_loads.py','tests/test_weather_quality.py','tests/test_api.py','-q','-p','no:cacheprovider'])]:
 with (out/('linux-'+label+'-v1.log')).open('xb') as log:
  result=subprocess.run([ctx['python'],*args],cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=900)
 print(json.dumps({'stage':label,'exit_code':result.returncode,'root':str(root)}),flush=True)
 if result.returncode:raise SystemExit(result.returncode)
 if label in ('analytic','native'):
  with (out/('linux-'+label+'-v1.json')).open('x') as f:json.dump(json.loads((base/label/'summary.json').read_text()),f,indent=2)
