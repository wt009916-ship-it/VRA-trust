import hashlib,json,os,subprocess,sys,uuid
from pathlib import Path
assert os.getuid()==65534
out=Path(__file__).resolve().parent
ctx=json.loads(Path('/mnt/d/稀土agent-稀土制暖全流程/vra-trust/validation/linux-isolation-20261105/linux-runtime-v2.json').read_text())
plan=json.loads((out/'candidate-source-v3.json').read_text())
source=Path('/mnt/c/'+plan['root'][3:].replace('\\','/'))
root=Path(ctx['root'])/('cad-state-source-'+uuid.uuid4().hex);root.mkdir()
for row in plan['files']:
    raw=(source/row['path']).read_bytes()
    assert hashlib.sha256(raw).hexdigest()==row['sha256'],row['path']
    target=root/row['path'];target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
with (out/'linux-source-v3.json').open('x',encoding='utf-8') as f:json.dump({'root':str(root),'uid':os.getuid(),'files':plan['files']},f,indent=2)
env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',ENERGYPLUS_EXE=ctx['engine'],VRA_DATA_DIR=str(root/'bootstrap'))
with (out/'linux-backend-v3.log').open('xb') as log:
    cp=subprocess.run([sys.executable,'-B','-m','pytest','-q','-rs','--tb=short','-p','no:cacheprovider','--basetemp',str(root/'pytest')],
                      cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=3000)
with (out/'linux-checks-v3.json').open('x',encoding='utf-8') as f:json.dump({'name':'backend','exit_code':cp.returncode,'annual_reference_not_rerun':'Physics code unchanged; reference-only skips reported'},f,indent=2)
raise SystemExit(cp.returncode)
