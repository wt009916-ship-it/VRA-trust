import json,os,socket,subprocess,sys,time,urllib.request
from pathlib import Path
repo=Path.cwd();out=repo/'validation/climate-20261107'
with socket.socket() as guard:guard.bind(('127.0.0.1',18772))
env=dict(os.environ)
env.update(VRA_DATA_DIR=str(repo/'validation/thermal-20261104/ui-runtime'),ENERGYPLUS_EXE='F:/EnergyPlusV9-0-1/energyplus.exe',
           PYTHONUTF8='1',VRA_SOURCE_PROJECT_FILES='1000',VRA_SOURCE_TOTAL_FILES='1000')
startup=subprocess.STARTUPINFO();startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=0
with (out/'ui-server.log').open('xb') as log,(out/'ui-server-error.log').open('xb') as error:
    proc=subprocess.Popen([sys.executable,'-X','utf8','-m','uvicorn','backend.api:app','--host','127.0.0.1','--port','18772'],
        cwd=repo,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=error,creationflags=subprocess.CREATE_NEW_CONSOLE,startupinfo=startup)
(out/'ui-server.pid').write_text(str(proc.pid),encoding='utf-8')
for _ in range(30):
    assert proc.poll() is None,'Prototype startup failed'
    try:
        with urllib.request.urlopen('http://127.0.0.1:18772/api/health',timeout=2) as r:health=json.load(r)
        assert health['status']=='ok' and health['worker_alive'];break
    except OSError:time.sleep(1)
else:raise RuntimeError('Prototype health deadline exceeded')
print(json.dumps({'launcher_pid':proc.pid,'health':health}))
