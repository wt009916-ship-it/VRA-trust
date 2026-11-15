"""Actual loopback HTTP and native annual utility comparison; synthetic, never calibrated."""
import csv,hashlib,io,json,math,os,secrets,socket,subprocess,sys,tempfile,time
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend import core


def execute(inputs,out):
    out.mkdir(parents=True,exist_ok=False);f=core.read_json(inputs/'frozen.json');checks=[];events=[];completed=False;runtime=Path(tempfile.mkdtemp(prefix='vra-utility-http-'))
    for name,digest in f['files'].items():assert core.sha(inputs/name)==digest
    def save(name,obj):core.write_json(out/name,obj)
    def check(name,yes):checks.append({'name':name,'passed':bool(yes)});save('checks.json',checks);assert yes,name
    save('inputs.json',{'frozen_sha256':core.sha(inputs/'frozen.json'),'script_sha256':core.sha(Path(__file__)),'calculator_sha256':core.sha(ROOT/'backend/utility_comparison.py'),'records_sha256':core.sha(ROOT/'backend/utility_records.py'),'engine_sha256':core.sha(core.engine_path()),'scope':'Synthetic independent interval schedules. No real-building, calibration or browser claim.'})
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    def hook(r):events.append({'method':r.request.method,'path':r.request.url.path,'status':r.status_code,'elapsed_seconds':None})
    with (out/'server.log').open('wb') as log:
        proc=subprocess.Popen([sys.executable,'-B','-m','uvicorn','backend.api:app','--host','127.0.0.1','--port',str(port)],cwd=ROOT,env={**os.environ,'VRA_DATA_DIR':str(runtime/'server'),'PYTHONDONTWRITEBYTECODE':'1'},stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            with httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=120,trust_env=False,event_hooks={'response':[hook]}) as c:
                for _ in range(100):
                    try:
                        if c.get('/api/health').status_code==200:break
                    except httpx.ConnectError:time.sleep(.1)
                else:raise RuntimeError('Readiness failed')
                r=c.post('/api/auth/register',json={'username':'utility_http_acceptance','display_name':'隔离账单核验','password':secrets.token_urlsafe(32)});check('isolated_registration',r.status_code==200);c.headers['X-CSRF-Token']=r.json()['csrf_token']
                for case in f['cases']:
                    cid=case['id'];work=out/cid;work.mkdir();source=inputs/cid
                    r=c.post('/api/projects',json={'name':'Synthetic calendar '+cid,'building':{'use':'reference','location':'Synthetic constant weather, no surveyed site','region':'TEST','area_m2':25.0}});check(cid+'_project',r.status_code==201);pid=r.json()['project_id'];base='/api/projects/'+pid;evs={};files={}
                    def upload_review(kind,name,data):
                        r=c.post(base+'/files',files={'file':(name,data)});check(cid+'_'+name+'_upload',r.status_code==201);file=r.json();files[name]=(file,data)
                        body={'type':kind,'name':name,'source_file':file['file_id'],'source_locator':'Frozen independent synthetic reference, original bytes retained','authority':'Reference author','permission':'Local public-reference verification','acquisition_method':'Declared schedules, not measured building','responsible_person':'Acceptance author','status':'ASSUMED'}
                        if kind=='idf':body['scheme_id']='baseline'
                        r=c.post(base+'/evidence',json=body);check(cid+'_'+name+'_evidence',r.status_code==201);ev=r.json()
                        r=c.patch(base+'/evidence/'+ev['evidence_id'],json={'expected_revision':ev['revision'],'review_state':'confirmed','responsible_person':'Acceptance author','review_note':'Synthetic source reviewed for arithmetic only, not real-building data'});check(cid+'_'+name+'_review',r.status_code==200);evs[name]=r.json();return r.json()
                    upload_review('idf','model.idf',(source/'model.idf').read_bytes());upload_review('epw','weather.epw',(source/'weather.epw').read_bytes())
                    for path in sorted(source.glob('*.csv')):upload_review('bill',path.name,path.read_bytes())
                    r=c.get(base+'/gate');save(cid+'/gate.json',r.json());check(cid+'_input_gate',r.status_code==200 and r.json()['can_simulate'])
                    r=c.post('/api/runs',json={'project_id':pid,'scheme_id':'baseline','factor_profile_id':'none'});check(cid+'_native_accepted',r.status_code==202);rid=r.json()['run_id'];deadline=time.monotonic()+600
                    while time.monotonic()<deadline:
                        r=c.get('/api/runs/'+rid);run=r.json()
                        if run['status'] not in ('queued','running'):break
                        time.sleep(1)
                    save(cid+'/run.json',run);check(cid+'_actual_native_succeeded',run['status']=='succeeded');print(cid,'native succeeded',flush=True)
                    rd=runtime/'server/runs'/rid;save(cid+'/native-artifacts.json',{'run_id':rid,'path':str(rd),'files':{str(p.relative_to(rd)).replace('\\','/'):core.sha(p) for p in rd.rglob('*') if p.is_file()}})
                    catalog_route=base+'/utility-meters/'+rid;r=c.get(catalog_route);save(cid+'/catalog.json',r.json())
                    if case['dst_expected']:
                        check(cid+'_dst_rejected',r.status_code==409 and 'daylight saving' in r.text);continue
                    check(cid+'_meter_catalog',r.status_code==200);catalog=r.json();check(cid+'_actual_calendar',catalog['year']==case['year'] and catalog['hours']==(8784 if cid=='2020' else 8760) and catalog['weather_calendar_matches_native']);check(cid+'_native_meter_available',any(m['name']=='Electricity:Facility' for m in catalog['meters']))
                    comparisons={};route=base+'/utility-comparisons'
                    def body(variant,**extra):return {'name':'Synthetic '+cid+' '+variant,'purpose':'Compare declared independent interval reference; never real-building calibration','run_id':rid,'bill_evidence_id':evs[variant+'.csv']['evidence_id'],'meter':'Electricity:Facility','bill_nature':'synthetic','alignment':'exact_calendar','period_kind':'calendar_month','clock_source':'Frozen declared local standard time; no DST','boundary_note':'All declared electric equipment and no other consumption; synthetic original bill','max_abs_mbe_percent':5.0,'max_cvrmse_percent':5.0,'threshold_source':'Explicit synthetic test goal, not a compliance certification',**extra}
                    for variant in ('matched','bias','cancellation','zero'):
                        before=time.monotonic();r=c.post(route,json=body(variant));elapsed=time.monotonic()-before;save(cid+'/'+variant+'-first.json',r.json());check(cid+'_'+variant+'_created',r.status_code==201);record=r.json();comparisons[variant]=record;stats=record['result']['statistics'];oracle=core.read_json(source/(variant+'-expected.json'))
                        for actual,expected in [('mbe_percent','mbe_pct'),('rmse_kwh','rmse_kwh'),('cvrmse_percent','cvrmse_pct')]:
                            want=oracle[expected];got=stats[actual];check(cid+'_'+variant+'_'+actual,got is None if want is None else got is not None and math.isclose(got,float(want),abs_tol=1e-8,rel_tol=1e-10))
                        check(cid+'_'+variant+'_reference_not_calibrated',record['status']=='compared_reference' and record['result']['calibration_status']=='not_certified_or_automatically_calibrated');check(cid+'_'+variant+'_coverage',record['result']['coverage']['complete_year']);save(cid+'/'+variant+'-timing.json',{'elapsed_seconds':elapsed,'purpose':'single local request observation, not a throughput/load benchmark'})
                        uri=route+'/'+record['utility_id'];r=c.get(uri+'/comparison.csv');check(cid+'_'+variant+'_csv',r.status_code==200);(work/(variant+'-export.csv')).write_bytes(r.content);rows=list(csv.DictReader(io.StringIO(r.text)));check(cid+'_'+variant+'_csv_rows',len(rows)==12)
                        for i,(actual,expected) in enumerate(zip(rows,record['result']['rows'])):check(cid+'_'+variant+'_csv_row_'+str(i),float(actual['native_kwh'])==expected['native_kwh'] and actual['start_inclusive']==expected['original']['start'])
                        r=c.get(uri+'/report.html');check(cid+'_'+variant+'_html',r.status_code==200 and record['source_run']['sql_sha256'] in r.text and '不是实楼校准' in r.text);(work/(variant+'-report.html')).write_bytes(r.content)
                    check(cid+'_zero_not_pass',comparisons['zero']['result']['within_declared_tolerances'] is None);check(cid+'_cancellation_not_hidden',abs(comparisons['cancellation']['result']['statistics']['mbe_percent'])<1e-8 and comparisons['cancellation']['result']['statistics']['cvrmse_percent']>5)
                    for variant in ('gap','duplicate','power_unit','wrong_carrier','wrong_year'):
                        r=c.post(route,json=body(variant));save(cid+'/'+variant+'-rejection.json',r.json());check(cid+'_'+variant+'_rejected',r.status_code==409)
                    r=c.post(route,json=body('matched',bill_nature='measured'));check(cid+'_cannot_upgrade_assumed_to_measured',r.status_code==409)
                    r=c.get(route);check(cid+'_history_names_only',r.status_code==200 and len(r.json()['records'])==4 and all(set(x)=={'utility_id','name'} for x in r.json()['records']))
                    if cid=='2019':
                        r=c.post(route,json=body('wrong_year',alignment='calendar_pattern'));save(cid+'/reference-mapping.json',r.json());check('explicit_reference_mapping',r.status_code==201 and 'month_day_mapping_not_same_year' in r.json()['result']['context_reasons']);check('reference_mapping_keeps_original_year',r.json()['result']['rows'][0]['original']['start'].startswith('2021') and r.json()['result']['rows'][0]['mapped_start'].startswith('2019'))
                        old=evs['matched.csv'];upload_review('bill','leap.csv',(inputs/'2020/matched.csv').read_bytes());r=c.post(route,json=body('matched',bill_evidence_id=evs['leap.csv']['evidence_id'],alignment='calendar_pattern'));check('leap_mapping_rejected',r.status_code==409 and 'leap' in r.text)
                        token=c.headers.pop('X-CSRF-Token');r=c.post(route,json=body('matched'));c.headers['X-CSRF-Token']=token;check('missing_csrf_denied',r.status_code==403)
                        uri=route+'/'+comparisons['matched']['utility_id'];urls=[route,uri,uri+'/comparison.csv',uri+'/report.html',catalog_route]
                        with httpx.Client(base_url=c.base_url,timeout=30,trust_env=False,event_hooks={'response':[hook]}) as stranger:
                            for url in urls:check('anonymous_'+url,stranger.get(url).status_code==401)
                            r=stranger.post('/api/auth/register',json={'username':'utility_http_other','display_name':'隔离其他账号','password':secrets.token_urlsafe(32)});check('foreign_account_created',r.status_code==200);stranger.headers['X-CSRF-Token']=r.json()['csrf_token']
                            for url in urls:check('foreign_'+url,stranger.get(url).status_code==404)
                            check('foreign_write_denied',stranger.post(route,json=body('matched')).status_code==404)
                        r=c.patch(base+'/evidence/'+old['evidence_id'],json={'expected_revision':old['revision'],'review_state':'pending','responsible_person':'Acceptance author','review_note':'Withdraw bill source confirmation'});check('bill_review_withdrawn',r.status_code==200);r=c.get(uri);save(cid+'/withdrawn-bill.json',r.json());check('bill_withdrawal_clears_numbers',r.json()['status']=='stale' and r.json()['result'] is None);check('bill_withdrawal_blocks_csv',c.get(uri+'/comparison.csv').status_code==409);check('bill_withdrawal_clears_html','全部比较数值已撤下' in c.get(uri+'/report.html').text)
                    for name,(file,data) in files.items():check(cid+'_'+name+'_original_preserved',hashlib.sha256(c.get(base+'/files/'+file['file_id']).content).hexdigest()==hashlib.sha256(data).hexdigest())
                    ev=evs['model.idf'];r=c.patch(base+'/evidence/'+ev['evidence_id'],json={'expected_revision':ev['revision'],'review_state':'rejected','responsible_person':'Acceptance author','review_note':'Withdraw native model applicability; no new result allowed'});check(cid+'_model_withdrawn',r.status_code==200)
                    uri=route+'/'+comparisons['bias']['utility_id'];r=c.get(uri);save(cid+'/withdrawn-model.json',r.json());check(cid+'_source_withdrawal_clears_numbers',r.json()['status']=='stale' and r.json()['result'] is None);check(cid+'_source_withdrawal_blocks_catalog',c.get(catalog_route).status_code==409);check(cid+'_source_withdrawal_blocks_create',c.post(route,json=body('bias')).status_code==409);print(cid,'comparison acceptance passed',flush=True)
                completed=True
        finally:
            proc.terminate()
            try:proc.wait(timeout=15)
            except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=5)
            save('summary.json',{'checks':checks,'all_passed':completed and all(c['passed'] for c in checks),'http_responses':events,'server_stopped':proc.poll() is not None,'runtime_path':str(runtime),'scope':'Actual authenticated HTTP plus three native annual runs. Checks are assertions, not independent buildings. No browser or field calibration.'});print(json.dumps({'checks':len(checks),'all_passed':completed and all(c['passed'] for c in checks),'responses':len(events),'server_stopped':proc.poll() is not None}),flush=True)


if __name__=='__main__':execute(Path(sys.argv[1]).resolve(),Path(sys.argv[2]).resolve())
