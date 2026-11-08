"""One frozen 18-request source-position screen. No retry or product service."""
import sys,os,socket,secrets,time,hashlib,json,subprocess
from pathlib import Path
from fractions import Fraction as F
import httpx
import position_protocol as protocol
ROOT=Path(__file__).resolve().parent

def sha(p):
 with p.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def write(p,data):p.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def payload(case,config):
 return {'model':'vra-source-positions','messages':protocol.messages(case['message']),'response_format':{'type':'json_schema','json_schema':{'name':'source_plan','strict':True,'schema':protocol.schema(case['message'])}},'temperature':0,'seed':config['seed'],'max_tokens':1400,'stream':False,'cache_prompt':False,'chat_template_kwargs':{'enable_thinking':False}}

def assess(case,response):
 row={'strict':False,'model_outcome_correct':False,'guarded':False}
 try:
  choice=response['choices'][0]
  assert len(response['choices'])==1 and choice['finish_reason']=='stop','Incomplete model output'
  review=protocol.review(case['message'],choice['message']['content']);row['review']=review;row['guarded']=review['guard'] is not None
  want=case['expected'];proposal=review['model_proposal']
  row['model_outcome_correct']=proposal['outcome']==want['outcome'] and proposal['issue'] in want['allowed_issues']
  assert review['outcome']==want['outcome'] and review['issue'] in want['allowed_issues'],'Application decision mismatch'
  tasks=review['tasks'];assert len(tasks)==len(want['tasks']),'Task coverage mismatch'
  for task,gold in zip(tasks,want['tasks']):
   assert task['kind']==gold['kind'],'Task kind mismatch'
   assert {k:v['ref'] for k,v in task['sources'].items()}==gold['refs'],'Parameter role/source position mismatch'
   assert set(task['values'])==set(gold['values']),'Field coverage mismatch'
   for k,v in task['values'].items():
    if k in {'support','no_self_weight','linear_elastic','small_deflection'}:assert v==gold['values'][k]
    else:assert F(v)==F(gold['values'][k]),'Independent SI value mismatch'
  calculations=protocol.calculate(tasks);row['calculation']=calculations
  for got,gold in zip(calculations,want['tasks']):
   assert got['status']==gold['status'],'Applicability status mismatch'
   for k,v in gold['oracle'].items():assert abs(float(got['metrics'][k])-float(F(v)))<=max(1e-9,abs(float(F(v)))*1e-8),'Independent arithmetic mismatch'
   if got['status']=='outside_model_screen':assert got['limitations'],'Missing applicability limitation'
  row['strict']=True
 except Exception as exc:row['failure']=type(exc).__name__+': '+str(exc)[:1200]
 return row

def main():
 f=json.loads((ROOT/'frozen.json').read_text(encoding='utf-8'))
 for name,h in f['source_sha256'].items():assert sha(ROOT/name)==h,'Frozen source changed'
 model=Path('E:/VRA-local-model-20261106/models/Qwen3-4B-Q4_K_M.gguf');assert sha(model)==f['model_sha256']
 out=ROOT/'first-run';out.mkdir(exist_ok=False)
 exe=Path('E:/VRA-local-model-20261106/runtime/llama-server.exe');token=secrets.token_urlsafe(36)
 with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
 env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','TEMP','TMP','COMSPEC','SYSTEMDRIVE'}}
 env.update(PATH=str(exe.parent)+os.pathsep+str(Path(os.environ['SystemRoot'])/'System32'),LLAMA_API_KEY=token)
 args=[str(exe),'-m',str(model),'--host','127.0.0.1','--port',str(port),'--alias','vra-source-positions','-c','16384','-np','1','-t','4','-ngl','99','--fit','off','--cache-ram','0','--no-context-shift','--offline','--no-webui','--no-agent','--no-webui-mcp-proxy','--no-slots','--jinja','--reasoning','off','--timeout','120']
 receipt={'frozen_sha256':sha(ROOT/'frozen.json'),'runtime_sha256':sha(exe),'model_sha256':sha(model),'server_arguments':args,'cases':[],'server_stopped':False,'completed':False,'formal_service_touched':False,'application_task_acceptance':False,'write_permission':False}
 proc=None
 with (out/'server.log').open('xb') as log:
  try:
   proc=subprocess.Popen(args,cwd=exe.parent,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW);receipt['pid']=proc.pid;write(out/'receipt.json',receipt)
   with httpx.Client(timeout=httpx.Timeout(120,connect=5),trust_env=False,follow_redirects=False) as net:
    start=time.monotonic()
    while time.monotonic()-start<120:
     assert proc.poll() is None,'Server exited'
     try:
      if net.get(f'http://127.0.0.1:{port}/health',timeout=2).status_code==200:break
     except httpx.HTTPError:pass
     time.sleep(1)
    else:raise TimeoutError('Startup budget exceeded')
    command='Get-NetTCPConnection -State Listen | Where-Object OwningProcess -eq '+str(proc.pid)+' | Select-Object LocalAddress,LocalPort | ConvertTo-Json -Compress'
    listeners=json.loads(subprocess.check_output(['powershell.exe','-NoProfile','-NonInteractive','-Command',command],timeout=30,creationflags=subprocess.CREATE_NO_WINDOW))
    if isinstance(listeners,dict):listeners=[listeners]
    assert listeners and all(x['LocalAddress']=='127.0.0.1' and x['LocalPort']==port for x in listeners)
    receipt['loopback_verified']=True
    assert net.post(f'http://127.0.0.1:{port}/v1/chat/completions',json={'model':'vra-source-positions','messages':[]}).status_code==401
    receipt['unauthenticated_status']=401
    for case in f['cases']:
     q=f['requests'][case['id']];assert q==payload(case,f)
     raw=json.dumps(q,ensure_ascii=False).encode();assert len(raw)<=f['request_bytes']
     row={'id':case['id'],'request':q,'strict':False};began=time.monotonic()
     try:
      with net.stream('POST',f'http://127.0.0.1:{port}/v1/chat/completions',content=raw,headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'}) as response:
       row['http_status']=response.status_code;data=bytearray()
       for chunk in response.iter_bytes():
        if time.monotonic()-began>120 or len(data)+len(chunk)>1048576:raise ValueError('Response budget exceeded')
        data.extend(chunk)
       row['raw_response']=data.decode('utf-8');assert response.status_code==200,'HTTP request failed'
      obj=json.loads(data);assert obj['model']=='vra-source-positions';row['usage']=obj.get('usage');row.update(assess(case,obj))
     except Exception as exc:row['failure']=type(exc).__name__+': '+str(exc)[:1200]
     row['seconds']=round(time.monotonic()-began,3);write(out/(case['id']+'.json'),row)
     receipt['cases'].append({k:row[k] for k in ['id','strict','seconds','failure','guarded','model_outcome_correct'] if k in row});write(out/'receipt.json',receipt)
     print(json.dumps(receipt['cases'][-1],ensure_ascii=False),flush=True)
   passed={r['id'] for r in receipt['cases'] if r['strict']}
   receipt.update(completed=True,passed=len(passed),total=18,critical_failed=sorted(set(f['gate']['critical'])-passed),eligible=len(passed)>=15 and set(f['gate']['critical'])<=passed)
  finally:
   if proc:
    if proc.poll() is None:proc.terminate()
    try:proc.wait(timeout=15)
    except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=10)
    receipt['server_stopped']=proc.poll() is not None
   write(out/'receipt.json',receipt)
 print(json.dumps({k:receipt.get(k) for k in ['completed','passed','total','critical_failed','eligible','server_stopped']}),flush=True)
if __name__=='__main__':main()
