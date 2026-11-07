"""Launch only the verified application after its PR is merged and old console stopped."""
import hashlib,json,os,socket,subprocess,sys,time,urllib.request
from pathlib import Path
out=Path(__file__).resolve().parent;repo=out.parents[1]
plan=json.loads((out/'git-source-verified-v1.json').read_text());merge=json.loads((out/'merge-receipt.json').read_text())
assert merge['merged'] and merge['tested_head']==plan['application_commit']
assert json.loads((out/'prototype-stopped-v1.json').read_text())['exit_code']==0
root=Path(plan['root'])
for row in plan['files']:
    assert hashlib.sha256((root/row['path']).read_bytes()).hexdigest()==row['sha256'],row['path']
for name,digest in plan['assets'].items():
    assert hashlib.sha256((root/'frontend/dist'/name).read_bytes()).hexdigest()==digest
with socket.socket() as guard:guard.bind(('127.0.0.1',18772))
env=dict(os.environ,VRA_DATA_DIR=json.loads((out/'runtime-context-v1.json').read_text())['prototype_data'],ENERGYPLUS_EXE='F:/EnergyPlusV9-0-1/energyplus.exe',
         PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',VRA_SOURCE_PROJECT_FILES='1000',VRA_SOURCE_TOTAL_FILES='1000')
startup=subprocess.STARTUPINFO();startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=0
with (out/'prototype-server-v1.log').open('xb') as log:
    proc=subprocess.Popen([sys.executable,'-B','-X','utf8','-m','uvicorn','backend.api:app','--host','127.0.0.1','--port','18772'],cwd=root,env=env,
        stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NEW_CONSOLE,startupinfo=startup)
with (out/'prototype-pid-v1.json').open('x',encoding='utf-8') as f:json.dump({'pid':proc.pid,'root':str(root)},f)
for _ in range(30):
    assert proc.poll() is None,'New prototype stopped; preserve logs and restore verified previous source if necessary'
    try:
        with urllib.request.urlopen('http://127.0.0.1:18772/api/health',timeout=2) as response:health=json.load(response)
        assert health['status']=='ok' and health['worker_alive'] and health['engine_available'] and not health['demo_mode'];break
    except OSError:time.sleep(1)
else:raise RuntimeError('Prototype health deadline exceeded')
record={'pid':proc.pid,'root':str(root),'application_commit':plan['application_commit'],'main':merge['merge_sha'],'health':health}
with (out/'prototype-started-v1.json').open('x',encoding='utf-8') as f:json.dump(record,f,indent=2)
print(json.dumps(record))
