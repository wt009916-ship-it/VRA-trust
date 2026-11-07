import hashlib,json,os,subprocess,sys,uuid
from pathlib import Path
assert os.getuid()==65534
out=Path(__file__).resolve().parent;repo=out.parents[1]
ctx=json.loads((repo/'validation/linux-isolation-20261105/linux-runtime-v2.json').read_text())
plan=json.loads((out/'candidate-source-v1.json').read_text())
root=Path(ctx['root'])/('hourly-'+uuid.uuid4().hex);root.mkdir()
for row in plan['files']:
    raw=(repo/row['path']).read_bytes()
    assert hashlib.sha256(raw).hexdigest()==row['sha256'],row['path']
    target=root/row['path'];target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
with (out/'linux-source-v1.json').open('x',encoding='utf-8') as f:json.dump({'root':str(root),'uid':os.getuid(),'files':plan['files']},f,indent=2)
env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',ENERGYPLUS_EXE=ctx['engine'],VRA_DATA_DIR=str(root/'bootstrap'))
checks=[]
for name,cmd in [('dynamic',[sys.executable,'-B','scripts/verify_hourly_thermal.py','--output',str(root/'dynamic')]),
                 ('annual',[sys.executable,'-B','scripts/run_reference.py']),
                 ('backend',[sys.executable,'-B','-m','pytest','-q','-rs','--tb=short','-p','no:cacheprovider','--basetemp',str(root/'pytest')])]:
    with (out/('linux-'+name+'-v1.log')).open('xb') as log:
        cp=subprocess.run(cmd,cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=3000)
    checks.append({'name':name,'exit_code':cp.returncode})
    print(json.dumps(checks[-1]),flush=True)
    if name=='annual' and cp.returncode:break
with (out/'linux-checks-v1.json').open('x',encoding='utf-8') as f:json.dump(checks,f,indent=2)
raise SystemExit(int(any(row['exit_code'] for row in checks)))
