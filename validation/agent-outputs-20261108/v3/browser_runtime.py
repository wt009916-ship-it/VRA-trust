"""Fixed first real-model batch. No scripted completions, training or answer injection."""
import hashlib,json,os,secrets,socket,subprocess,sys,tempfile,time,uuid
from pathlib import Path
out=Path(__file__).resolve().parent;repo=out.parents[1];sys.path.insert(0,str(repo))
from backend.private_storage import private_mkdir
plan=json.loads((Path('D:/稀土agent-稀土制暖全流程/vra-trust/validation/local-model-20261106/prepared-runtime.json')).read_text());cache=Path(plan['root'])
api_source=repo
out=out/'browser-runtime-interactive';out.mkdir()
root=private_mkdir(Path(tempfile.gettempdir())/('vra-live-model-'+uuid.uuid4().hex))
os.environ['VRA_DATA_DIR']=str(root/'api');os.environ['VRA_LOCAL_MODEL_TOKEN']=secrets.token_urlsafe(32)
os.environ['ENERGYPLUS_EXE']='F:/EnergyPlusV9-0-1/energyplus.exe'
token=os.environ['VRA_LOCAL_MODEL_TOKEN'];port=18773
with socket.socket() as sock:sock.bind(('127.0.0.1',port))
env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','TEMP','TMP','COMSPEC','SYSTEMDRIVE'}}
env.update(PATH=str(cache/'runtime')+os.pathsep+str(Path(os.environ['SystemRoot'])/'System32'),LLAMA_API_KEY=token)
exe=cache/'runtime/llama-server.exe';model=cache/'models/Qwen3-4B-Q4_K_M.gguf'
for item in plan['extracted']:
 p=cache/item['path']
 with p.open('rb') as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==item['sha256']
with model.open('rb') as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==plan['verified'][2]['sha256']
args=[str(exe),'-m',str(model),'--host','127.0.0.1','--port',str(port),'--alias','vra-qwen3-4b','-c','8192','-np','1',
      '-t','4','-ngl','99','--fit','off','--cache-ram','0','--no-context-shift','--offline','--no-webui','--no-agent',
      '--no-webui-mcp-proxy','--no-slots','--jinja','--reasoning','off','--timeout','120']
receipt={'runtime_root':str(root),'model_sha256':plan['verified'][2]['sha256'],'runtime_commit':plan['runtime_commit'],
         'model_revision':plan['model_revision'],'model_name':'vra-qwen3-4b','server_arguments':args,'data_nature':'synthetic, not real building',
         'score_before':77,'score_change':0,'training':False,'cases':[]}
(out/'live-plan.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
log=(out/'live-server.log').open('wb');process=subprocess.Popen(args,cwd=exe.parent,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
receipt['server_pid']=process.pid
try:
 import httpx
 with httpx.Client(timeout=5,trust_env=False) as network:
  for _ in range(120):
   assert process.poll() is None,'Model process exited before readiness'
   try:
    if network.get(f'http://127.0.0.1:{port}/health').status_code==200:break
   except httpx.HTTPError:pass
   time.sleep(1)
  else:raise RuntimeError('Model readiness timed out')
  command='Get-NetTCPConnection -State Listen | Where-Object OwningProcess -eq '+str(process.pid)+' | Select-Object LocalAddress,LocalPort | ConvertTo-Json -Compress'
  observed=subprocess.check_output([str(Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'),'-NoProfile','-NonInteractive','-Command',command],timeout=30,creationflags=subprocess.CREATE_NO_WINDOW)
  listeners=json.loads(observed);listeners=[listeners] if isinstance(listeners,dict) else listeners
  assert listeners and all(c['LocalAddress']=='127.0.0.1' and c['LocalPort']==port for c in listeners),'Unexpected model listener'
  denied=network.post(f'http://127.0.0.1:{port}/v1/chat/completions',json={'model':'vra-qwen3-4b','messages':[]})
  assert denied.status_code==401
  receipt['unauthenticated_request_status']=denied.status_code;receipt['loopback_listener_verified']=True
 api_env={**env,'VRA_DATA_DIR':str(root/'api'),'VRA_LOCAL_MODEL_TOKEN':token,'ENERGYPLUS_EXE':'F:/EnergyPlusV9-0-1/energyplus.exe','PYTHONUTF8':'1'}
 api_log=(out/'api.log').open('wb')
 api=subprocess.Popen([sys.executable,'-m','uvicorn','backend.api:app','--host','127.0.0.1','--port','18774'],cwd=api_source,env=api_env,stdin=subprocess.DEVNULL,stdout=api_log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
 try:
  for _ in range(120):
   assert api.poll() is None,'Private API exited'
   try:
    with httpx.Client(timeout=3,trust_env=False) as c:
     if c.get('http://127.0.0.1:18774/api/health').status_code==200:break
   except httpx.HTTPError:pass
   time.sleep(1)
  else:raise RuntimeError('Private API readiness timed out')
  receipt.update(api_pid=api.pid,api_port=18774,source_hashes={str(p.relative_to(api_source)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (api_source/'backend').glob('*.py')})
  with httpx.Client(base_url='http://127.0.0.1:18774',timeout=30,trust_env=False) as client:
   response=client.post('/api/auth/register',json={'username':'outputs_ui_test','display_name':'Isolated UI acceptance','password':secrets.token_urlsafe(32)})
   assert response.status_code==200,response.status_code
   client.headers['X-CSRF-Token']=response.json()['csrf_token']
   assert client.put('/api/developer/local-model',json={'enabled':True,'port':18773,'model':'vra-qwen3-4b'}).status_code==200
   response=client.post('/api/projects',json={'name':'Agent output contract acceptance','building':{'use':'office','location':'Synthetic UI test','region':'US-CO','area_m2':1024}})
   assert response.status_code==201,response.status_code
   pid=response.json()['project_id']
   case=json.loads((repo/'validation/agent-completion-20261107/frozen-holdout.json').read_text(encoding='utf-8'))['cases'][1]
   assembly=case['seed_thermal']['wall'];assembly['name']='UI independent wall'
   assembly['layers'][0].update(thickness=167.,conductivity=.05)
   response=client.post(f'/api/projects/{pid}/thermal',json=assembly);assert response.status_code==201,response.status_code
   wall=response.json()
   state={'cookies':[{'name':c.name,'value':c.value,'domain':'127.0.0.1','path':'/','expires':-1,'httpOnly':True,'secure':False,'sameSite':'Strict'} for c in client.cookies.jar],'origins':[]}
   state_path=root/'browser-state.json';state_path.write_text(json.dumps(state),encoding='utf-8')
   receipt.update(project_id=pid,thermal_id=wall['thermal_id'],expected_R='3.51',browser_state_path=str(state_path))
   (out/'browser-ready.json').write_text(json.dumps({k:receipt[k] for k in ['project_id','thermal_id','expected_R','browser_state_path']},indent=2),encoding='utf-8')
  print(json.dumps({'ready':True,'api_pid':api.pid,'model_pid':process.pid,'url':'http://127.0.0.1:18774','new_private_account_required':True}),flush=True)
  assert input().strip()=='stop','Only explicit stop accepted'
 finally:
  if api.poll() is None:api.terminate()
  api.wait(timeout=30);api_log.close();receipt['api_stopped']=True
finally:
 if process.poll() is None:process.terminate()
 process.wait(timeout=30);log.close();receipt['server_stopped']=True
 (out/'runtime-receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'api_stopped':receipt.get('api_stopped',False),'model_stopped':True}),flush=True)

