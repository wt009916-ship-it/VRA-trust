"""Fixed9B tool/coverage screen with retained actual clarification history."""
import hashlib,json,os,secrets,socket,subprocess,time,sys
from pathlib import Path
from fractions import Fraction as F
import httpx
import tool_protocol as protocol
import position_protocol as calculation
from coverage_guard import guard
ROOT=Path(__file__).resolve().parent

def sha(path):
 with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def write(path,obj):path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def payload(case,config,history):
 fresh=protocol.messages(case['message'])
 return {'model':'vra-nine-b-tools','messages':[fresh[0],*history,fresh[1]],'tools':protocol.tools(case['message']),'tool_choice':'auto','parallel_tool_calls':False,'temperature':0,'seed':config['seed'],'max_tokens':1400,'stream':False,'cache_prompt':False,'chat_template_kwargs':{'enable_thinking':False}}

def assess(case,message):
 row={'strict':False}
 try:
  proposal=protocol.decode(case['message'],message);row['proposal']=proposal
  reviewed=guard(case['message'],proposal);row['review']=reviewed;want=case['expected']
  assert reviewed['outcome']==want['outcome'] and reviewed['issue'] in want['allowed_issues'],'Decision mismatch'
  assert len(reviewed['tasks'])==len(want['tasks']),'Task coverage mismatch'
  for t,g in zip(reviewed['tasks'],want['tasks']):
   assert t['kind']==g['kind'] and {k:v['ref'] for k,v in t['sources'].items()}==g['refs'],'Role/source mismatch'
   for k,v in t['values'].items():
    if k in {'support','no_self_weight','linear_elastic','small_deflection'}:assert v==g['values'][k]
    else:assert F(v)==F(g['values'][k]),'Independent SI value mismatch'
  results=calculation.calculate(reviewed['tasks']);row['calculation']=results
  for t,g in zip(results,want['tasks']):
   assert t['status']==g['status'],'Applicability mismatch'
   assert all(abs(float(t['metrics'][k])-float(F(v)))<=max(1e-9,abs(float(F(v)))*1e-8) for k,v in g['oracle'].items()),'Independent arithmetic mismatch'
   if t['status']=='outside_model_screen':assert t['limitations'],'Missing applicability limits'
  row['strict']=True
 except Exception as exc:row['failure']=type(exc).__name__+': '+str(exc)[:1200]
 return row

def history_append(history,question,message,review):
 history.append(question)
 if message is None:
  # No invented model response; only the actual question remains available.
  return
 history.append(message)
 for call in message.get('tool_calls',[]):
  history.append({'role':'tool','tool_call_id':call['id'],'content':json.dumps(review if review is not None else {'error':'The previous proposal was invalid; no calculation or business write was performed.'},ensure_ascii=False)})

def main():
 f=json.loads((ROOT/'frozen.json').read_text(encoding='utf-8'))
 for n,h in f['source_sha256'].items():assert sha(ROOT/n)==h,'Frozen code changed'
 model=Path(f['model_path']);assert sha(model)==f['model_sha256']
 exe=Path('E:/VRA-local-model-20261106/runtime/llama-server.exe');token=secrets.token_urlsafe(36)
 with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
 env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','TEMP','TMP','COMSPEC','SYSTEMDRIVE'}};env.update(PATH=str(exe.parent)+os.pathsep+str(Path(os.environ['SystemRoot'])/'System32'),LLAMA_API_KEY=token)
 args=[str(exe),'-m',str(model),'--host','127.0.0.1','--port',str(port),'--alias','vra-nine-b-tools','-c','16384','-np','1','-t','4','-ngl','99','--fit','off','--cache-ram','0','--no-context-shift','--offline','--no-webui','--no-agent','--no-webui-mcp-proxy','--no-slots','--jinja','--reasoning','off','--timeout','120']
 out=ROOT/'first-run';out.mkdir(exist_ok=False)
 r={'frozen_sha256':sha(ROOT/'frozen.json'),'model_sha256':sha(model),'runtime_sha256':sha(exe),'server_arguments':args,'tasks':[],'server_stopped':False,'completed':False,'formal_service_touched':False,'application_task_acceptance':False,'write_permission':False,'model_downloaded':False,'training':False}
 proc=None
 with (out/'server.log').open('xb') as log:
  try:
   proc=subprocess.Popen(args,cwd=exe.parent,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW);r['pid']=proc.pid;write(out/'receipt.json',r)
   with httpx.Client(timeout=httpx.Timeout(120,connect=5),trust_env=False,follow_redirects=False) as net:
    began=time.monotonic()
    while time.monotonic()-began<120:
     assert proc.poll() is None,'Server exited before readiness'
     try:
      if net.get(f'http://127.0.0.1:{port}/health',timeout=2).status_code==200:break
     except httpx.HTTPError:pass
     time.sleep(1)
    else:raise TimeoutError('Startup budget exceeded')
    cmd='Get-NetTCPConnection -State Listen | Where-Object OwningProcess -eq '+str(proc.pid)+' | Select-Object LocalAddress,LocalPort | ConvertTo-Json -Compress'
    listeners=json.loads(subprocess.check_output(['powershell.exe','-NoProfile','-NonInteractive','-Command',cmd],timeout=30,creationflags=subprocess.CREATE_NO_WINDOW))
    if isinstance(listeners,dict):listeners=[listeners]
    assert listeners and all(x['LocalAddress']=='127.0.0.1' and x['LocalPort']==port for x in listeners)
    r['loopback_verified']=True
    assert net.post(f'http://127.0.0.1:{port}/v1/chat/completions',json={'model':'vra-nine-b-tools','messages':[]}).status_code==401
    r['unauthenticated_status']=401
    for task in f['tasks']:
     history=[];tr={'id':task['id'],'steps':[]};r['tasks'].append(tr)
     for i,case in enumerate(task['steps']):
      q=payload(case,f,history);assert payload(case,f,[])==case['request_template']
      row={'task_id':task['id'],'step':i+1,'request':q,'history_length':len(history),'strict':False};began=time.monotonic();message=None
      try:
       raw=json.dumps(q,ensure_ascii=False,allow_nan=False).encode();assert len(raw)<=f['limits']['request_bytes'],'Request budget exceeded'
       with net.stream('POST',f'http://127.0.0.1:{port}/v1/chat/completions',content=raw,headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'}) as response:
        row['http_status']=response.status_code;data=bytearray()
        for chunk in response.iter_bytes():
         if time.monotonic()-began>120 or len(data)+len(chunk)>1048576:raise ValueError('Response budget exceeded')
         data.extend(chunk)
        row['raw_response']=data.decode('utf-8');assert response.status_code==200,'Model HTTP request failed'
       obj=json.loads(data);assert obj['model']=='vra-nine-b-tools';choice=obj['choices'][0];assert len(obj['choices'])==1 and choice['finish_reason'] in {'stop','tool_calls'},'Incomplete model response'
       message=choice['message'];row['usage']=obj.get('usage');row.update(assess(case,message))
      except Exception as exc:row['failure']=type(exc).__name__+': '+str(exc)[:1200]
      row['seconds']=round(time.monotonic()-began,3);write(out/f"{task['id']}-{i+1}.json",row)
      tr['steps'].append({k:row[k] for k in ['step','strict','seconds','failure'] if k in row});write(out/'receipt.json',r)
      print(json.dumps({'id':task['id'],**tr['steps'][-1]},ensure_ascii=False),flush=True)
      history_append(history,q['messages'][-1],message,row.get('review'))
     tr['strict']=all(x['strict'] for x in tr['steps']);write(out/'receipt.json',r)
    passed={t['id'] for t in r['tasks'] if t['strict']};r.update(completed=True,passed=len(passed),total=len(f['tasks']),requests=sum(len(t['steps']) for t in r['tasks']),critical_failed=sorted(set(f['gate']['critical'])-passed),eligible=len(passed)>=f['gate']['minimum_complete_tasks'] and set(f['gate']['critical'])<=passed)
  finally:
   if proc:
    if proc.poll() is None:proc.terminate()
    try:proc.wait(timeout=15)
    except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=10)
    r['server_stopped']=proc.poll() is not None
   write(out/'receipt.json',r)
 print(json.dumps({k:r.get(k) for k in ['completed','passed','total','requests','critical_failed','eligible','server_stopped']}),flush=True)
if __name__=='__main__':main()
