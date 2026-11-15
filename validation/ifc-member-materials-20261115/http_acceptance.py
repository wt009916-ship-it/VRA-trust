"""Actual HTTP through local API and isolated native parser; no browser."""
import hashlib,json,os,secrets,socket,subprocess,sys,time
from pathlib import Path
import httpx

repo=Path('C:/Users/18483/AppData/Local/Temp/vra-timestep-reliability-20261108');sys.path[:0]=[str(repo),str(repo/'tests')]
from test_ifc_member_quantities import member
from test_material_scenarios import payload
out=Path(__file__).parent/'actual-http';out.mkdir(exist_ok=False)
runtime=Path('C:/Users/18483/AppData/Local/Temp')/('vra-member-http-'+secrets.token_hex(6));runtime.mkdir()
_,_,element,_,input_path=member(runtime,'IfcColumn','MILLI')
source=input_path.read_bytes();(out/'synthetic-column.ifc').write_bytes(source)
with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
env={**os.environ,'VRA_DATA_DIR':str(runtime/'data'),'PYTHONDONTWRITEBYTECODE':'1','PYTHONPATH':str(repo)}
command=[sys.executable,'-B','-X','utf8','-c','from backend.api import create_app; import uvicorn; uvicorn.run(create_app(start_worker=False),host="127.0.0.1",port='+str(port)+',access_log=False)']
log=(out/'server.log').open('wb');proc=subprocess.Popen(command,cwd=repo,env=env,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
checks=[]
def check(name,condition,value):
 checks.append({'name':name,'passed':bool(condition),'actual':value});assert condition,name
def save(name,value):(out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
try:
 with httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=120) as c:
  for _ in range(80):
   try:
    if c.get('/api/health').status_code==200:break
   except httpx.TransportError:pass
   time.sleep(.25)
  login=c.post('/api/auth/register',json={'username':'member_acceptance','display_name':'Isolated member acceptance','password':secrets.token_urlsafe(32)})
  assert login.status_code==200;c.headers['X-CSRF-Token']=login.json()['csrf_token'];del login
  p=c.post('/api/projects',json={'name':'Synthetic column material test','building':{'use':'test','location':'Reference','region':'US-CO','area_m2':100.}}).json()
  base='/api/projects/'+p['project_id'];f=c.post(base+'/files',files={'file':('column.ifc',source)}).json()
  start=time.monotonic();response=c.post(base+'/cad-inspections',json={'file_id':f['file_id']});check('native_inspection',response.status_code==201,response.status_code)
  cad=response.json();save('cad-response.json',cad)
  response=c.post(base+'/ifc-layer-takeoffs',json={'cad_id':cad['cad_id'],'product_id':element.id()});check('member_takeoff_created',response.status_code==201,response.status_code)
  r=response.json();save('takeoff.json',r);check('net_volume_22',r['status']=='measured' and abs(r['result']['total_layer_envelope_m3']-22)<1e-8,{'volume':r['result']['total_layer_envelope_m3'],'elapsed_s':time.monotonic()-start})
  ev=c.post(base+'/evidence',json={'type':'manual_input','name':'Declared synthetic material assumptions','source_locator':'QA arithmetic','authority':'QA','permission':'Test only','acquisition_method':'Manual','responsible_person':'QA','status':'ASSUMED'}).json()
  b=payload(r);b['functional_scope']='Selected synthetic column, same envelope, explicit assumptions'
  for a in b['alternatives']:a['layers'][0]['evidence_ids']=[ev['evidence_id']]
  save('scenario-input.json',b);response=c.post(base+'/material-scenarios',json=b);check('scenario_created',response.status_code==201,response.status_code)
  scenario=response.json();save('scenario.json',scenario);first=scenario['result']['alternatives'][0]
  check('independent_cost_1210',first['cost']['material_total']=='1210.00',first['cost']['material_total'])
  check('independent_carbon_24200',abs(first['carbon']['boundary_total_kgco2e']-24200)<1e-6,first['carbon']['boundary_total_kgco2e'])
  check('no_issued_credit',scenario['result']['issued_credits_t'] is None,None)
  report=c.get(base+'/material-scenarios/'+scenario['scenario_id']+'/report.html');(out/'scenario-report.html').write_bytes(report.content);check('report',report.status_code==200 and '1210.00' in report.text,report.status_code)
  response=c.post(base+'/ifc-layer-takeoffs',json={'cad_id':cad['cad_id'],'product_id':element.id()},headers={'X-CSRF-Token':''});check('csrf_refused',response.status_code==403,response.status_code)
  c.patch(base+'/evidence/'+ev['evidence_id'],json={'expected_revision':1,'review_state':'rejected','responsible_person':'QA','review_note':'Withdraw synthetic assumptions'})
  current=c.get(base+'/material-scenarios/'+scenario['scenario_id']).json();save('withdrawn.json',current);check('withdrawal_hides_old_amounts',current['status']=='stale' and current['result'] is None,current['status'])
  check('source_preserved',hashlib.sha256(input_path.read_bytes()).digest()==hashlib.sha256(source).digest(),hashlib.sha256(source).hexdigest())
  c.cookies.clear();response=c.get(base+'/ifc-layer-takeoffs/'+r['takeoff_id']+'/report.html');check('anonymous_refused',response.status_code==401,response.status_code)
finally:
 proc.terminate();proc.wait(timeout=15);log.close()
 sources={}
 for path in sorted((repo/'backend').glob('*.py')):sources[path.relative_to(repo).as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
 save('receipt.json',{'checks':checks,'passed':sum(c['passed'] for c in checks),'complete':len(checks)==12 and all(c['passed'] for c in checks),
  'transport':'actual loopback HTTP with real isolated native IFC worker','source_sha256':sources,'browser':'deferred by user','real_building':False})
 print(json.dumps({'checks':len(checks),'passed':sum(c['passed'] for c in checks)}))
