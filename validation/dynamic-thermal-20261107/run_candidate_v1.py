"""New annual references for changed physics hash; no old run resigning."""
import hashlib,json,os,subprocess,sys
from pathlib import Path
out=Path(__file__).resolve().parent
plan=json.loads((out/'candidate-source-v1.json').read_text());root=Path(plan['root'])
for item in plan['files']:
    assert hashlib.sha256((root/item['path']).read_bytes()).hexdigest()==item['sha256'],item['path']
env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',ENERGYPLUS_EXE='F:/EnergyPlusV9-0-1/energyplus.exe',VRA_DATA_DIR=str(root/'bootstrap'))
checks=[]
for name,command in [('annual',[sys.executable,'-B','-X','utf8','scripts/run_reference.py']),
                     ('backend',[sys.executable,'-B','-X','utf8','-m','pytest','-q','-rs','--tb=short','-p','no:cacheprovider','--basetemp',str(root/'pytest')]),
                     ('lint',[sys.executable,'-B','-m','ruff','check','backend'])]:
    with (out/('candidate-'+name+'-v1.log')).open('xb') as f:
        cp=subprocess.run(command,cwd=root,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=3000)
    checks.append({'name':name,'exit_code':cp.returncode})
    print(json.dumps(checks[-1]),flush=True)
    if name=='annual' and cp.returncode:break
with (out/'candidate-checks-v1.json').open('x',encoding='utf-8') as f:json.dump(checks,f,indent=2)
raise SystemExit(int(any(c['exit_code'] for c in checks)))
