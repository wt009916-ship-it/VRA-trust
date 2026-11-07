import hashlib,json,os,secrets,socket,subprocess,sys,tempfile,time,uuid
from decimal import Decimal
from pathlib import Path
import httpx
out=Path(__file__).resolve().parent
candidate=Path(json.loads((out/'candidate.json').read_text())['candidate'])
sys.path.insert(0,str(candidate))
from backend.private_storage import private_mkdir
runtime=private_mkdir(Path(tempfile.gettempdir())/('vra-five-stage-browser-'+uuid.uuid4().hex))
port=18775
with socket.socket() as s:s.bind(('127.0.0.1',port))
env={**os.environ,'VRA_DATA_DIR':str(runtime/'api'),'ENERGYPLUS_EXE':'F:/EnergyPlusV9-0-1/energyplus.exe','PYTHONUTF8':'1'}
log=(out/'browser-api.log').open('wb')
api=subprocess.Popen([sys.executable,'-B','-m','uvicorn','backend.api:app','--host','127.0.0.1','--port',str(port)],cwd=candidate,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
state_path=runtime/'browser-state.json';receipt={'api_pid':api.pid,'port':port,'candidate':str(candidate),'isolated_runtime':str(runtime)}
try:
 with httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=120,trust_env=False) as client:
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
  pid=receipt['project_id']
  source=Path('D:/稀土agent-稀土制暖全流程/outputs/vra-m2-intake-20261108/Duplex_A_20110907.ifc')
  response=client.post(f'/api/projects/{pid}/files',files={'file':(source.name,source.read_bytes(),'application/octet-stream')});assert response.status_code==201
  fid=response.json()['file_id']
  frozen=json.loads((out/'public-frozen.json').read_text(encoding='utf-8'))
  assert hashlib.sha256(source.read_bytes()).hexdigest()==frozen['source_sha256']
  assert client.get(f'/api/projects/{pid}/files/{fid}').content==source.read_bytes()
  response=client.post(f'/api/projects/{pid}/cad-inspections',json={'file_id':fid});assert response.status_code==201
  cad=response.json()
  response=client.post(f'/api/projects/{pid}/ifc-layer-takeoffs',json={'cad_id':cad['cad_id'],'product_id':5903});assert response.status_code==201
  takeoff=response.json();assert takeoff['status']=='measured'
  body=json.loads((out/'public-frozen.json').read_text(encoding='utf-8'))['input'];body['takeoff_id']=takeoff['takeoff_id']
  response=client.post(f'/api/projects/{pid}/material-scenarios',json=body);assert response.status_code==201,response.text[:500]
  result=response.json();assert result['status']=='calculated'
  assert [a['cost']['material_total'] for a in result['result']['alternatives']]==['26.82','21.44']
  (out/'public-scenario.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
  receipt['scenario_id']=result['scenario_id']
  for alt,want in zip(result['result']['alternatives'],frozen['expected']):
   assert alt['cost']['material_total']==want['material_cost']
   for stage,value in want['stages'].items():assert abs(Decimal(str(alt['carbon']['stages'][stage]['kgco2e']))-Decimal(value))<Decimal('1e-8')
   assert abs(Decimal(str(alt['carbon']['boundary_total_kgco2e']))-Decimal(want['total_kgco2e']))<Decimal('1e-8')
  receipt['api_independent_crosscheck']=True
  (out/'public-report.html').write_text(client.get(f"/api/projects/{pid}/material-scenarios/{result['scenario_id']}/report.html").text,encoding='utf-8')
  ev=client.post(f'/api/projects/{pid}/evidence',json={'type':'assumption','name':'Synthetic activity and route reference','source_locator':'Frozen reference rows, five-stage-v1/public-frozen.json','authority':'QA author','permission':'test only','acquisition_method':'synthetic sensitivity case','responsible_person':'auditor','status':'ASSUMED'}).json()
  receipt['evidence_id']=ev['evidence_id']
  receipt['takeoff_id']=takeoff['takeoff_id']


  state={'cookies':[{'name':c.name,'value':c.value,'domain':'127.0.0.1','path':'/','expires':-1,'httpOnly':True,'secure':False,'sameSite':'Strict'} for c in client.cookies.jar],'origins':[]}
  state_path.write_text(json.dumps(state),encoding='utf-8')
  receipt['browser_state_path']=str(state_path)
 (out/'browser-ready.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
 print(json.dumps({'ready':True,'pid':api.pid,'port':port}),flush=True)
 while True:
  command=input().strip()
  if command=='stop':break
  assert command in {'verify','reject_source'}
  with httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=120,trust_env=False) as check:
   for c in state['cookies']:check.cookies.set(c['name'],c['value'])
   auth=check.get('/api/auth/me');assert auth.status_code==200
   check.headers['X-CSRF-Token']=auth.json()['csrf_token']
   records=check.get(f'/api/projects/{pid}/material-scenarios').json()
   candidates=[r for r in records if r['scenario_id']!=receipt['scenario_id']]
   assert candidates,'Browser must submit a separate real scenario'
   ident=candidates[0]['scenario_id'];url=f'/api/projects/{pid}/material-scenarios/{ident}'
   if command=='verify':
    actual=check.get(url).json();assert actual['status']=='calculated'
    for alt,want in zip(actual['result']['alternatives'],frozen['expected']):
     assert alt['cost']['material_total']==want['material_cost']
     for stage,value in want['stages'].items():assert abs(Decimal(str(alt['carbon']['stages'][stage]['kgco2e']))-Decimal(value))<Decimal('1e-8')
    assert ev['evidence_id'] in [e['evidence_id'] for e in actual['source_snapshot']]
    (out/'browser-scenario.json').write_text(json.dumps(actual,ensure_ascii=False,indent=2),encoding='utf-8')
    receipt['browser_scenario_id']=ident;receipt['browser_values_and_evidence_passed']=True
    print(json.dumps({'browser_verified':True,'scenario_id':ident}),flush=True)
   else:
    review=check.patch(f"/api/projects/{pid}/evidence/{ev['evidence_id']}",json={'expected_revision':ev['revision'],'review_state':'rejected','responsible_person':'auditor','review_note':'Independent reference source withdrawn'})
    assert review.status_code==200,review.text
    actual=check.get(url).json();assert actual['status']=='stale' and actual['result'] is None
    receipt['source_withdrawal_passed']=True
    print(json.dumps({'source_withdrawal_passed':True}),flush=True)
  (out/'browser-ready.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')

finally:
 if api.poll() is None:api.terminate()
 api.wait(timeout=30);log.close()
 if state_path.exists():state_path.unlink()
 receipt.update(stopped=True,private_browser_state_deleted=True)
 (out/'browser-runtime-receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
 print('Private API stopped; private browser state deleted',flush=True)
