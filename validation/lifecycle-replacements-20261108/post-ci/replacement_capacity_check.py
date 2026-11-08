from pathlib import Path
import copy,json,os,secrets,socket,subprocess,sys,tempfile,time
import httpx
root=Path('C:/Users/18483/AppData/Local/Temp/vra-lifecycle-ledger-release-20261108')
sys.path[:0]=[str(root),str(root/'tests')]
from test_lifecycle_replacements import replacement_inventory
out=Path(tempfile.mkdtemp(prefix='vra-replacement-capacity-'));runtime=out/'runtime'
with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
with (out/'server.log').open('w') as log:
 p=subprocess.Popen([sys.executable,'-B','-m','uvicorn','backend.api:app','--host','127.0.0.1','--port',str(port)],cwd=root,env={**os.environ,'VRA_DATA_DIR':str(runtime),'PYTHONDONTWRITEBYTECODE':'1'},stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 try:
  with httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=30) as c:
   for _ in range(100):
    try:
     if c.get('/api/health').status_code==200:break
    except httpx.ConnectError:time.sleep(.1)
   login=c.post('/api/auth/register',json={'username':'capacity_test','display_name':'Bounded capacity test','password':secrets.token_urlsafe(32)});assert login.status_code==200
   c.headers['X-CSRF-Token']=login.json()['csrf_token']
   proj=c.post('/api/projects',json={'name':'Synthetic capacity case','building':{'use':'office','location':'Golden','region':'US-CO','area_m2':927.2}});assert proj.status_code==201
   base='/api/projects/'+proj.json()['project_id'];body=replacement_inventory();body['study_years']=200
   template=body['replacements'][0];template.update(condition='existing',remaining_life_years=.1,service_life_years=.2)
   body['replacements']=[dict(copy.deepcopy(template),component_id='component-'+str(i)) for i in range(5)]
   started=time.perf_counter();saved=c.post(base+'/lifecycle',json=body);save_seconds=time.perf_counter()-started;assert saved.status_code==201,saved.text
   record=saved.json();events=sum(len(x['events']) for x in record['result']['replacement']['components']);assert events==5000
   # Five components, 1000 events each; independent decimal expectation.
   assert abs(record['result']['replacement']['total_kgco2e']-1148040)<1e-7
   assert abs(record['result']['boundary_total_kgco2e']-1249130)<1e-7
   route=base+'/lifecycle/'+record['lifecycle_id'];started=time.perf_counter();r=c.get(route);read_seconds=time.perf_counter()-started;assert r.status_code==200
   started=time.perf_counter();report=c.get(route+'/report.html');report_seconds=time.perf_counter()-started;assert report.status_code==200
   body['replacements'].append(dict(copy.deepcopy(template),component_id='sixth-component'))
   rejected=c.post(base+'/lifecycle',json=body);assert rejected.status_code==422,rejected.text
   assert len(c.get(base+'/lifecycle').json())==1
   receipt={'events':events,'replacement_kgco2e':record['result']['replacement']['total_kgco2e'],'boundary_total_kgco2e':record['result']['boundary_total_kgco2e'],'save_seconds':save_seconds,'read_seconds':read_seconds,'report_seconds':report_seconds,'record_response_bytes':len(saved.content),'report_bytes':len(report.content),'sixth_component_status':rejected.status_code,'records_after_rejection':1,'scope':'one bounded local sequential functional-capacity run; not concurrency, production throughput or browser performance','product_commit':'c3dedd985969c54061b47e904458c573f82df641'}
 finally:
  p.terminate();p.wait(timeout=15)
receipt['server_stopped']=p.poll() is not None
(out/'summary.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
Path('D:/稀土agent-稀土制暖全流程/outputs/vra-soak-20261108/replacement-capacity-receipt.json').write_text(json.dumps({'output':str(out),**receipt},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(receipt,ensure_ascii=False))
