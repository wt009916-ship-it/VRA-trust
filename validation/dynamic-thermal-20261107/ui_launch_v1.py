import hashlib,json,os,shutil,socket,subprocess,sys,time,urllib.request
from pathlib import Path
out=Path(__file__).resolve().parent;repo=out.parents[1]
plan=json.loads((out/'candidate-source-v1.json').read_text());root=Path(plan['root'])
for row in plan['files']:
    assert hashlib.sha256((root/row['path']).read_bytes()).hexdigest()==row['sha256'],row['path']
shutil.copytree(repo/'frontend/dist',root/'frontend/dist')
with socket.socket() as guard:guard.bind(('127.0.0.1',18774))
env=dict(os.environ,VRA_DATA_DIR=str(root/'ui-data'),ENERGYPLUS_EXE='F:/EnergyPlusV9-0-1/energyplus.exe',PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1')
startup=subprocess.STARTUPINFO();startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=0
with (out/'ui-server-v1.log').open('xb') as log:
    proc=subprocess.Popen([sys.executable,'-B','-X','utf8','-m','uvicorn','backend.api:app','--host','127.0.0.1','--port','18774'],cwd=root,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NEW_CONSOLE,startupinfo=startup)
record={'launcher_pid':proc.pid,'root':str(root),'data':str(root/'ui-data'),'port':18774,'business_data_used':False}
with (out/'ui-runtime-v1.json').open('x',encoding='utf-8') as f:json.dump(record,f,indent=2)
for _ in range(30):
    assert proc.poll() is None
    try:
        with urllib.request.urlopen('http://127.0.0.1:18774/api/health',timeout=2) as response:health=json.load(response)
        assert health['status']=='ok';break
    except OSError:time.sleep(1)
else:raise RuntimeError('Health timeout')
print(json.dumps({**record,'health':health}))
