"""Bounded mixed native/model HTTP workload, isolated from the user's prototype.

Fixed oracle checks are reference regression, not fresh semantic or building accuracy scores.
No external requests, no training, no mocked execution. All failures remain in this run.
"""
from pathlib import Path
import argparse,concurrent.futures,hashlib,io,json,os,runpy,secrets,socket,sqlite3,subprocess,sys,sysconfig,threading,time,traceback,uuid
from decimal import Decimal

R=Path('C:/Users/18483/AppData/Local/Temp/vra-drawing-components-20261108')
H=Path(__file__).parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',required=True)
parser.add_argument('--seconds',type=int,default=1800)
parser.add_argument('--serve',action='store_true')
parser.add_argument('--port',type=int)
parser.add_argument('--site')
args=parser.parse_args()
if args.site:sys.path.insert(0,args.site)
sys.path.insert(0,str(R));O=Path(args.output).resolve()
os.environ.update(VRA_DATA_DIR=str(O/'private/api'),PYTHONDONTWRITEBYTECODE='1',ENERGYPLUS_EXE='F:/EnergyPlusV9-0-1/energyplus.exe')
if args.serve:
 import uvicorn
 from backend.api import app
 server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=args.port,log_level='warning',access_log=False))
 def stop_from_parent():
  sys.stdin.buffer.read(1);server.should_exit=True
 threading.Thread(target=stop_from_parent,daemon=True).start();server.run();raise SystemExit(0)

import httpx,ezdxf
from backend.private_storage import private_mkdir
assert sys.platform=='win32' and args.seconds in {120,1800},'Only explicit 120s harness check or 1800s mixed acceptance'
assert not O.exists();O.mkdir();private_mkdir(O/'private');private_mkdir(O/'private/tmp')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,obj):p.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=R,text=True).strip()
assert not subprocess.check_output(['git','status','--porcelain'],cwd=R)
source_hashes={p.relative_to(R).as_posix():sha(p) for p in (R/'backend').glob('*.py')}
runtime=json.loads((H.parents[1]/'vra-trust/validation/local-model-20261106/prepared-runtime.json').read_text())
cache=Path(runtime['root']);exe=cache/'runtime/llama-server.exe';model=cache/'models/Qwen3-4B-Q4_K_M.gguf'
for row in runtime['extracted']:assert sha(cache/row['path'])==row['sha256']
assert sha(model)==runtime['verified'][2]['sha256']
duplex=H.parent/'vra-m2-intake-20261108/Duplex_A_20110907.ifc'
assert sha(duplex)=='b347a2c8aa8fff6db896a4417a9c50c22ac0ccd7c5cfc22b99b8d29336c606ed'
doc=ezdxf.new('R2010');doc.units=4;doc.modelspace().add_line((0,0),(3000,4000))
stream=io.StringIO();doc.write(stream);dxf=stream.getvalue().encode()
png=(R/'fixtures/drawing_gold/clean.png').read_bytes()
seed=runpy.run_path(str(H/'run_next_intent_pair.py'))['seeds']()['thermal']
frozen=dict(head=head,harness_sha256=sha(Path(__file__)),source_hashes=source_hashes,
 duration_seconds=args.seconds,epochs=2,interval_seconds=60,tenants=2,
 model_sha256=runtime['verified'][2]['sha256'],runtime_commit=runtime['runtime_commit'],
 inputs={'ifc':sha(duplex),'ocr':hashlib.sha256(png).hexdigest(),'dxf':hashlib.sha256(dxf).hexdigest(),
 'thermal':seed,'reference':{name:sha(R/'fixtures/demo/reference_5zone'/name) for name in ['baseline.idf','weather.epw']}},
 oracles={'annual_energy_kwh':'57193.23','thermal_U':'1/1.36','dxf_length_m':5,'ifc_product_count':295,
 'ocr_labels':['平面图','6000 mm','办公室','会议室','LEVEL 1']},
 limits={'job_timeout_seconds':240,'parser_timeout_seconds':180,'health_p95_ms':2000,'health_p99_ms':5000,
 'sampled_private_bytes':8*1024**3,'source_sha_unchanged':True},
 criteria=['each native job matches reference oracle','all acknowledged IDs survive graceful restart',
 'all uploaded bytes preserved','cross-tenant reads refused','SQLite integrity ok','health latency within frozen limits',
 'model tasks terminate within budget; semantic correctness separately counted','no remaining parser leases after shutdown'],
 scope='Local two-tenant bounded mixed load and drained graceful restart; no forced crash, production SLA, 24h, GPU-memory bound or new semantic score.')
write(O/'frozen.json',frozen)
lock=threading.Lock();stop_monitor=threading.Event();fatal=threading.Event()
api=None;llm=None;model_log=None;epoch=0;users=[];sources=[];ack=[];samples=[];heartbeats=[];cases=[];failures=[]
summary=dict(head=head,completed=False,passed=False,formal_prototype_touched=False,model_semantics_new_score=False,seconds=args.seconds)
def event(name,obj):
 with lock:
  with (O/(name+'.jsonl')).open('a',encoding='utf-8') as f:f.write(json.dumps(obj,ensure_ascii=False)+'\n')
def ensure(ok,message):
 if not ok:raise AssertionError(message)
def call(client,method,path,status=(200,201,202),**kw):
 start=time.monotonic();r=client.request(method,path,**kw)
 event('requests',dict(epoch=epoch,method=method,path=path,status=r.status_code,started_monotonic=start,seconds=time.monotonic()-start))
 ensure(r.status_code in status,f'{method} {path}: status {r.status_code}')
 return r
def free_port():
 with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]
api_port=free_port();model_port=free_port();token=secrets.token_urlsafe(32)
def new_client():return httpx.Client(base_url=f'http://127.0.0.1:{api_port}',timeout=190,trust_env=False)
def start_api():
 global api
 env={**os.environ,'VRA_LOCAL_MODEL_TOKEN':token,'TEMP':str(O/'private/tmp'),'TMP':str(O/'private/tmp')}
 python=getattr(sys,'_base_executable',sys.executable)
 with (O/f'api-{epoch}.log').open('xb') as log:
  api=subprocess.Popen([python,str(Path(__file__)), '--serve','--output',str(O),'--port',str(api_port),'--site',sysconfig.get_paths()['purelib']],cwd=R,env=env,stdin=subprocess.PIPE,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
 deadline=time.monotonic()+45
 with new_client() as c:
  while time.monotonic()<deadline:
   ensure(api.poll() is None,'API exited before readiness')
   try:
    r=c.get('/api/health',timeout=2)
    if r.status_code==200 and r.json()['worker_alive']:
     ensure(r.json()['engine_available'] and not r.json()['demo_mode'],'Native engine unavailable');return
   except httpx.HTTPError:pass
   time.sleep(.2)
 raise AssertionError('API readiness exceeded45s')
def stop_api():
 if api is not None and api.poll() is None:
  api.stdin.close();api.wait(timeout=45);ensure(api.returncode==0,'API did not stop cleanly')
def authenticated(user):
 c=new_client();r=call(c,'POST','/api/auth/login',json={'username':user['username'],'password':user['password']}).json()
 c.headers['X-CSRF-Token']=r['csrf_token'];return c
def await_job(c,path,kind):
 start=time.monotonic()
 while time.monotonic()-start<240:
  value=call(c,'GET',path).json()
  if value['status'] not in {'queued','running'}:return value
  time.sleep(.5)
 raise AssertionError(kind+' job exceeded240s')
def native_engine(user,index):
 with authenticated(user) as c:
  value=call(c,'POST','/api/runs',json={'project_id':user['pid'],'scheme_id':'baseline','factor_profile_id':'reference_scenario'}).json()
  value=await_job(c,'/api/runs/'+value['run_id'],'engine')
  ensure(value['status']=='succeeded','EnergyPlus failed')
  ensure(Decimal(str(value['metrics']['annual_energy_kwh']))==Decimal('57193.23'),'Native energy differs from pinned reference')
  path='/api/runs/'+value['run_id'];ack.append((0,path));return {'lane':'engine','run_id':value['run_id'],'kwh':value['metrics']['annual_energy_kwh']}
def native_parser(user,index):
 kind=['ifc','ocr','dxf'][index%3];fid=user['files'][kind]
 route='drawings' if kind=='ocr' else 'cad-inspections'
 with authenticated(user) as c:
  value=call(c,'POST',f'/api/projects/{user["pid"]}/{route}',json={'file_id':fid}).json()
  ensure(value['status'] not in {'stale','failed'},'Parser returned invalid source')
  if kind=='ocr':ensure({v['text'] for v in value['result']['candidates']}==set(frozen['oracles']['ocr_labels']),'OCR label regression')
  elif kind=='ifc':ensure(sum(value['result']['counts'].values())==295,'IFC count regression')
  else:ensure(value['result']['counts']=={'LINE':1} and value['result']['objects'][0]['length_m']==5,'DXF geometry regression')
  key='drawing_id' if kind=='ocr' else 'cad_id';path=f'/api/projects/{user["pid"]}/{route}/{value[key]}'
  ack.append((1,path));return {'lane':'parser','kind':kind,'record_id':value[key],'source_hash':value['source']['hash']}
def real_agent(user,index):
 with authenticated(user) as c:
  value=call(c,'POST',f'/api/projects/{user["pid"]}/agent/chat',json={'message':'只返回所选墙体的传热系数U及单位，不需要其他数值或解释。',
   'mode':'local_model','allow_compute':False,'read_requests':[{'request_key':'wall','kind':'thermal','purpose':'results','record_id':user['thermal_id']}]}).json()
  path=f'/api/projects/{user["pid"]}/agent/{value["agent_id"]}';value=await_job(c,path,'Agent')
  facts=[f for d in (value.get('answer') or {}).get('checked_statements',[]) for f in d['facts']]
  for f in facts:
   if f['fact']=='u_w_m2k':ensure(abs(Decimal(f['value'])-Decimal(1)/Decimal('1.36'))<Decimal('1e-11'),'Verified U differs from independent oracle')
  valid=len(facts)==1 and facts[0]['fact']=='u_w_m2k' and value['status']=='succeeded'
  ensure(any(e['tool']=='llm.request' for e in value['events']),'No actual model request')
  ack.append((1,path));write(O/f'agent-{epoch}-{index}.json',value)
  return {'lane':'agent','status':value['status'],'requested_fact_delivered':valid,'task_id':value['agent_id'],'model_calls':sum(e['tool']=='llm.request' for e in value['events'])}
def monitor():
 with new_client() as c:
  iteration=0
  while not stop_monitor.is_set():
   try:
    started=time.monotonic();r=c.get('/api/health',timeout=6);ms=(time.monotonic()-started)*1000
    ensure(r.status_code==200 and r.json()['worker_alive'],'Health unavailable under load')
    heartbeats.append(ms);event('health',dict(epoch=epoch,ms=ms))
    if iteration%4==0:
     command='$all=@(Get-CimInstance Win32_Process);$ids=@('+str(api.pid)+','+str(llm.pid)+');do{$old=$ids.Count;$ids=@($ids+@($all|Where-Object {$_.ParentProcessId -in $ids}|ForEach-Object {[int]$_.ProcessId})|Select-Object -Unique)}while($ids.Count -gt $old);@($all|Where-Object {$_.ProcessId -in $ids}|Select-Object ProcessId,ParentProcessId,Name,PrivatePageCount,WorkingSetSize)|ConvertTo-Json -Compress'
     rows=json.loads(subprocess.check_output(['powershell.exe','-NoProfile','-NonInteractive','-Command',command],timeout=20,creationflags=subprocess.CREATE_NO_WINDOW))
     if isinstance(rows,dict):rows=[rows]
     size=sum(int(x['PrivatePageCount']) for x in rows)
     samples.append(size);event('resources',dict(epoch=epoch,private_bytes=size,processes=rows))
     ensure(size<=frozen['limits']['sampled_private_bytes'],'Sampled private-memory budget exceeded')
   except Exception as e:failures.append(dict(lane='monitor',error_type=type(e).__name__,message=str(e)));fatal.set();return
   iteration+=1;stop_monitor.wait(5)
def checkpoint():
 with sqlite3.connect((O/'private/api/vra.sqlite3').as_uri()+'?mode=ro',uri=True) as db:
  ensure(db.execute('PRAGMA integrity_check').fetchone()[0]=='ok','Database integrity error')
  h=hashlib.sha256()
  for table,cols,order in [('records','kind,id,revision,project_id,body','kind,id,revision'),('jobs','id,project_id,state,body,error','id')]:
   for row in db.execute('SELECT '+cols+' FROM '+table+' ORDER BY '+order):h.update(json.dumps(row,ensure_ascii=False).encode())
  return h.hexdigest()
def timed_lane(function,user,index):
 started=time.monotonic();result=function(user,index)
 return {**result,'started_monotonic':started,'finished_monotonic':time.monotonic()}
try:
 model_env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','TEMP','TMP','COMSPEC','SYSTEMDRIVE'}}
 model_env.update(PATH=str(exe.parent)+os.pathsep+str(Path(os.environ['SystemRoot'])/'System32'),LLAMA_API_KEY=token)
 model_args=[str(exe),'-m',str(model),'--host','127.0.0.1','--port',str(model_port),'--alias','vra-mixed-load',
 '-c','8192','-np','1','-t','4','-ngl','99','--fit','off','--cache-ram','0','--no-context-shift','--offline',
 '--no-webui','--no-agent','--no-webui-mcp-proxy','--no-slots','--jinja','--reasoning','off','--timeout','120']
 model_log=(O/'model.log').open('xb');llm=subprocess.Popen(model_args,cwd=exe.parent,env=model_env,stdin=subprocess.DEVNULL,stdout=model_log,stderr=model_log,creationflags=subprocess.CREATE_NO_WINDOW)
 with httpx.Client(timeout=3,trust_env=False) as c:
  for _ in range(120):
   ensure(llm.poll() is None,'Model exited during startup')
   try:
    if c.get(f'http://127.0.0.1:{model_port}/health').status_code==200:break
   except httpx.HTTPError:pass
   time.sleep(1)
  else:raise AssertionError('Model startup timeout')
  ensure(c.post(f'http://127.0.0.1:{model_port}/v1/chat/completions',json={'messages':[]}).status_code==401,'Model anonymous access not rejected')
 start_api()
 for index in range(2):
  user=dict(username='mixed_'+str(index),password=secrets.token_urlsafe(32))
  with new_client() as c:
   auth=call(c,'POST','/api/auth/register',json={'username':user['username'],'password':user['password'],'display_name':'Isolated mixed load'}).json();c.headers['X-CSRF-Token']=auth['csrf_token']
   if index==0:
    call(c,'PUT','/api/developer/local-model',json={'enabled':True,'port':model_port,'model':'vra-mixed-load'})
    user['pid']=call(c,'POST','/api/reference-projects').json()['project_id']
    for item in call(c,'GET',f'/api/projects/{user["pid"]}/evidence').json():
     call(c,'PATCH',f'/api/projects/{user["pid"]}/evidence/{item["evidence_id"]}',json={'expected_revision':item['revision'],'review_state':'confirmed','responsible_person':'Automated reference test','review_note':'Public reference only, not measured building or engineering signoff'})
   else:
    user['pid']=call(c,'POST','/api/projects',json={'name':'Mixed parser and model load','building':{'use':'office','location':'Synthetic','region':'US-CO','area_m2':800}}).json()['project_id']
    user['thermal_id']=call(c,'POST',f'/api/projects/{user["pid"]}/thermal',json=seed).json()['thermal_id'];user['files']={}
    for kind,name,raw in [('ifc','Duplex.ifc',duplex.read_bytes()),('ocr','clean.png',png),('dxf','line.dxf',dxf)]:
     fid=call(c,'POST',f'/api/projects/{user["pid"]}/files',files={'file':(name,raw)}).json()['file_id'];user['files'][kind]=fid
     sources.append((index,f'/api/projects/{user["pid"]}/files/{fid}',hashlib.sha256(raw).hexdigest()))
  users.append(user)
 with authenticated(users[1]) as c:call(c,'GET','/api/projects/'+users[0]['pid'],status=(404,))
 run_start=time.monotonic();round_index=0
 for epoch in range(2):
  stop_monitor.clear();watcher=threading.Thread(target=monitor,daemon=True);watcher.start()
  began=time.monotonic()
  with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
   while time.monotonic()-began<args.seconds/2:
    ensure(not fatal.is_set(),'Monitoring failed');cycle=time.monotonic()
    futures=[pool.submit(timed_lane,native_engine,users[0],round_index),pool.submit(timed_lane,native_parser,users[1],round_index),pool.submit(timed_lane,real_agent,users[1],round_index)]
    row={'epoch':epoch,'round':round_index,'results':[f.result(timeout=250) for f in futures]}
    row['seconds']=time.monotonic()-cycle;cases.append(row);event('rounds',row)
    write(O/'progress.json',dict(head=head,elapsed_seconds=time.monotonic()-run_start,rounds=len(cases),acknowledged=len(ack),failures=failures))
    print(json.dumps(dict(epoch=epoch,round=round_index,seconds=round(row['seconds'],2),model_delivery=row['results'][2]['requested_fact_delivered'])),flush=True)
    round_index+=1
    remaining=min(60-(time.monotonic()-cycle),args.seconds/2-(time.monotonic()-began))
    if remaining>0:fatal.wait(remaining)
  stop_monitor.set();watcher.join(timeout=25);ensure(not watcher.is_alive(),'Monitor did not stop');ensure(not fatal.is_set(),'Mixed monitor failed')
  if epoch==0:
   before=checkpoint();stop_api();ensure(checkpoint()==before,'Business state changed during drained shutdown')
   epoch=1;start_api();ensure(checkpoint()==before,'Acknowledged state changed during restart')
   for user_index,path in ack:
    with authenticated(users[user_index]) as c:call(c,'GET',path)
   event('restart',{'business_digest_unchanged':True,'acknowledged_readable':len(ack),'drained':True})
 for user_index,path,digest in sources:
  with authenticated(users[user_index]) as c:ensure(hashlib.sha256(call(c,'GET',path).content).hexdigest()==digest,'Uploaded source changed')
 checkpoint();ensure(all(sha(R/p)==digest for p,digest in source_hashes.items()),'Source code changed during benchmark')
 latency=sorted(heartbeats)
 p95=latency[min(len(latency)-1,int(len(latency)*.95))];p99=latency[min(len(latency)-1,int(len(latency)*.99))]
 ensure(p95<=2000 and p99<=5000,'Health latency exceeded frozen limits')
 summary.update(completed=True,passed=True,elapsed_seconds=time.monotonic()-run_start,rounds=len(cases),
 acknowledged=len(ack),health_samples=len(latency),p95_ms=p95,p99_ms=p99,sampled_private_peak=max(samples),
 agent_requested_fact_passes=sum(x['results'][2]['requested_fact_delivered'] for x in cases),agent_total=len(cases))
except Exception as e:
 failures.append({'error_type':type(e).__name__,'message':str(e)});(O/'failure.txt').write_text(traceback.format_exc(),encoding='utf-8')
finally:
 stop_monitor.set()
 try:stop_api()
 except Exception as e:failures.append({'cleanup_error':str(e)});summary['passed']=False
 if llm is not None and llm.poll() is None:
  llm.terminate()
  try:llm.wait(timeout=20)
  except subprocess.TimeoutExpired:llm.kill();llm.wait()
 if model_log:model_log.close()
 leftovers=[str(p.relative_to(O/'private/tmp')) for root in (O/'private/tmp').glob('vra-native-v1-*') for p in root.iterdir() if p.is_dir()]
 if leftovers:failures.append({'native_task_directories_remaining':leftovers});summary['passed']=False
 summary.update(failures=failures,api_stopped=api is None or api.poll() is not None,model_stopped=llm is None or llm.poll() is not None)
 write(O/'summary.json',summary);print(json.dumps(summary,ensure_ascii=False),flush=True)
raise SystemExit(0 if summary['passed'] else 1)
