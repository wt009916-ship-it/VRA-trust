import json,os,secrets,socket,subprocess,sys,tempfile,time,uuid
from pathlib import Path
import httpx
out=Path(__file__).resolve().parent
candidate=Path(json.loads((out/'candidate.json').read_text())['candidate'])
sys.path.insert(0,str(candidate))
from backend.private_storage import private_mkdir
runtime=private_mkdir(Path(tempfile.gettempdir())/('vra-material-browser-'+uuid.uuid4().hex))
port=18775
with socket.socket() as s:s.bind(('127.0.0.1',port))
env={**os.environ,'VRA_DATA_DIR':str(runtime/'api'),'ENERGYPLUS_EXE':'F:/EnergyPlusV9-0-1/energyplus.exe','PYTHONUTF8':'1'}
log=(out/'browser-api.log').open('wb')
api=subprocess.Popen([sys.executable,'-B','-m','uvicorn','backend.api:app','--host','127.0.0.1','--port',str(port)],cwd=candidate,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
state_path=runtime/'browser-state.json';receipt={'api_pid':api.pid,'port':port,'candidate':str(candidate),'isolated_runtime':str(runtime)}
try:
 with httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=5,trust_env=False) as client:
  for _ in range(60):
   assert api.poll() is None,'Private API exited'
   try:
    if client.get('/api/health').status_code==200:break
   except httpx.HTTPError:pass
   time.sleep(1)
  else:raise RuntimeError('API readiness timeout')
  response=client.post('/api/auth/register',json={'username':'material_workflow_ui','display_name':'Isolated material reference','password':secrets.token_urlsafe(32)})
  assert response.status_code==200
  client.headers['X-CSRF-Token']=response.json()['csrf_token']
  response=client.post('/api/projects',json={'name':'公开IFC材料方案验收（非实楼）','data_nature':'engineering_reference','building':{'use':'reference','location':'Public reference','region':'US-CO','area_m2':927.2}})
  assert response.status_code==201
  receipt['project_id']=response.json()['project_id']
  state={'cookies':[{'name':c.name,'value':c.value,'domain':'127.0.0.1','path':'/','expires':-1,'httpOnly':True,'secure':False,'sameSite':'Strict'} for c in client.cookies.jar],'origins':[]}
  state_path.write_text(json.dumps(state),encoding='utf-8')
  receipt['browser_state_path']=str(state_path)
 (out/'browser-ready.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
 print(json.dumps({'ready':True,'pid':api.pid,'port':port}),flush=True)
 assert input().strip()=='stop'
finally:
 if api.poll() is None:api.terminate()
 api.wait(timeout=30);log.close()
 if state_path.exists():state_path.unlink()
 receipt.update(stopped=True,private_browser_state_deleted=True)
 (out/'browser-runtime-receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
 print('Private API stopped; private browser state deleted',flush=True)
