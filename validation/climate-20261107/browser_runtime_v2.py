import json,os,subprocess,sys
from pathlib import Path
out=Path(__file__).resolve().parent;plan=json.loads((out/'browser-prepared-v2.json').read_text())
root=Path(plan['root']);source=Path(plan['source'])
env=dict(os.environ,VRA_DATA_DIR=str(root/'api'),PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',ENERGYPLUS_EXE='F:/EnergyPlusV9-0-1/energyplus.exe')
with (out/'browser-api-v2.log').open('xb') as log:
    process=subprocess.Popen([sys.executable,'-m','uvicorn','backend.api:app','--host','127.0.0.1','--port','18774'],
        cwd=source,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        print(json.dumps({'pid':process.pid,'source':str(source),'url':'http://127.0.0.1:18774'}),flush=True)
        assert input().strip()=='stop'
    finally:
        if process.poll() is None:process.terminate()
        process.wait(timeout=30)
        with (out/'browser-runtime-v2.json').open('x',encoding='utf-8') as stream:
            json.dump({'pid':process.pid,'stopped':True,'returncode':process.returncode,'source':str(source)},stream)
