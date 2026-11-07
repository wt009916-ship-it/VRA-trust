import hashlib,json,os,subprocess,sys
from pathlib import Path
out=Path(__file__).resolve().parent
plan=json.loads((out/'candidate-source-v3.json').read_text());root=Path(plan['root'])
for row in plan['files']:
    assert hashlib.sha256((root/row['path']).read_bytes()).hexdigest()==row['sha256'],row['path']
env=dict(os.environ,PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',ENERGYPLUS_EXE='F:/EnergyPlusV9-0-1/energyplus.exe',VRA_DATA_DIR=str(root/'bootstrap'))
with (out/'windows-backend-v3.log').open('xb') as log:
    cp=subprocess.run([sys.executable,'-B','-X','utf8','-m','pytest','-q','-rs','--tb=short','-p','no:cacheprovider','--basetemp',str(root/'pytest')],cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=3000)
with (out/'windows-checks-v3.json').open('x',encoding='utf-8') as f:json.dump({'exit_code':cp.returncode,'source':str(root)},f,indent=2)
raise SystemExit(cp.returncode)
