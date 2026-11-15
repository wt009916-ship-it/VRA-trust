"""Frozen synthetic annual HVAC acceptance through real local HTTP and native engine."""
import argparse,gzip,hashlib,json,math,os,secrets,socket,sqlite3,subprocess,sys,tempfile,time
from fractions import Fraction as F
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts'))
import verify_hvac_end_use as reference
from backend import core


def freeze(path):
    path.mkdir(parents=True,exist_ok=False)
    raw=(ROOT/'fixtures/demo/reference_5zone/weather.epw').read_text(encoding='utf8');lines=raw.splitlines();source=json.loads((ROOT/'fixtures/test/native_zone_sizing_projection.json').read_text())['model_idf'];cases=[]
    for s in reference.specifications():
        if s['id'] not in ('C02','H01','P02','M01','Z01'):continue
        work=path/s['id'];work.mkdir();data=reference.rows(reference.model(s,source));data=[r for r in data if r[0].casefold()!='sizingperiod:designday']
        for r in data:
            if r[0].casefold()=='simulationcontrol':r[1:]=['No','No','No','No','Yes']
        data.append(['RunPeriod','Controlled annual reference',1,1,'',12,31,'','Sunday','No','No','No','Yes','Yes'])
        model=reference.emit(data);(work/'model.idf').write_text(model,encoding='ascii')
        out=lines[:8];out[0]='LOCATION,Synthetic controlled HVAC reference,NA,NA,Synthetic,000000,0,0,0,0'
        t=s['outside'];dew=min(-12,t-5)
        saturation=lambda temp:math.exp(17.625*temp/(243.04+temp))
        rh=100*saturation(dew)/saturation(t)
        for line in lines[8:]:
            r=line.split(',');r[0]='2001';r[6]=str(t);r[7]=str(dew);r[8]=str(round(rh,2));r[9]='101325';r[12]='300'
            for i in (13,14,15,16,17,18,19,20,21):r[i]='0'
            out.append(','.join(r))
        (work/'weather.epw').write_text('\n'.join(out)+'\n',encoding='ascii')
        cases.append({'id':s['id'],'model_sha256':core.sha(work/'model.idf'),'weather_sha256':core.sha(work/'weather.epw'),'area_m2':50 if s['type']=='mixed' else 25,'expected_kwh':{k:str(F(v)*8760/1000) for k,v in reference.oracle(s)['expected_power_W'].items()},'relative_tolerance':.005,'absolute_kwh_tolerance':8.76})
    core.write_json(path/'frozen.json',{'cases':cases,'scope':'Synthetic constant controlled weather derived from public calendar only; not a real climate or measured building. Four active equipment cases plus one zero-use case.','weather_calendar_source':'fixtures/demo/reference_5zone/weather.epw','weather_calendar_sha256':core.sha(ROOT/'fixtures/demo/reference_5zone/weather.epw'),'script_sha256':core.sha(Path(__file__)),'model_builder_sha256':core.sha(Path(reference.__file__))})
    print('Frozen annual cases:',core.sha(path/'frozen.json'))


def execute(inputs,out):
    out.mkdir(parents=True,exist_ok=False);f=core.read_json(inputs/'frozen.json');assert core.sha(Path(__file__))==f['script_sha256'] and core.sha(Path(reference.__file__))==f['model_builder_sha256'];checks=[];events=[];cases=[];runtime=Path(tempfile.mkdtemp(prefix='vra-hvac-enduse-http-'))
    def save(name,obj):core.write_json(out/name,obj)
    def check(name,yes):checks.append({'name':name,'passed':bool(yes)});save('checks.json',checks);assert yes,name
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    env={**os.environ,'VRA_DATA_DIR':str(runtime/'server'),'PYTHONDONTWRITEBYTECODE':'1'};completed=False
    with (out/'server.log').open('wb') as log:
        proc=subprocess.Popen([sys.executable,'-B','-m','uvicorn','backend.api:app','--host','127.0.0.1','--port',str(port)],cwd=ROOT,env=env,stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            with httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=120,trust_env=False,event_hooks={'response':[lambda r:events.append({'method':r.request.method,'path':r.request.url.path,'status':r.status_code})]}) as c:
                for _ in range(100):
                    try:
                        if c.get('/api/health').status_code==200:break
                    except httpx.ConnectError:time.sleep(.1)
                else:raise RuntimeError('Readiness failed')
                r=c.post('/api/auth/register',json={'username':'hvac_enduse_acceptance','display_name':'隔离设备核验','password':secrets.token_urlsafe(32)});check('isolated_registration',r.status_code==200);c.headers['X-CSRF-Token']=r.json()['csrf_token']
                for case in f['cases']:
                    cid=case['id'];work=out/cid;work.mkdir();model=(inputs/cid/'model.idf').read_bytes();weather=(inputs/cid/'weather.epw').read_bytes();assert hashlib.sha256(model).hexdigest()==case['model_sha256'] and hashlib.sha256(weather).hexdigest()==case['weather_sha256']
                    r=c.post('/api/projects',json={'name':'Synthetic equipment '+cid,'building':{'use':'reference','location':'Synthetic constant weather, no real site','region':'TEST','area_m2':float(case['area_m2'])}});check(cid+'_project',r.status_code==201);pid=r.json()['project_id'];base='/api/projects/'+pid;evs=[]
                    for kind,data,name in [('idf',model,'model.idf'),('epw',weather,'synthetic.epw')]:
                        r=c.post(base+'/files',files={'file':(name,data)});check(cid+'_'+kind+'_upload',r.status_code==201);file=r.json()
                        body={'type':kind,'name':name,'source_file':file['file_id'],'source_locator':'Frozen synthetic controlled equipment reference','authority':'Independent synthetic reference author','permission':'Local public-reference verification','acquisition_method':'Generated controlled reference, not measured','responsible_person':'Acceptance author','status':'ASSUMED'}
                        if kind=='idf':body['scheme_id']='baseline'
                        r=c.post(base+'/evidence',json=body);check(cid+'_'+kind+'_evidence',r.status_code==201);ev=r.json()
                        r=c.patch(base+'/evidence/'+ev['evidence_id'],json={'expected_revision':ev['revision'],'review_state':'confirmed','responsible_person':'Acceptance author','review_note':'Synthetic controls reviewed only; not surveyed or measured building data'});check(cid+'_'+kind+'_review',r.status_code==200);evs.append(r.json())
                    r=c.get(base+'/gate');save(cid+'/gate.json',r.json());check(cid+'_gate',r.status_code==200 and r.json()['can_simulate'])
                    r=c.post('/api/runs',json={'project_id':pid,'scheme_id':'baseline','factor_profile_id':'none'});check(cid+'_run_accepted',r.status_code==202);rid=r.json()['run_id'];deadline=time.monotonic()+600
                    while time.monotonic()<deadline:
                        r=c.get('/api/runs/'+rid);view=r.json()
                        if view['status'] not in ('queued','running'):break
                        time.sleep(1)
                    save(cid+'/run.json',view);check(cid+'_real_annual_success',view['status']=='succeeded')
                    r=c.post(base+'/end-use-ledgers',json={'name':'设备分项 '+cid,'purpose':'核对受控设备真实原生能耗与独立输入算术，保留各载体口径','run_id':rid});save(cid+'/ledger-first.json',r.json());check(cid+'_ledger_created',r.status_code==201);ledger=r.json();lid=ledger['enduse_id'];route=base+'/end-use-ledgers/'+lid;summary=ledger['summary'];check(cid+'_complete_year',summary['hours']==8760)
                    index=c.get(base+'/end-use-ledgers');check(cid+'_name_only_history',index.status_code==200 and index.json()['records'][0]['enduse_id']==lid and 'summary' not in index.text)
                    for meter,want in case['expected_kwh'].items():
                        use,resource=meter.split(':');use={'InteriorEquipment':'Interior Equipment'}.get(use,use);carrier={'NaturalGas':'Natural Gas','Electricity':'Electricity','DistrictCooling':'District Cooling'}[resource];v=next(x for x in summary['rows'] if x['end_use']==use)['carriers'][carrier];expected=float(F(want));actual=v['hourly_meter_kwh'];tolerance=max(case['absolute_kwh_tolerance'],abs(expected)*case['relative_tolerance']);check(cid+'_'+meter+'_independent_energy',actual is not None and abs(actual-expected)<=tolerance)
                    if cid=='M01':
                        token=c.headers.pop('X-CSRF-Token');denied=c.post(base+'/end-use-ledgers',json={'name':'Unauthorized','purpose':'Missing CSRF must not create another ledger','run_id':rid});c.headers['X-CSRF-Token']=token;check('missing_csrf_denied',denied.status_code==403)
                        with httpx.Client(base_url=c.base_url,timeout=30,trust_env=False) as stranger:
                            for suffix in ['', '/'+lid, '/'+lid+'/report.html']:
                                check('anonymous_'+suffix,stranger.get(base+'/end-use-ledgers'+suffix).status_code==401)
                            account=stranger.post('/api/auth/register',json={'username':'enduse_outsider','display_name':'隔离外部账号','password':secrets.token_urlsafe(32)});check('outsider_registered',account.status_code==200);stranger.headers['X-CSRF-Token']=account.json()['csrf_token']
                            for suffix in ['', '/'+lid, '/'+lid+'/report.html']:
                                check('foreign_'+suffix,stranger.get(base+'/end-use-ledgers'+suffix).status_code==404)
                            denied=stranger.post(base+'/end-use-ledgers',json={'name':'Foreign account','purpose':'Cross-account creation must be rejected','run_id':rid});check('foreign_write_denied',denied.status_code==404)
                    rd=runtime/'server/runs'/rid
                    with sqlite3.connect(rd/'output/eplusout.sql') as con:
                        for row in summary['rows']:
                            for carrier,value in row['carriers'].items():
                                loc=value['tabulated']['locator'];raw=con.execute('SELECT Value FROM TabularDataWithStrings WHERE ReportName=? AND ReportForString=? AND TableName=? AND RowName=? AND ColumnName=?',(loc['report'],loc['for'],loc['table'],loc['row'],loc['column'])).fetchone()[0].strip();check(cid+'_cell_'+row['end_use']+'/'+carrier,raw==loc['raw_value'])
                        if cid=='M01':
                            projection={'model_idf':model.decode(),'mtd':(rd/'output/eplusout.mtd').read_text(),'sql_sha256':core.sha(rd/'output/eplusout.sql'),'tables':{}}
                            # Native projection keeps all expected end-use hourly meters, not redundant submeter series.
                            tables=['Simulations','EnvironmentPeriods','Time','TabularDataWithStrings','ReportDataDictionary','ReportData']
                            wanted=set()
                            from backend.end_use import USES,METER_USES,CARRIERS
                            for use in USES:
                                for resources in CARRIERS.values():wanted.update(METER_USES.get(use,use)+':'+resource for resource in resources)
                            dictionaries=con.execute("SELECT * FROM ReportDataDictionary WHERE IsMeter=1 AND ReportingFrequency='Hourly'").fetchall();cols=[x[1] for x in con.execute('PRAGMA table_info(ReportDataDictionary)')];ids=[d[cols.index('ReportDataDictionaryIndex')] for d in dictionaries if d[cols.index('Name')] in wanted]
                            for table in tables:
                                cols=[x[1] for x in con.execute('PRAGMA table_info('+table+')')]
                                query='SELECT * FROM '+table;params=()
                                if table=='ReportData':query+=' WHERE ReportDataDictionaryIndex IN ('+','.join('?' for _ in ids)+')';params=ids
                                elif table=='ReportDataDictionary':query+=' WHERE ReportDataDictionaryIndex IN ('+','.join('?' for _ in ids)+')';params=ids
                                projection['tables'][table]={'columns':cols,'rows':con.execute(query,params).fetchall()}
                            (out/'native_projection.json.gz').write_bytes(gzip.compress(json.dumps(projection,separators=(',',':')).encode(),mtime=0))
                    html=c.get(route+'/report.html');check(cid+'_report',html.status_code==200 and 'kWh' in html.text);(work/'report.html').write_text(html.text,encoding='utf8');check(cid+'_json_current',c.get(route).json()['summary']==summary)
                    r=c.patch(base+'/evidence/'+evs[0]['evidence_id'],json={'expected_revision':evs[0]['revision'],'review_state':'rejected','responsible_person':'Acceptance author','review_note':'Withdraw synthetic input to check current-state gate'});check(cid+'_withdraw',r.status_code==200)
                    r=c.get(route);save(cid+'/ledger-stale.json',r.json());check(cid+'_stale_numbers_withdrawn',r.json()['status']=='stale' and r.json()['summary'] is None);check(cid+'_stale_report', '全部数值已撤下' in c.get(route+'/report.html').text)
                    check(cid+'_original_input_preserved',core.sha(rd/'input/model.idf')==case['model_sha256']);cases.append({'id':cid,'project_id':pid,'run_id':rid,'ledger_id':lid,'run_dir':str(rd),'passed':True});save('cases.json',cases);print(cid+' passed',flush=True)
                completed=True
        finally:
            proc.terminate()
            try:proc.wait(timeout=20)
            except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=10)
            save('responses.json',events);save('receipt.json',{'completed':completed,'checks':len(checks),'passed':sum(x['passed'] for x in checks),'responses':len(events),'cases':cases,'server_stopped':proc.poll() is not None,'runtime':str(runtime),'browser_used':False,'formal_data_touched':False,'frozen_sha256':core.sha(inputs/'frozen.json')})
    print(json.dumps({'completed':completed,'checks':len(checks),'passed':sum(x['passed'] for x in checks)}))


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--freeze',type=Path);ap.add_argument('--inputs',type=Path);ap.add_argument('--output',type=Path);a=ap.parse_args()
    if a.freeze:freeze(a.freeze.resolve())
    elif a.inputs and a.output:execute(a.inputs.resolve(),a.output.resolve())
    else:ap.error('Freeze inputs or run frozen HTTP acceptance')
