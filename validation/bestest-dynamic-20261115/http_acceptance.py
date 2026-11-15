"""Real project workflow on frozen public reference inputs; no browser or model fitting."""
import argparse,hashlib,io,json,math,os,secrets,socket,subprocess,sys,tempfile,time
from pathlib import Path
import httpx
from pypdf import PdfReader
from native_probe import extract

BASE=Path(__file__).parent
ROOT=Path('D:/稀土agent-稀土制暖全流程/.codex_work/vra-resource-leveling-20261115')
def sha(data):return hashlib.sha256(data).hexdigest()
def run(out,preflight_only):
    out.mkdir(exist_ok=False)
    frozen=json.loads((BASE/'reference-frozen-v2.json').read_text());prep=json.loads((BASE/'input-preparation-v4.json').read_text())
    assert prep['reference_sha256']==sha((BASE/'reference-frozen-v2.json').read_bytes())
    weather=(BASE/'public-reference'/frozen['weather']['path']).read_bytes();assert sha(weather)==frozen['weather']['sha256']
    expected={r['case']:r for n in ['native-v4-first','native-v4-remaining'] for r in json.loads((BASE/n/'receipt.json').read_text())['cases']}
    runtime=Path(tempfile.mkdtemp(prefix='vra-bestest-http-'));checks=[];responses=[];observations=[];complete=False;error=None
    def save(name,obj):(out/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    def check(name,condition):
        checks.append({'name':name,'passed':bool(condition)})
        if not condition:raise AssertionError(name)
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    with (out/'server.log').open('w',encoding='utf-8') as log:
        env={**os.environ,'VRA_DATA_DIR':str(runtime/'server'),'PYTHONDONTWRITEBYTECODE':'1','ENERGYPLUS_EXE':'F:/EnergyPlusV9-0-1/energyplus.exe'}
        process=subprocess.Popen([sys.executable,'-B','-m','uvicorn','backend.api:app','--host','127.0.0.1','--port',str(port)],cwd=ROOT,env=env,stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            with httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=120,event_hooks={'response':[lambda r:responses.append({'method':r.request.method,'path':r.request.url.path,'status':r.status_code})]}) as c:
                for _ in range(100):
                    try:
                        if c.get('/api/health').status_code==200:break
                    except httpx.ConnectError:time.sleep(.1)
                else:raise RuntimeError('Isolated server unavailable')
                r=c.post('/api/auth/register',json={'username':'bestest_http_test','display_name':'Isolated public reference verification','password':secrets.token_urlsafe(32)});check('registration',r.status_code==200);c.headers['X-CSRF-Token']=r.json()['csrf_token']
                for item in prep['cases'][:1] if preflight_only else prep['cases']:
                    case=item['case'];model=Path(item['path']).read_bytes();assert sha(model)==item['derived_sha256']
                    project={'name':'Public BESTEST '+case+' — uncalibrated reference','building':{'use':'reference','location':'Denver reference weather; not a real building','region':'US-CO','area_m2':64 if case=='960' else 48}}
                    r=c.post('/api/projects',json=project);check(case+' project',r.status_code==201);base='/api/projects/'+r.json()['project_id'];pid=r.json()['project_id'];files={};evidences={}
                    for kind,data in [('idf',model),('epw',weather)]:
                        r=c.post(base+'/files',files={'file':('Case'+case+'.'+kind,data)});check(case+' upload '+kind,r.status_code==201);file=r.json();files[kind]=file
                        body={'type':kind,'name':'Frozen public reference '+kind,'source_file':file['file_id'],'source_locator':frozen['repository']+'@'+frozen['source_commit'],'authority':'Archived public validation reference','permission':'Public source accessed for local reference verification','acquisition_method':'Pinned public download; explicit IDF field mapping; original weather bytes','responsible_person':'Acceptance author','status':'ASSUMED' if kind=='idf' else 'IMPORTED'}
                        if kind=='idf':body['scheme_id']='baseline'
                        r=c.post(base+'/evidence',json=body);check(case+' evidence '+kind,r.status_code==201);e=r.json()
                        r=c.patch(base+'/evidence/'+e['evidence_id'],json={'expected_revision':e['revision'],'review_state':'confirmed','responsible_person':'Acceptance author','review_note':'Public reference applicability for this experiment only; no real-building attestation'});check(case+' review '+kind,r.status_code==200);evidences[kind]=r.json()
                    gate=c.get(base+'/gate').json();save(case+'-gate.json',gate)
                    if preflight_only:
                        check('baseline rejected 32-column EPW',not gate['can_simulate'] and any(b['field']=='epw' and '35' in b['message'] for b in gate['blockers']))
                        r=c.post('/api/runs',json={'project_id':pid,'scheme_id':'baseline','factor_profile_id':'none'});check('baseline run blocked',r.status_code==409);save('rejected-run.json',r.json());check('baseline no run created',c.get(base+'/runs').json()==[]);break
                    check(case+' gate conditional',gate['can_simulate'] and gate['weather_quality']['status']=='accepted_with_conditions')
                    q=gate['weather_quality'];check(case+' missing columns visible',q['record_field_count']==32 and all(q['fields'][k]['missing_count']==8760 and q['fields'][k]['min'] is None for k in ['albedo','liquid_precipitation_depth','liquid_precipitation_quantity']))
                    r=c.post('/api/runs',json={'project_id':pid,'scheme_id':'baseline','factor_profile_id':'none'});check(case+' queued',r.status_code==202);rid=r.json()['run_id'];route='/api/runs/'+rid;deadline=time.monotonic()+180
                    while time.monotonic()<deadline:
                        r=c.get(route);view=r.json()
                        if view['status'] not in ('queued','running'):break
                        time.sleep(.3)
                    save(case+'-run.json',view);check(case+' succeeded',view['status']=='succeeded');check(case+' weather same source',view['weather_quality']==q)
                    sql=runtime/'server/runs'/rid/'output/eplusout.sql';zones=next(x['zones'] for x in frozen['cases'] if x['case']==case);metrics,identity=extract(sql,zones)
                    for key,value in metrics.items():check(case+' repeat native '+key,math.isclose(value,expected[case]['metrics'][key],rel_tol=1e-11,abs_tol=1e-8))
                    hourly=view['metrics']['hourly_thermal'];check(case+' hourly ready',hourly['status']=='calculated_model_scenario' and hourly['summary']['hour_count']==8760)
                    b=hourly['summary']['building']
                    for mode in ('heating','cooling'):
                        check(case+' app annual '+mode,math.isclose(b[mode+'_delivered_sensible_kWh']/1000,metrics[mode+'_mwh'],abs_tol=1e-9))
                        check(case+' app coincident '+mode,math.isclose(b[mode+'_peak']['value_W']/1000,metrics['peak_'+mode+'_kw'],abs_tol=1e-9))
                    z=next(z for z in hourly['summary']['zones'] if z['zone_name']==('SUN ZONE' if case=='960' else zones[0]))
                    for key in ('min','max'):check(case+' app temperature '+key,math.isclose(z['temperature_'+key+'_C'],metrics['temperature_'+key+'_c'],abs_tol=1e-9))
                    comparison=[{**{k:m[k] for k in ['key','minimum','maximum']},'actual':metrics[m['key']],'within_range':m['minimum']<=metrics[m['key']]<=m['maximum']} for m in next(x['metrics'] for x in frozen['cases'] if x['case']==case)]
                    observations.append({'case':case,'run_id':rid,'sql_sha256':sha(sql.read_bytes()),'metrics':metrics,'comparisons':comparison,'native_identity':identity})
                    save('observations.json',observations)
                    check(case+' original weather retained',c.get(base+'/files/'+files['epw']['file_id']).content==weather)
                    check(case+' original model retained',c.get(base+'/files/'+files['idf']['file_id']).content==model)
                    if case in ('600','620','960','650FF'):
                        r=c.get(route+'/report.json');check(case+' JSON same source',r.status_code==200 and r.json()['run']['weather_quality']==q);save(case+'-report.json',r.json())
                        r=c.get(route+'/report.html');check(case+' HTML conditions',r.status_code==200 and '旧版32列' in r.text and q['source_sha256'] in r.text);(out/(case+'-report.html')).write_text(r.text,encoding='utf-8')
                        r=c.get(route+'/report.pdf');check(case+' PDF',r.status_code==200 and r.content.startswith(b'%PDF'));(out/(case+'-report.pdf')).write_bytes(r.content)
                        text='\n'.join(p.extract_text() or '' for p in PdfReader(io.BytesIO(r.content)).pages);check(case+' PDF missing context','旧版32列' in text and '未观测' in text);(out/(case+'-pdf-text.txt')).write_text(text,encoding='utf-8')
                    if case=='650FF':
                        csrf=c.headers.pop('X-CSRF-Token');check('CSRF rejected',c.post('/api/runs',json={'project_id':pid,'scheme_id':'baseline'}).status_code==403);c.headers['X-CSRF-Token']=csrf
                        with httpx.Client(base_url=str(c.base_url)) as anon:check('anonymous report denied',anon.get(route+'/report.json').status_code==401)
                        e=evidences['epw'];r=c.patch(base+'/evidence/'+e['evidence_id'],json={'expected_revision':e['revision'],'review_state':'rejected','responsible_person':'Acceptance author','review_note':'Deliberate source withdrawal after comparison; preserve original run'});check('weather withdrawal',r.status_code==200)
                        stale=c.get(route).json();save('withdrawn-run.json',stale);check('withdraw numbers',stale['status']=='stale' and stale['metrics'] is None and stale['weather_quality'] is None)
                        check('withdraw JSON numbers',c.get(route+'/report.json').json()['run']['metrics'] is None)
                        check('withdraw prevents run',c.post('/api/runs',json={'project_id':pid,'scheme_id':'baseline'}).status_code==409)
                    print(json.dumps({'case':case,'integration':'passed','outside_reference':sum(not x['within_range'] for x in comparison)}),flush=True)
                if not preflight_only:
                    by={r['case']:r['metrics'] for r in observations};paired=[]
                    for p in frozen['sensitivities']:
                        actual=by[p['changed']][p['key']]-by[p['baseline']][p['key']];paired.append({**p,'actual':actual,'within_range':p['minimum']<=actual<=p['maximum']})
                    save('paired.json',paired)
                complete=True
        except Exception as exc:error=type(exc).__name__+': '+str(exc);raise
        finally:
            process.terminate()
            try:process.wait(timeout=15)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
            save('summary.json',{'all_checks_passed':complete and all(x['passed'] for x in checks),'preflight_only':preflight_only,'checks':checks,'responses':responses,'runtime_path':str(runtime),'server_stopped':process.poll() is not None,'error':error,'reference_sha256':prep['reference_sha256'],'script_sha256':sha(Path(__file__).read_bytes()),'scope':'Integration checks are not physical-reference passes; raw 67 scalar/24 paired comparative outcomes kept separately. No browser or field acceptance.'})
    print(json.dumps({'complete':complete,'checks':len(checks),'cases':len(observations)}))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--preflight-only',action='store_true');a=p.parse_args();run(BASE/a.output,a.preflight_only)
