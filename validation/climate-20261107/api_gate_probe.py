"""Preserve next-batch API counterexamples; no simulation is submitted."""
import hashlib,json,os,secrets,sys,tempfile,uuid
from pathlib import Path
repo=Path.cwd();out=Path(__file__).resolve().parent
frozen=Path(json.loads((repo/'validation/ifc-topology-20261107/release-final/windows-source.json').read_text())['root'])
sys.path.insert(0,str(frozen))
from backend.private_storage import private_mkdir
root=private_mkdir(Path(tempfile.gettempdir())/('vra-climate-gate-'+uuid.uuid4().hex))
os.environ['VRA_DATA_DIR']=str(root/'bootstrap')
from backend.api import create_app
from fastapi.testclient import TestClient
probe=json.loads((out/'preflight-probe.json').read_text());cases=[]
model=frozen/'fixtures/demo/reference_5zone/baseline.idf'
with TestClient(create_app(root/'api',start_worker=False)) as client:
 r=client.post('/api/auth/register',json={'username':'climate_gate_test','display_name':'Isolated weather gate test','password':secrets.token_urlsafe(32)})
 assert r.status_code==200;client.headers['X-CSRF-Token']=r.json()['csrf_token']
 for case in probe['cases']:
  p=client.post('/api/projects',json={'name':'Weather counterexample '+case['case'],'data_nature':'engineering_reference',
    'building':{'use':'reference test','location':'Synthetic mutation, not a real building','region':'US-CO','area_m2':927.2}})
  assert p.status_code==201,p.text
  pid=p.json()['project_id'];base='/api/projects/'+pid
  for kind,path in [('idf',model),('epw',Path(case['path']))]:
   raw=path.read_bytes();file=client.post(base+'/files',files={'file':(path.name,raw)})
   assert file.status_code==201,file.text
   body={'type':kind,'name':kind+' synthetic preflight test','source_file':file.json()['file_id'],
         'source_locator':'Public reference copy; adversarial variation '+case['case'],'authority':'Independent development test',
         'permission':'Authorized public reference/synthetic local testing','acquisition_method':'Byte-preserving original; variation in separate copy',
         'responsible_person':'Automated isolated test','status':'IMPORTED'}
   if kind=='idf':body['scheme_id']='baseline'
   ev=client.post(base+'/evidence',json=body);assert ev.status_code==201,ev.text
   reviewed=client.patch(base+'/evidence/'+ev.json()['evidence_id'],json={'expected_revision':1,'review_state':'confirmed',
    'responsible_person':'Automated isolated test','review_note':'Intentional malformed input acceptance test; not field certification'})
   assert reviewed.status_code==200,reviewed.text
   _,stored=client.app.state.domain.file_record(pid,file.json()['file_id'])
   assert hashlib.sha256(stored.read_bytes()).hexdigest()==hashlib.sha256(raw).hexdigest()
  r=client.get(base+'/gate');assert r.status_code==200,r.text
  cases.append({'case':case['case'],'gate':r.json(),'weather_sha256':case['sha256']})
 with client.app.state.domain.store.connect() as con:assert con.execute('SELECT COUNT(*) FROM jobs').fetchone()[0]==0
record={'application_commit':probe['application_commit'],'frozen_source':str(frozen),'private_root':str(root),
        'cases':cases,'engine_calls':0,'scope':'Authenticated API upload, evidence review and gate only. No simulation or result quality claim.'}
with (out/'api-gate-probe.json').open('x',encoding='utf-8') as stream:json.dump(record,stream,indent=2)
print(json.dumps({'cases':[{'case':r['case'],'can_simulate':r['gate']['can_simulate'],'blockers':len(r['gate']['blockers'])} for r in cases],'engine_calls':0}))
