"""Four previously seen diagnostic replays; NEVER a fresh acceptance score."""
import hashlib,json,os,secrets,socket,subprocess,time,sys
from pathlib import Path
from fractions import Fraction as F
import httpx
import tool_protocol as protocol
import position_protocol as calculations
BASE=Path(__file__).resolve().parent
OUT=BASE/'tool-diagnostic'
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def write(p,obj):p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def freeze():
 OUT.mkdir(exist_ok=False);old=json.loads((BASE/'frozen.json').read_text(encoding='utf-8'))
 cases=[c for c in old['cases'] if c['id'] in ['S01','S05','S13','S17']]
 rows=[]
 for c in cases:
  q={'model':'vra-tool-diagnostic','messages':protocol.messages(c['message']),'tools':protocol.tools(c['message']),'tool_choice':'auto','temperature':0,'seed':43721,'max_tokens':1400,'stream':False,'chat_template_kwargs':{'enable_thinking':False},'cache_prompt':False}
  rows.append({'case':c,'payload':q})
 f={'scope':'Previously seen four-case diagnostic; contract+prompt+tool framing changed together; no causal isolation, no acceptance or score gain, no write permission','cases':rows,'model_sha256':old['model_sha256'],'source_sha256':{n:sha(BASE/n) for n in ['source_catalog.py','position_protocol.py','tool_protocol.py','run_tool_diagnostic.py']},'original_frozen_sha256':sha(BASE/'frozen.json')}
 write(OUT/'frozen.json',f);print(json.dumps({'frozen_sha256':sha(OUT/'frozen.json'),'diagnostic_requests':4,'unseen_requests':0}))
def main():
 f=json.loads((OUT/'frozen.json').read_text(encoding='utf-8'))
 for n,h in f['source_sha256'].items():assert sha(BASE/n)==h
 model=Path('E:/VRA-local-model-20261106/models/Qwen3-4B-Q4_K_M.gguf');assert sha(model)==f['model_sha256']
 exe=Path('E:/VRA-local-model-20261106/runtime/llama-server.exe');token=secrets.token_urlsafe(36)
 with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
 args=[str(exe),'-m',str(model),'--host','127.0.0.1','--port',str(port),'--alias','vra-tool-diagnostic','-c','16384','-np','1','-t','4','-ngl','99','--fit','off','--cache-ram','0','--no-context-shift','--offline','--no-webui','--no-agent','--no-webui-mcp-proxy','--no-slots','--jinja','--reasoning','off','--timeout','120']
 env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','TEMP','TMP','COMSPEC','SYSTEMDRIVE'}};env.update(PATH=str(exe.parent)+os.pathsep+str(Path(os.environ['SystemRoot'])/'System32'),LLAMA_API_KEY=token)
 receipt={'scope':f['scope'],'frozen_sha256':sha(OUT/'frozen.json'),'runtime_sha256':sha(exe),'server_arguments':args,'cases':[],'server_stopped':False,'score_delta':0,'application_accepted':False};proc=None
 with (OUT/'server.log').open('xb') as log:
  try:
   proc=subprocess.Popen(args,cwd=exe.parent,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW);receipt['pid']=proc.pid;write(OUT/'receipt.json',receipt)
   with httpx.Client(timeout=httpx.Timeout(120,connect=5),trust_env=False,follow_redirects=False) as net:
    began=time.monotonic()
    while time.monotonic()-began<120:
     assert proc.poll() is None,'Server exited'
     try:
      if net.get(f'http://127.0.0.1:{port}/health',timeout=2).status_code==200:break
     except httpx.HTTPError:pass
     time.sleep(1)
    else:raise TimeoutError('Startup budget exceeded')
    cmd='Get-NetTCPConnection -State Listen | Where-Object OwningProcess -eq '+str(proc.pid)+' | Select-Object LocalAddress,LocalPort | ConvertTo-Json -Compress'
    listeners=json.loads(subprocess.check_output(['powershell.exe','-NoProfile','-NonInteractive','-Command',cmd],timeout=30,creationflags=subprocess.CREATE_NO_WINDOW))
    if isinstance(listeners,dict):listeners=[listeners]
    assert listeners and all(x['LocalAddress']=='127.0.0.1' and x['LocalPort']==port for x in listeners)
    receipt['loopback_verified']=True
    assert net.post(f'http://127.0.0.1:{port}/v1/chat/completions',json={'model':'vra-tool-diagnostic','messages':[]}).status_code==401
    receipt['unauthenticated_status']=401
    for item in f['cases']:
     case=item['case'];q=item['payload'];row={'id':case['id'],'request':q,'diagnostic_match':False};began=time.monotonic()
     try:
      raw=json.dumps(q,ensure_ascii=False).encode();assert len(raw)<=196608
      with net.stream('POST',f'http://127.0.0.1:{port}/v1/chat/completions',content=raw,headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'}) as response:
       data=bytearray();row['http_status']=response.status_code
       for chunk in response.iter_bytes():
        if time.monotonic()-began>120 or len(data)+len(chunk)>1048576:raise ValueError('Response budget exceeded')
        data.extend(chunk)
       row['raw_response']=data.decode('utf-8');assert response.status_code==200
      obj=json.loads(data);assert obj['model']=='vra-tool-diagnostic';choice=obj['choices'][0]
      assert len(obj['choices'])==1 and choice['finish_reason'] in {'stop','tool_calls'}
      r=protocol.decode(case['message'],choice['message']);row['review']=r;row['usage']=obj.get('usage');gold=case['expected']
      assert r['outcome']==gold['outcome'] and r['issue'] in gold['allowed_issues'],'Decision mismatch'
      assert len(r['tasks'])==len(gold['tasks']),'Task coverage mismatch'
      for t,g in zip(r['tasks'],gold['tasks']):assert t['kind']==g['kind'] and {k:v['ref'] for k,v in t['sources'].items()}==g['refs'],'Role/source mismatch'
      result=calculations.calculate(r['tasks']);row['calculation']=result
      for t,g in zip(result,gold['tasks']):
       assert t['status']==g['status']
       assert all(abs(float(t['metrics'][k])-float(F(v)))<=max(1e-9,abs(float(F(v)))*1e-8) for k,v in g['oracle'].items())
      row['diagnostic_match']=True
     except Exception as exc:row['failure']=type(exc).__name__+': '+str(exc)[:1000]
     row['seconds']=round(time.monotonic()-began,3);write(OUT/(case['id']+'.json'),row)
     receipt['cases'].append({k:row[k] for k in ['id','diagnostic_match','failure','seconds'] if k in row});write(OUT/'receipt.json',receipt);print(json.dumps(receipt['cases'][-1],ensure_ascii=False),flush=True)
  finally:
   if proc:
    if proc.poll() is None:proc.terminate()
    try:proc.wait(timeout=15)
    except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=10)
    receipt['server_stopped']=proc.poll() is not None
   write(OUT/'receipt.json',receipt)
 print(json.dumps({'diagnostic_matches':sum(x['diagnostic_match'] for x in receipt['cases']),'total':len(receipt['cases']),'server_stopped':receipt['server_stopped'],'score_delta':0}),flush=True)
if __name__=='__main__':freeze() if sys.argv[-1]=='freeze' else main()
