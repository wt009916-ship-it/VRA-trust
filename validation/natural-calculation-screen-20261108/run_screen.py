"""Single frozen screening run; no API endpoint, no database, no adaptive retry."""
import hashlib,json,os,secrets,socket,subprocess,sys,time
from pathlib import Path
from fractions import Fraction
import httpx
import draft_protocol as protocol
ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]
sys.path.insert(0,str(REPO))
from backend import thermal,engineering

def sha(path):
 with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def write(path,obj):path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def calculators(tasks,case):
 results=[]
 for ti,task in enumerate(tasks):
  rows=task['parameters'];v={k:r['value'] for k,r in rows.items()}
  def f(k):return float(v[k])
  if task['kind']=='thermal':
   count=len([k for k in v if k.endswith('.thickness')]);layers=[]
   for i in range(count):
    prefix=f'layers.{i}.'
    layers.append(dict(name=f'User layer {i+1}',thickness=f(prefix+'thickness'),thickness_unit='m',conductivity=f(prefix+'conductivity'),conductivity_unit='W/(m K)',correction_factor=f(prefix+'correction'),correction_basis='User quote: '+rows[prefix+'correction']['quote'],source='User declared input; not independently verified'))
   body=thermal.Assembly(name=case['id'],layers=layers,rsi_m2k_w=f('rsi'),rse_m2k_w=f('rse'),surface_basis='User quotes: '+rows['rsi']['quote']+'; '+rows['rse']['quote'],application='Synthetic extraction reference; one-dimensional steady opaque assembly only')
   result=thermal.calculate(body);metrics=result
  else:
   body=engineering.BeamInput(name=case['id'],support=v['support'],span=f('span'),span_unit='m',width=f('width'),depth=f('depth'),section_unit='m',elastic_modulus=f('modulus'),modulus_unit='Pa',geometry_source='User declaration, not independent evidence',material_source='User declaration, not independent evidence',support_basis='User quote: '+rows['support']['quote'],analysis_basis='User quote: '+rows['analysis']['quote'],loads=[dict(type='point',name='User point load',magnitude=f('force'),unit='N',position=f('position'),position_unit='m',source='User declared force and position')])
   result=engineering.calculate(body);metrics=result.get('metrics') or {}
  checks={key:abs(float(metrics[key])-float(Fraction(want)))<=max(1e-9,abs(float(Fraction(want)))*1e-8) for key,want in case['expected']['tasks'][ti]['oracle'].items()}
  results.append({'input':body.model_dump(mode='json'),'status':result['status'],'metrics':{k:metrics.get(k) for k in checks},'independent_oracle_checks':checks})
 return results

def assess(case,response):
 result={'strict':False,'input_verified':False,'calculator_checked':False}
 try:
  choice=response['choices'][0]
  if len(response['choices'])!=1 or choice['finish_reason']!='stop': raise ValueError('Incomplete response')
  obj=json.loads(choice['message']['content']);result['draft']=obj
  tasks=protocol.verify(case['message'],obj);result['verified_sources']=tasks;result['input_verified']=True
  want=case['expected']
  if obj['outcome']!=want['outcome'] or sorted(obj['issues'])!=sorted(want['issues']):raise ValueError('Outcome/issue differs from independent oracle')
  if len(tasks)!=len(want['tasks']):raise ValueError('Task coverage mismatch')
  for task,gold in zip(tasks,want['tasks']):
   got={k:v['value'] for k,v in task['parameters'].items()}
   if task['kind']!=gold['kind'] or set(got)!=set(gold['values']):raise ValueError('Task kind or fields mismatch')
   for key,value in got.items():
    if key in {'support','analysis'}:
     if value!=gold['values'][key]:raise ValueError('Semantic field mismatch: '+key)
    elif Fraction(value)!=Fraction(gold['values'][key]):raise ValueError('Numeric field mismatch: '+key)
  if tasks:
   result['calculation']=calculators(tasks,case)
   result['calculator_checked']=all(r['status']=='calculated' and all(r['independent_oracle_checks'].values()) for r in result['calculation'])
   if not result['calculator_checked']:raise ValueError('Calculation or independent arithmetic mismatch')
  result['strict']=True
 except Exception as exc:result['failure']=type(exc).__name__+': '+str(exc)[:600]
 return result

def main():
 frozen=ROOT/'frozen.json';config=json.loads(frozen.read_text(encoding='utf-8'));frozen_hash=sha(frozen)
 for name,digest in config['source_sha256'].items():assert sha(ROOT/name)==digest,'Source changed after freeze: '+name
 model=Path(config['model']['path']);assert sha(model)==config['model']['sha256']
 out=ROOT/'first-run';out.mkdir(exist_ok=False)
 exe=Path('E:/VRA-local-model-20261106/runtime/llama-server.exe')
 receipt={'frozen_sha256':frozen_hash,'model_sha256':sha(model),'runtime_sha256':sha(exe),'product_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),'source_sha256':config['source_sha256'],'arms':[],'completed':False,'formal_service_touched':False,'application_task_acceptance':False,'write_permission':False}
 write(out/'receipt.json',receipt)
 for arm in config['arms']:
  aout=out/arm['name'];aout.mkdir();token=secrets.token_urlsafe(36)
  with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
  env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','TEMP','TMP','COMSPEC','SYSTEMDRIVE'}}
  env.update(PATH=str(exe.parent)+os.pathsep+str(Path(os.environ['SystemRoot'])/'System32'),LLAMA_API_KEY=token)
  args=[str(exe),'-m',str(model),'--host','127.0.0.1','--port',str(port),'--alias','vra-draft-screen','-c','16384','-np','1','-t','4','-ngl','99','--fit','off','--cache-ram','0','--no-context-shift','--offline','--no-webui','--no-agent','--no-webui-mcp-proxy','--no-slots','--jinja','--reasoning','on' if arm['thinking'] else 'off','--reasoning-format','deepseek','--timeout','120']
  if arm['thinking']:args+=['--reasoning-budget',str(arm['reasoning_budget'])]
  entry={'name':arm['name'],'server_arguments':args,'cases':[],'server_stopped':False};receipt['arms'].append(entry)
  proc=None
  with (aout/'server.log').open('xb') as log:
   try:
    proc=subprocess.Popen(args,cwd=exe.parent,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
    entry['server_pid']=proc.pid;write(out/'receipt.json',receipt)
    with httpx.Client(timeout=httpx.Timeout(120,connect=5),follow_redirects=False,trust_env=False) as net:
     began=time.monotonic()
     while time.monotonic()-began<120:
      assert proc.poll() is None,'Model server exited during startup'
      try:
       if net.get(f'http://127.0.0.1:{port}/health',timeout=2).status_code==200:break
      except httpx.HTTPError:pass
      time.sleep(1)
     else:raise TimeoutError('Model startup exceeded budget')
     command='Get-NetTCPConnection -State Listen | Where-Object OwningProcess -eq '+str(proc.pid)+' | Select-Object LocalAddress,LocalPort | ConvertTo-Json -Compress'
     listeners=json.loads(subprocess.check_output(['powershell.exe','-NoProfile','-NonInteractive','-Command',command],timeout=30,creationflags=subprocess.CREATE_NO_WINDOW))
     if isinstance(listeners,dict):listeners=[listeners]
     assert listeners and all(v['LocalAddress']=='127.0.0.1' and v['LocalPort']==port for v in listeners)
     entry['loopback_verified']=True
     assert net.post(f'http://127.0.0.1:{port}/v1/chat/completions',json={'model':'vra-draft-screen','messages':[]}).status_code==401
     entry['unauthenticated_status']=401
     for seed in arm['seeds']:
      for case in config['cases']:
       payload={'model':'vra-draft-screen','messages':[{'role':'system','content':config['system']},{'role':'user','content':case['message']}],'response_format':{'type':'json_schema','json_schema':{'name':'engineering_draft','strict':True,'schema':config['schema']}},'stream':False,'seed':seed,'cache_prompt':False,'chat_template_kwargs':{'enable_thinking':arm['thinking']},**{k:arm[k] for k in ['temperature','max_tokens','top_p','top_k','min_p'] if k in arm}}
       raw=json.dumps(payload,ensure_ascii=False,allow_nan=False).encode();assert len(raw)<=config['limits']['request_bytes']
       row={'id':case['id'],'seed':seed,'request':payload,'strict':False};start=time.monotonic()
       try:
        with net.stream('POST',f'http://127.0.0.1:{port}/v1/chat/completions',content=raw,headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'}) as response:
         row['http_status']=response.status_code;data=bytearray()
         for chunk in response.iter_bytes():
          if time.monotonic()-start>120 or len(data)+len(chunk)>1048576:raise ValueError('Response exceeded budget')
          data.extend(chunk)
         row['raw_response']=data.decode('utf-8')
         if response.status_code!=200:raise ValueError('HTTP '+str(response.status_code))
        obj=json.loads(data);row['usage']=obj.get('usage');row.update(assess(case,obj))
       except Exception as exc:row['failure']=type(exc).__name__+': '+str(exc)[:600]
       row['seconds']=round(time.monotonic()-start,3)
       write(aout/f'{seed}-{case["id"]}.json',row)
       entry['cases'].append({k:row[k] for k in ['id','seed','strict','seconds','failure'] if k in row});write(out/'receipt.json',receipt)
       print(json.dumps({'arm':arm['name'],'seed':seed,'id':case['id'],'strict':row['strict'],'seconds':row['seconds'],'failure':row.get('failure')},ensure_ascii=False),flush=True)
   except Exception as exc:
    entry['fatal_error']=type(exc).__name__+': '+str(exc)[:600]
    raise
   finally:
    if proc:
     if proc.poll() is None:proc.terminate()
     try:proc.wait(timeout=15)
     except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=10)
     entry['server_stopped']=proc.poll() is not None
    write(out/'receipt.json',receipt)
 baseline={r['id'] for r in receipt['arms'][0]['cases'] if r['strict']}
 critical=set(config['gate']['critical']);decisions=[]
 for arm,entry in zip(config['arms'],receipt['arms']):
  seed_results=[]
  for seed in arm['seeds']:
   passed={r['id'] for r in entry['cases'] if r['seed']==seed and r['strict']}
   eligible=len(passed)>=15 and critical<=passed
   if arm['name']!='greedy':eligible=eligible and baseline<=passed and len(passed)-len(baseline)>=4
   seed_results.append({'seed':seed,'passed':len(passed),'total':18,'regressions':sorted(baseline-passed),'critical_failed':sorted(critical-passed),'eligible':eligible})
  decisions.append({'name':arm['name'],'seeds':seed_results,'eligible':all(s['eligible'] for s in seed_results)})
 receipt.update(completed=True,decisions=decisions)
 write(out/'receipt.json',receipt);print(json.dumps({'complete':True,'decisions':decisions},ensure_ascii=False),flush=True)
if __name__=='__main__':main()
