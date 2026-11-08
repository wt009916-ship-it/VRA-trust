"""Actual local inference, unmodified application tools, frozen paired cases."""
import copy,ctypes,hashlib,json,os,secrets,socket,subprocess,sys,tempfile,threading,time,uuid
from ctypes import wintypes
from decimal import Decimal
from pathlib import Path
base=Path(__file__).resolve().parent;repo=next(p for p in base.parents if (p/"backend/agent.py").is_file());sys.path.insert(0,str(repo))
variant=sys.argv[1];assert variant in {'4b','8b'}
cohort=sys.argv[2];assert cohort in {'regression','fresh','holdout','comparison'}
out=base/(cohort+'-'+variant);out.mkdir()
fixture=base/f'frozen-{cohort}.json';digest=hashlib.sha256(fixture.read_bytes()).hexdigest()
assert digest==(base/f'frozen-{cohort}.sha256').read_text().strip()
cases=json.loads(fixture.read_text(encoding='utf-8'))
assert all(hashlib.sha256((repo/name).read_bytes()).hexdigest()==digest for name,digest in cases['source_hashes'].items()), 'Frozen candidate source mismatch'
from backend.private_storage import private_mkdir
runtime=json.loads((Path('D:/稀土agent-稀土制暖全流程/vra-trust/validation/local-model-20261106/prepared-runtime.json')).read_text());cache=Path(runtime['root'])
model_info=runtime['verified'][2] if variant=='4b' else json.loads((Path('D:/稀土agent-稀土制暖全流程/vra-trust/validation/model-comparison-20261106/prepared-candidate.json')).read_text())
model=cache/'models/Qwen3-4B-Q4_K_M.gguf' if variant=='4b' else Path(model_info['local_path'])
for item in runtime['extracted']:
 with (cache/item['path']).open('rb') as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==item['sha256']
with model.open('rb') as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==model_info['sha256']
root=private_mkdir(Path(tempfile.gettempdir())/('vra-model-pair-'+uuid.uuid4().hex))
os.environ.update(VRA_DATA_DIR=str(root/'api'),VRA_LOCAL_MODEL_TOKEN=secrets.token_urlsafe(32),ENERGYPLUS_EXE='F:/EnergyPlusV9-0-1/energyplus.exe')
port=18773;alias='vra-model-comparison'
with socket.socket() as sock:sock.bind(('127.0.0.1',port))
env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','TEMP','TMP','COMSPEC','SYSTEMDRIVE'}}
env.update(PATH=str(cache/'runtime')+os.pathsep+str(Path(os.environ['SystemRoot'])/'System32'),LLAMA_API_KEY=os.environ['VRA_LOCAL_MODEL_TOKEN'])
exe=cache/'runtime/llama-server.exe'
args=[str(exe),'-m',str(model),'--host','127.0.0.1','--port',str(port),'--alias',alias,'-c','8192','-np','1','-t','4','-ngl','99','--fit','off','--cache-ram','0',
 '--no-context-shift','--offline','--no-webui','--no-agent','--no-webui-mcp-proxy','--no-slots','--jinja','--reasoning','off','--timeout','120']
receipt={'variant':variant,'fixture_sha256':digest,'application_commit':cases['application_commit'],'model_sha256':model_info['sha256'],'server_arguments':args,
 'runtime_root':str(root),'runtime_commit':runtime['runtime_commit'],'training':False,'cases':[],'samples':[],
 'source_hashes':{str(p.relative_to(repo)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (repo/'backend').glob('*.py')}}
def save():(out/'results.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
save();start=time.monotonic();log=(out/'server.log').open('xb')
process=subprocess.Popen(args,cwd=exe.parent,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
receipt['server_pid']=process.pid;save();stop=threading.Event()
class Memory(ctypes.Structure):
 _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[(n,ctypes.c_size_t) for n in ['PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage']]
getmem=ctypes.WinDLL('psapi',use_last_error=True).GetProcessMemoryInfo
getmem.argtypes=[wintypes.HANDLE,ctypes.POINTER(Memory),wintypes.DWORD];getmem.restype=wintypes.BOOL
def monitor():
 while not stop.is_set():
  sample={'elapsed_s':round(time.monotonic()-start,2)};m=Memory();m.cb=ctypes.sizeof(m)
  if getmem(wintypes.HANDLE(int(process._handle)),ctypes.byref(m),m.cb):sample.update(rss_bytes=m.WorkingSetSize,peak_rss_bytes=m.PeakWorkingSetSize,private_commit_bytes=m.PagefileUsage)
  try:sample['gpu_total_used_mib']=int(subprocess.check_output(['nvidia-smi','--query-gpu=memory.used','--format=csv,noheader,nounits'],timeout=5,creationflags=subprocess.CREATE_NO_WINDOW).decode().strip())
  except Exception:sample['gpu_observation_failed']=True
  receipt['samples'].append(sample);stop.wait(5)
thread=threading.Thread(target=monitor,daemon=True);thread.start()
try:
 import httpx
 with httpx.Client(timeout=5,trust_env=False) as network:
  for _ in range(120):
   assert process.poll() is None,'Model exited before readiness'
   try:
    if network.get(f'http://127.0.0.1:{port}/health').status_code==200:break
   except httpx.HTTPError:pass
   time.sleep(1)
  else:raise RuntimeError('Model readiness timed out')
  receipt['startup_seconds']=round(time.monotonic()-start,3)
  command='Get-NetTCPConnection -State Listen | Where-Object OwningProcess -eq '+str(process.pid)+' | Select-Object LocalAddress,LocalPort | ConvertTo-Json -Compress'
  listeners=json.loads(subprocess.check_output(['powershell.exe','-NoProfile','-NonInteractive','-Command',command],timeout=30,creationflags=subprocess.CREATE_NO_WINDOW))
  listeners=[listeners] if isinstance(listeners,dict) else listeners
  assert listeners and all(c['LocalAddress']=='127.0.0.1' and c['LocalPort']==port for c in listeners)
  receipt['loopback_verified']=True
  assert network.post(f'http://127.0.0.1:{port}/v1/chat/completions',json={'model':alias,'messages':[]}).status_code==401
  receipt['unauthenticated_status']=401
 from fastapi.testclient import TestClient
 from backend.api import app
 from backend.local_model import LocalModelGateway
 from backend.engineering import BeamInput,Engineering
 original=LocalModelGateway.complete;capture={'case':None,'index':0}
 def observed(self,messages,tools,**kwargs):
  began=time.monotonic();entry={'case':capture['case'],'messages':copy.deepcopy(messages),'tools':copy.deepcopy(tools)}
  try:
   result=original(self,messages,tools,**kwargs);entry['response']=result;return result
  except Exception as exc:entry['error_type']=type(exc).__name__;raise
  finally:
   entry['seconds']=round(time.monotonic()-began,3);capture['index']+=1
   (out/f"model-call-{capture['index']:03}.json").write_text(json.dumps(entry,ensure_ascii=False,indent=2),encoding='utf-8')
 LocalModelGateway.complete=observed # Passive recording only; original real HTTP result returned unchanged.
 previous={}
 with TestClient(app) as client:
  r=client.post('/api/auth/register',json={'username':'isolated_model_comparison','display_name':'Synthetic comparison','password':secrets.token_urlsafe(32)})
  assert r.status_code==200;client.headers['X-CSRF-Token']=r.json()['csrf_token']
  assert client.put('/api/developer/local-model',json={'enabled':True,'port':port,'model':alias}).status_code==200
  for c in cases['cases']:
   capture['case']=c['id'];began=time.monotonic();calls_before=capture['index'];body={'message':c['message'],'mode':'local_model'}
   if c.get('previous'):
    pid,prior=previous[c['previous']];body['previous_agent_id']=prior['agent_id']
    if 'change_area' in c:
     p=client.get(f'/api/projects/{pid}').json();building={**p['building'],'area_m2':c['change_area']}
     r=client.put(f'/api/projects/{pid}/building',json={'expected_revision':p['revision'],'building':building});assert r.status_code==200,r.text
   else:
    r=client.post('/api/projects',json={'name':c.get('project_name','Synthetic paired '+c['id']),'building':c.get('building',{'use':'office','location':'Synthetic comparison','region':'US-CO','area_m2':721.})})
    assert r.status_code==201;pid=r.json()['project_id']
   if c.get('seed_beam'):Engineering(app.state.domain).save(pid,BeamInput.model_validate(c['seed_beam']))
   bindings={}
   for key,assembly in c.get('seed_thermal',{}).items():
    seeded=client.post(f'/api/projects/{pid}/thermal',json=assembly);assert seeded.status_code==201,seeded.text
    bindings['{{'+key+'}}']=seeded.json()['thermal_id']
   for key,inventory in c.get('seed_lifecycle',{}).items():
    seeded=client.post(f'/api/projects/{pid}/lifecycle',json=inventory);assert seeded.status_code==201,seeded.text
    bindings['{{'+key+'}}']=seeded.json()['lifecycle_id']
   def resolve(value):
    raw=json.dumps(value,ensure_ascii=False)
    for marker,ident in bindings.items():raw=raw.replace(marker,ident)
    return json.loads(raw)
   c=resolve(c);body['message']=c['message']
   if c.get('stale_seed'):
    p=client.get(f'/api/projects/{pid}').json();building={**p['building'],'area_m2':722.}
    changed=client.put(f'/api/projects/{pid}/building',json={'expected_revision':p['revision'],'building':building});assert changed.status_code==200
   if c.get('read_requests'):body['read_requests']=c['read_requests']
   if c.get('plans'):
    body.update(allow_compute=True,calculation_plans=copy.deepcopy(c['plans']))
    if c.get('csv'):
     r=client.post(f'/api/projects/{pid}/files',files={'file':('sensor.csv',c['csv'].encode())});assert r.status_code==201
     for p in body['calculation_plans']:
      if p['kind']=='operation':p['input']['file_id']=r.json()['file_id']
   r=client.post(f'/api/projects/{pid}/agent/chat',json=body);assert r.status_code==202,r.text;t=r.json()
   while t['status']=='running':
    assert time.monotonic()-began<700,'Task exceeded bounded model budget';time.sleep(.25)
    r=client.get(f'/api/projects/{pid}/agent/'+t['agent_id']);assert r.status_code==200;t=r.json()
   previous[c['id']]=(pid,t);answer=t.get('answer') or {};events=t.get('events',[])
   values={f['fact']:f['value'] for row in answer.get('checked_statements',[]) for f in row['facts']}
   rows={r['capability_id']:r for r in answer.get('capability_assessments',[])}
   expected=c.get('capabilities',{});missing=sorted(set(expected)-set(rows));extra=sorted(set(rows)-set(expected))
   checks={'expected_task_status':t['status']==c.get('expected_task_status','succeeded'),'bounded_events':len(events)<=15}
   if expected:checks['exact_capabilities']=not missing and not extra and all(rows[k]['assessment']==v for k,v in expected.items())
   if c.get('facts'):checks['facts']=all(k in values and values[k] is not None and abs(Decimal(values[k])-Decimal(v))<=Decimal('1e-12') for k,v in c['facts'].items())
   if c.get('states'):checks['progress_states']=[p['state'] for p in t.get('calculation_progress',[])]==c['states']
   if c.get('no_facts'):checks['no_numeric_delivery']=not values
   if c.get('forbidden_facts'):checks['no_forbidden_facts']=not (set(values)&set(c['forbidden_facts']))
   if c.get('forbidden_execution'):checks['no_conditional_execution']=not any(e['tool']=='calculation_execute' and e.get('arguments',{}).get('plan_key') in c['forbidden_execution'] for e in events)
   if c.get('critical'):checks['critical_tasks']=any((a.get('result') or {}).get('planned',{}).get('critical_tasks')==c['critical'] for a in answer.get('artifacts',[]))
   if c.get('limit_status'):checks['formal_limit']=any(l.get('state')==c['limit_status'] for l in answer.get('checked_limitations',[]))
   if c.get('limit_states'):checks['all_current_limits']=all(any(l['record_id'].startswith(k+'_') and l['state']==v for l in answer.get('checked_limitations',[])) for k,v in c['limit_states'].items())
   if c.get('required_model_tool'):checks['required_model_tool']=any(e['tool']==c['required_model_tool'] and e.get('origin')=='model' for e in events)
   if c.get('no_writes'):checks['no_new_compute']=not any(e['tool']=='calculation_execute' for e in events)
   if c.get('needs_stale_read'):checks['stale_read']=any(e['tool'].endswith('_read') and (e.get('result') or {}).get('status')=='stale' for e in events)
   if c.get('expect_reason'):checks['exact_observed_reasons']=bool(answer.get('checked_limitations')) and all([d['code'] for d in l.get('stale_details',[])]==[c['expect_reason']] for l in answer['checked_limitations'])
   if c.get('missing_kinds'):checks['exact_missing_kinds']=sorted(x['kind'] for x in answer.get('checked_missing',[]))==sorted(c['missing_kinds'])
   if 'missing_count' in c:checks['scope_record_count']=bool(answer.get('checked_missing')) and all(x['project_record_count']==c['missing_count'] for x in answer['checked_missing'])
   if c.get('missing_scopes'):checks['per_kind_scope']={x['kind']:x['scope'] for x in answer.get('checked_missing',[])}==c['missing_scopes']
   if c.get('missing_scope'):checks['missing_scope']=all(x['scope']==c['missing_scope'] for x in answer.get('checked_missing',[]))
   if c.get('expected_error'):checks['expected_rejection']=c['expected_error'] in (t.get('error') or '')
   if c.get('required_attempt'):checks['actual_calculation_attempt']=any(e['tool']=='calculation_execute' for e in events)
   if c.get('expected_empty'):checks['actual_catalog_empty']=all(not app.state.domain.store.list(k,pid) for k in c['expected_empty'])
   if c.get('read_requests'):
    checks['declared_request_preserved']=t.get('read_requests')==body['read_requests']
    checks['scope_states']=[p['state'] for p in t.get('read_request_progress',[])]==c['read_states']
    checks['scope_coverage']=answer.get('read_request_coverage')=='all_declared_scopes_checked'
    allowed={r['record_id'] for r in body['read_requests'] if r['purpose']=='results'}
    checks['no_wrong_record_delivery']=all(r['record_id'] in allowed for r in answer.get('checked_statements',[])+answer.get('checked_limitations',[]))
    if 'availability_states' in c:
     checked={r['request_key']:r for r in answer.get('checked_availability',[])}
     wanted=[r for r in body['read_requests'] if r['purpose']=='availability']
     checks['exact_availability']=set(checked)=={r['request_key'] for r in wanted} and [checked.get(r['request_key'],{}).get('state') for r in wanted]==c['availability_states']
    if c.get('record_facts'):
     actual={r['record_id']:{f['fact']:f['value'] for f in r['facts']} for r in answer.get('checked_statements',[])}
     checks['per_record_facts']=all(rid in actual and all(actual[rid].get(k) is not None and abs(Decimal(actual[rid][k])-Decimal(v))<=Decimal('1e-12') for k,v in facts.items()) for rid,facts in c['record_facts'].items())
   if c.get('expected_outputs'):
    planned={r['request_key']:r for r in (answer.get('output_plan') or {}).get('items',[])}
    outputs={r['request_key']:r for r in answer.get('requested_outputs',[])}
    checks['required_output_contract']=all(key in planned and key in outputs and
      set(want.get('facts',[]))<=set(planned[key]['fact_keys']) and
      set(want.get('topics',[]))<=set(planned[key]['explanation_topics']) and
      outputs[key]['state']==want.get('state','fulfilled') and
      set(want.get('topics',[]))<={x['topic'] for x in outputs[key]['explanations']}
      for key,want in c['expected_outputs'].items())
    checks['inference_not_certified']=(answer.get('output_plan') or {}).get('intent_verified') is False
   row={'id':c['id'],'cohort':c['cohort'],'task':t,'seconds':round(time.monotonic()-began,3),'model_calls':capture['index']-calls_before,
    'checks':checks,'automated_pass':all(checks.values()),'missing_capabilities':missing,'extra_capabilities':extra,'manual_review':'pending'}
   receipt['cases'].append(row);save();print(json.dumps({k:row[k] for k in ['id','seconds','model_calls','checks','automated_pass']}),flush=True)
 receipt['completed']=True
except Exception as exc:
 receipt['harness_error']={'type':type(exc).__name__,'message':str(exc)[:500]};raise
finally:
 stop.set();thread.join(timeout=7)
 if process.poll() is None:process.terminate()
 process.wait(timeout=30);log.close();receipt['server_stopped']=True;receipt['server_exit']=process.returncode;save()
