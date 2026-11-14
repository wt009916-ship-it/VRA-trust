"""Fresh live API/model screen. Instrumentation logs gateway messages without replacing responses."""
import hashlib,json,math,os,secrets,socket,subprocess,sys,time
from pathlib import Path
from fractions import Fraction
import httpx
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
BASE=Path(__file__).resolve().parent
SOURCE=Path('C:/Users/18483/AppData/Local/Temp/vra-utility-reference-20261109/frozen-v2')
MODEL=Path('C:/Users/18483/AppData/Local/Temp/vra-qwen35-9b-20261108/Qwen3.5-9B-Q4_K_M.gguf')
EXE=Path('E:/VRA-local-model-20261106/runtime/llama-server.exe')
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(p,x):Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def port():
 with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]
def serve():
 import uvicorn
 from backend.api import app
 gateway=app.state.agent.local_model;original=gateway.complete;counter=0
 def captured(messages,tools,**kwargs):
  nonlocal counter
  counter+=1;p=Path(os.environ['VRA_CAPTURE_DIR'])/('model-call-%03d.json'%counter)
  row={'messages':messages,'tools':tools,'response_mode':kwargs.get('response_mode','tools'),'instrumentation':'Unmodified gateway return including original JSON action response; no model substitution. Adapter translates validated model actions to controller calls.'};save(p,row)
  try:
   answer=original(messages,tools,**kwargs);row['response']=answer;return answer
  except Exception as e:
   row['error']=type(e).__name__+': '+str(e)
   if hasattr(e,'response'):row['raw_rejected_response']=e.response
   raise
  finally:save(p,row)
 gateway.complete=captured
 uvicorn.run(app,host='127.0.0.1',port=int(sys.argv[2]),log_level='warning')

def run():
 out=BASE/('live-'+os.environ.get('VRA_METRIC_RUN','first'));out.mkdir(exist_ok=False)
 runtime=Path('C:/Users/18483/AppData/Local/Temp/vra-agent-metric-reads-live-20261113-'+os.environ.get('VRA_METRIC_RUN','a'));runtime.mkdir(exist_ok=False)
 captures=out/'model-calls';captures.mkdir();r={'completed':False,'scope':'Eight new questions: catalog-constrained metric reads and independent unresolved relationship control. No claim that the full metric/relationship work batch is complete. Actual JSON-constrained model-selected actions, not native function calling. Public synthetic 2020 leap-year source; no browser, training, real building or old question replay.','checks':[],'tasks':[],'processes_stopped':False};save(out/'receipt.json',r)
 frozen=json.loads((SOURCE/'frozen.json').read_text(encoding='utf-8'))
 for name,digest in frozen['files'].items():assert sha(SOURCE/name)==digest
 expected=next(c for c in frozen['cases'] if c['id']=='2020')['monthly_expected']
 e_total=float(sum(Fraction(x['electricity_kwh']) for x in expected));g_total=float(sum(Fraction(x['gas_kwh']) for x in expected))
 oracle={v:json.loads((SOURCE/'2020'/f'{v}-expected.json').read_text()) for v in ('matched','bias','cancellation','zero')}
 token=secrets.token_urlsafe(36);ap,mp=port(),port();processes=[];logs=[]
 r.update(runtime=str(runtime),script_sha256=sha(__file__),source_sha256=sha(SOURCE/'frozen.json'),independent_totals={'electricity_kwh':e_total,'gas_kwh':g_total},product_sha256={str(p.relative_to(ROOT)):sha(p) for p in sorted((ROOT/'backend').glob('*.py'))})
 def launch(args,env,name,cwd):
  log=(out/name).open('xb');logs.append(log);p=subprocess.Popen(args,cwd=cwd,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW);processes.append(p);return p
 def check(name,yes):
  r['checks'].append({'name':name,'passed':bool(yes)});save(out/'receipt.json',r);assert yes,name
 try:
  app=launch([sys.executable,'-B','-X','utf8',str(Path(__file__).resolve()),'serve',str(ap)],{**os.environ,'VRA_DATA_DIR':str(runtime),'ENERGYPLUS_EXE':'F:/EnergyPlusV9-0-1/energyplus.exe','VRA_LOCAL_MODEL_TOKEN':token,'VRA_CAPTURE_DIR':str(captures),'PYTHONDONTWRITEBYTECODE':'1'},'application.log',ROOT)
  with httpx.Client(base_url=f'http://127.0.0.1:{ap}',timeout=120,trust_env=False) as c:
   for _ in range(200):
    assert app.poll() is None,'Application stopped'
    try:
     if c.get('/api/health').status_code==200:break
    except httpx.ConnectError:pass
    time.sleep(.1)
   else:raise TimeoutError('Application startup')
   x=c.post('/api/auth/register',json={'username':'agent_energy_isolated','display_name':'隔离Agent验收','password':secrets.token_urlsafe(32)});check('isolated_account',x.status_code==200);c.headers['X-CSRF-Token']=x.json()['csrf_token']
   def request(method,url,body=None,files=None):
    x=c.request(method,url,json=body,files=files)
    if x.status_code>=400:save(out/'setup-error.json',{'method':method,'path':url,'status':x.status_code,'response':x.text});x.raise_for_status()
    return x.json()
   def project(name):return request('POST','/api/projects',{'name':name,'building':{'use':'reference','location':'Synthetic public reference, no surveyed building','region':'TEST','area_m2':25.0}})['project_id']
   pid=project('Agent energy synthetic screen');other=project('Separate project without source access');base='/api/projects/'+pid;ev={}
   def upload(name,kind):
    data=(SOURCE/'2020'/name).read_bytes();file=request('POST',base+'/files',files={'file':(name,data)})
    body={'type':kind,'name':name,'source_file':file['file_id'],'source_locator':'Existing frozen independent synthetic input, new actual run','authority':'Reference author','permission':'Public reference local verification','acquisition_method':'Declared synthetic schedules, not measurements','responsible_person':'Independent acceptance','status':'ASSUMED'}
    if kind=='idf':body['scheme_id']='baseline'
    item=request('POST',base+'/evidence',body);item=request('PATCH',base+'/evidence/'+item['evidence_id'],{'expected_revision':item['revision'],'review_state':'confirmed','responsible_person':'Independent acceptance','review_note':'Synthetic arithmetic context, no real building certification'});ev[name]=item
   for name,kind in [('model.idf','idf'),('weather.epw','epw')]+[(v+'.csv','bill') for v in ('matched','bias','cancellation','zero')]:upload(name,kind)
   run=request('POST','/api/runs',{'project_id':pid,'scheme_id':'baseline','factor_profile_id':'none'});rid=run['run_id'];until=time.monotonic()+600
   while time.monotonic()<until:
    run=request('GET','/api/runs/'+rid)
    if run['status'] not in ('queued','running'):break
    time.sleep(1)
   save(out/'native-run.json',run);check('fresh_native_source',run['status']=='succeeded');print('Fresh native source succeeded',flush=True)
   records={}
   def compare(variant,name=None):
    item=request('POST',base+'/utility-comparisons',{'name':name or 'Energy '+variant,'purpose':'Independent synthetic Agent reading acceptance, never calibration','run_id':rid,'bill_evidence_id':ev[variant+'.csv']['evidence_id'],'meter':'Electricity:Facility','bill_nature':'synthetic','alignment':'calendar_pattern' if variant=='wrong_year' else 'exact_calendar','period_kind':'calendar_month','clock_source':'Frozen local standard time, no DST','boundary_note':'Whole facility electricity, excluding gas; synthetic source','max_abs_mbe_percent':5.0,'max_cvrmse_percent':5.0,'threshold_source':'Test declaration only, no certification'})
    return item
   for variant in ('matched','bias','cancellation','zero'):records[variant]=compare(variant)
   records['enduse']=request('POST',base+'/end-use-ledgers',{'name':'Native equipment ledger','purpose':'Inspect native energy carriers with declared synthetic input only','run_id':rid})
   save(out/'records-before.json',records);save(out/'evidence.json',ev)
   for variant in ('matched','bias','cancellation','zero'):
    for key,ref in [('mbe_percent','mbe_pct'),('cvrmse_percent','cvrmse_pct'),('rmse_kwh','rmse_kwh')]:
     actual=records[variant]['result']['statistics'][key];want=oracle[variant][ref]
     check(variant+'_'+key,actual is None if want is None else actual is not None and math.isclose(actual,float(want),abs_tol=1e-8,rel_tol=1e-10))
   # Security uses the same live endpoint and never reads another user's private data.
   task_url=base+'/agent/chat';basic={'message':'读取账单总量','mode':'local_model','allow_compute':False}
   csrf=c.headers.pop('X-CSRF-Token');check('agent_missing_csrf',c.post(task_url,json=basic).status_code==403);c.headers['X-CSRF-Token']=csrf
   with httpx.Client(base_url=c.base_url,trust_env=False) as anon:check('agent_anonymous',anon.post(task_url,json=basic).status_code==401)
   tasks=[]
   def add(ident,message,scopes,expect,*,model=False,infer=True,project_id=pid,action=None):
    requests=[{'request_key':key,'kind':kind,'purpose':'results','record_id':records[which][kind+'_id'] if which in records else which} for key,kind,which in scopes]
    tasks.append({'id':ident,'message':message,'body':{'message':message,'mode':'local_model','allow_compute':False,'read_requests':requests,'read_execution':'model' if model else 'application','infer_outputs':infer},'project_id':project_id,'expected':expect,'action':action})
   wall={'name':'Independent 20261113 wall','rsi_m2k_w':.11,'rse_m2k_w':.06,'surface_basis':'Declared reference films, not compliance defaults','application':'Steady opaque wall reference',
         'layers':[{'name':name,'thickness':d,'thickness_unit':u,'conductivity':k,'conductivity_unit':ku,'correction_factor':corr,'correction_basis':'Declared synthetic adjustment','source':'Public synthetic acceptance input'}
                   for name,d,u,k,ku,corr in [('Mineral A',160.,'mm',.8,'W/(m K)',1.),('Insulation B',6.,'cm',40.,'mW/(m K)',1.2)]]}
   wall_record=request('POST',base+'/thermal',wall);records['wall']=wall_record
   save(out/'records-before.json',records)
   r_wall=Fraction(11,100)+Fraction(6,100)+Fraction(160,1000)/Fraction(8,10)+Fraction(60,1000)/(Fraction(40,1000)*Fraction(12,10))
   assert r_wall==Fraction(81,50)
   thermal_oracle={'total_resistance_m2k_w':float(r_wall),'u_w_m2k':float(1/r_wall),'formula':'0.11+0.06+0.160/0.8+0.060/(0.040*1.2)=81/50; U=50/81'}
   check('fresh_thermal_R',math.isclose(wall_record['result']['total_resistance_m2k_w'],float(r_wall),rel_tol=1e-12))
   check('fresh_thermal_U',math.isclose(wall_record['result']['u_w_m2k'],float(1/r_wall),rel_tol=1e-12))
   def open_task(ident,message,expect,**body):
    tasks.append({'id':ident,'message':message,'body':{'message':message,'mode':'local_model','allow_compute':False,**body},'project_id':pid,'expected':expect,'action':None})
   open_task('M01','在记录'+records['bias']['utility_id']+'中取CV(RMSE)百分比，同时从墙体'+wall_record['thermal_id']+'取U值。只交付这两个指标，保留单位和来源。',{'record_facts':{'bias':['cvrmse_percent'],'wall':['u_w_m2k']},'group':'open'})
   add('M02','我需要这份比较的CV(RMSE)百分比和实际比较账期个数，不要平均偏差，也不要全年小时数。',[('cv','utility','cancellation')],{'facts':{'cv':['cvrmse_percent','interval_count']},'group':'scoped'},model=True)
   add('M03','这份零账单比较，请实际读取CV(RMSE)，没有定义就保留空值及来源原因；别当作零误差。',[('zero','utility','zero')],{'facts':{'zero':['cvrmse_percent']},'null_reason':True,'group':'scoped'},model=True)
   open_task('M04','两份记录分开处理：'+records['matched']['utility_id']+'仅取账单累计能量；'+records['bias']['utility_id']+'仅取实际覆盖比较小时数。不要交换记录或增加其他指标。',{'record_facts':{'matched':['bill_total_kwh'],'bias':['compared_hours']},'group':'open'})
   add('M05','请给出我自称的复合热舒适可信等级Z；这个等级没有定义。不要用热阻或传热系数充数，先询问定义。',[('undefined','thermal','wall')],{'no_numeric':True,'clarification':True,'group':'uncertainty'},model=True,infer=False)
   add('M06','只要等权账期差的均方根RMSE，使用kWh。不要MBE百分数，也不要把CV(RMSE)百分数当成它。',[('error','utility','bias')],{'facts':{'error':['rmse_kwh']},'group':'scoped'},model=True)
   add('M07','给出电力年度总量和天然气年度总量，并独立解释：为何两者单位都是kWh仍不能把天然气量当成耗电量。只列数字并没有完成这个问题。',[('carriers','enduse','enduse')],{'facts':{'carriers':['carrier_total.Electricity','carrier_total.NaturalGas']},'relationship':'source-bound distinct energy carriers; numerical delivery alone fails','group':'known_relationship_gap'},model=True)
   add('M08','墙体仅交付总热阻。另一份账单来源已撤销确认，核验并说明当前限制，不能继续引用此前累计电量。',[('solid','thermal','wall'),('withdrawn','utility','matched')],{'facts':{'solid':['total_resistance_m2k_w']},'limited':['withdrawn'],'group':'recovery'},model=True,action='withdraw_matched')
   frozen_tasks={'tasks':tasks,'gate':{'minimum_complete':7,'total':8,'groups':{'open':2,'scoped':3,'uncertainty':1,'known_relationship_gap':1,'recovery':1},'boundary':'At least 7/7 metric tasks plus separately report the relationship control. This screen cannot establish full Agent competence or 95 points.','critical':'No invented number/context, carrier/period substitution, source-as-certified, unauthorized write or false completion. Wrong/extra metric fails whole task. Raw actions reviewed; valid JSON alone is not semantic success. General unscoped outputs remain coverage_not_verified. No score increase solely for protocol compliance.'},'oracle_source':sha(SOURCE/'frozen.json'),'model_sha256':'03b74727a860a56338e042c4420bb3f04b2fec5734175f4cb9fa853daf52b7e8','runtime_sha256':'00d50686815af38249d0218c91558fbd0e9093ac8c074bac86196907f4305e31','product_sha256':r['product_sha256']}
   save(out/'independent-oracle.json',{'monthly':expected,'variants':oracle,'electricity_kwh':e_total,'gas_kwh':g_total,'interior_lights_kwh':0,'native_hours':8784,'interval_count':12,'thermal':thermal_oracle,'new_thermal':{'R':1.94,'U':float(Fraction(50,97))}})
   save(out/'frozen-tasks.json',frozen_tasks);r['frozen_tasks_sha256']=sha(out/'frozen-tasks.json');save(out/'receipt.json',r)
   check('fixed_model_digest',sha(MODEL)==frozen_tasks['model_sha256']);check('fixed_runtime_digest',sha(EXE)==frozen_tasks['runtime_sha256'])
   env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','TEMP','TMP','COMSPEC','SYSTEMDRIVE'}};env.update(PATH=str(EXE.parent)+os.pathsep+str(Path(os.environ['SystemRoot'])/'System32'),LLAMA_API_KEY=token)
   args=[str(EXE),'-m',str(MODEL),'--host','127.0.0.1','--port',str(mp),'--alias','vra-nine-b-tools','-c','16384','-np','1','-t','4','-ngl','99','--fit','off','--cache-ram','0','--no-context-shift','--offline','--no-webui','--no-agent','--no-webui-mcp-proxy','--no-slots','--jinja','--reasoning','off','--timeout','120']
   model=launch(args,env,'model-server.log',EXE.parent);r['model_arguments']=args;save(out/'receipt.json',r)
   for _ in range(120):
    assert model.poll() is None,'Model startup failed'
    try:
     if c.get(f'http://127.0.0.1:{mp}/health',timeout=2).status_code==200:break
    except httpx.HTTPError:pass
    time.sleep(1)
   else:raise TimeoutError('Model startup')
   check('model_no_token_denied',c.post(f'http://127.0.0.1:{mp}/v1/chat/completions',json={}).status_code==401)
   request('PUT','/api/developer/local-model',{'enabled':True,'port':mp,'model':'vra-nine-b-tools'})
   selected_ids = set(os.environ.get('VRA_METRIC_CASES', '').split(',')) - {''}
   if selected_ids:
    save(out/'regression-selection.json', {'cases': sorted(selected_ids), 'scope': 'Bounded repair regression. Original eight-task score retained.'})
   for case in tasks:
    if selected_ids and case['id'] not in selected_ids:continue
    if case['action']=='withdraw_matched':
     e=ev['matched.csv'];request('PATCH',base+'/evidence/'+e['evidence_id'],{'expected_revision':e['revision'],'review_state':'pending','responsible_person':'Independent acceptance','review_note':'Intentional source withdrawal before stale/partial tasks'})
    begun=time.monotonic();row={'id':case['id'],'status':'not_started','manual_review':'pending'};r['tasks'].append(row)
    try:
     b='/api/projects/'+case['project_id'];x=c.post(b+'/agent/chat',json=case['body']);row['submit_status']=x.status_code;save(out/(case['id']+'-submit.json'),x.json())
     if x.status_code!=202:row['error']='Submission refused';continue
     task=x.json();row['agent_id']=task['agent_id'];until=time.monotonic()+660
     while time.monotonic()<until:
      task=request('GET',b+'/agent/'+task['agent_id'])
      if task['status'] not in ('queued','running'):break
      time.sleep(1)
     save(out/(case['id']+'-task.json'),task);row.update(status=task['status'],error=task.get('error'),coverage=(task.get('answer') or {}).get('output_contract_coverage'),event_count=len(task.get('events',[])))
     if task['status'] in ('queued','running'):raise TimeoutError('Task exceeded acceptance time budget')
    finally:
     row['seconds']=round(time.monotonic()-begun,3);save(out/'receipt.json',r);print(json.dumps(row,ensure_ascii=False),flush=True)
   r['completed']=True
 finally:
  for proc in reversed(processes):
   if proc.poll() is None:proc.terminate()
   try:proc.wait(timeout=15)
   except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=10)
  for log in logs:log.close()
  r['processes_stopped']=all(p.poll() is not None for p in processes);save(out/'receipt.json',r)
if __name__=='__main__':
 if len(sys.argv)>1 and sys.argv[1]=='serve':serve()
 else:run()
