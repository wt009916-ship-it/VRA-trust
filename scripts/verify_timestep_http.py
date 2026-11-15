"""Actual HTTP, three native annual runs, independent SQL comparison and withdrawal."""
import hashlib
import json
import math
import os
from pathlib import Path
import secrets
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import httpx
ROOT=Path(__file__).resolve().parents[1]


def main(reference,out):
    out.mkdir(exist_ok=False);frozen=json.loads((reference/'annual-frozen.json').read_text());raw=(reference/'annual-source.idf').read_bytes();weather=(ROOT/frozen['weather_repository_path']).read_bytes()
    sha=lambda b:hashlib.sha256(b).hexdigest()
    assert sha(raw)==frozen['model_sha256'] and sha(weather)==frozen['weather_sha256']
    runtime=Path(tempfile.mkdtemp(prefix='vra-timestep-http-'));checks=[];responses=[];complete=False;error=None
    def save(name,obj):(out/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
    save('frozen.json',frozen)
    def check(name,ok):
        checks.append({'name':name,'passed':bool(ok)})
        if not ok:raise AssertionError(name)
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    with (out/'server.log').open('w',encoding='utf-8') as log:
        process=subprocess.Popen([sys.executable,'-B','-m','uvicorn','backend.api:app','--host','127.0.0.1','--port',str(port)],cwd=ROOT,env={**os.environ,'VRA_DATA_DIR':str(runtime/'server'),'PYTHONDONTWRITEBYTECODE':'1'},stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            with httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=120,event_hooks={'response':[lambda r:responses.append({'method':r.request.method,'path':r.request.url.path,'status':r.status_code})]}) as c:
                for _ in range(100):
                    try:
                        if c.get('/api/health').status_code==200:break
                    except httpx.ConnectError:time.sleep(.1)
                else:raise RuntimeError('Isolated server unavailable')
                r=c.post('/api/auth/register',json={'username':'timestep_http_test','display_name':'Isolated timestep test','password':secrets.token_urlsafe(32)});check('registration',r.status_code==200);c.headers['X-CSRF-Token']=r.json()['csrf_token']
                project={'name':'Declared timestep comparison, public reference weather','building':{'use':'reference','location':'synthetic reference','region':'US-CO','area_m2':25}}
                r=c.post('/api/projects',json=project);check('project',r.status_code==201);pid=r.json()['project_id'];base='/api/projects/'+pid
                def upload(name,data):
                    r=c.post(base+'/files',files={'file':(name,data)});check('upload '+name,r.status_code==201);return r.json()
                def evidence(file,kind,scheme=None):
                    b={'type':kind,'name':file['name'] if 'name' in file else kind+' source','source_file':file['file_id'],'source_locator':'Frozen synthetic integration reference','authority':'Reference author','permission':'Public reference verification','acquisition_method':'Explicit imported test source','responsible_person':'Acceptance author','status':'ASSUMED' if kind=='idf' else 'IMPORTED'}
                    if scheme:b['scheme_id']=scheme
                    r=c.post(base+'/evidence',json=b);check('evidence '+str(scheme),r.status_code==201);e=r.json();r=c.patch(base+'/evidence/'+e['evidence_id'],json={'expected_revision':e['revision'],'review_state':'confirmed','responsible_person':'Acceptance author','review_note':'Explicit synthetic model and weather review; not field calibration'});check('review '+str(scheme),r.status_code==200);return r.json()
                original=upload('source.idf',raw);evidence(upload('reference.epw',weather),'epw');models={6:raw};files={6:original};ev={};runs={}
                for step in (12,60):
                    r=c.get(base+'/files/'+original['file_id']+'/timestep.idf',params={'steps':step,'expected_source_hash':original['hash']});check('derivative '+str(step),r.status_code==200);models[step]=r.content;check('only explicit number changed '+str(step),r.content==raw.replace(b'Timestep,6;',f'Timestep,{step};'.encode()));check('derivative receipt '+str(step),r.headers['x-vra-derivative-sha256']==sha(r.content));(out/f'model-{step}.idf').write_bytes(r.content);files[step]=upload(f'model-{step}.idf',r.content)
                for step,scheme in zip((6,12,60),('baseline','R1','R2')):ev[step]=evidence(files[step],'idf',scheme)
                for step,scheme in zip((6,12,60),('baseline','R1','R2')):
                    r=c.post('/api/runs',json={'project_id':pid,'scheme_id':scheme,'factor_profile_id':'none'});check('native accepted '+str(step),r.status_code==202);rid=r.json()['run_id'];deadline=time.monotonic()+600
                    while time.monotonic()<deadline:
                        view=c.get('/api/runs/'+rid).json()
                        if view['status'] not in ('queued','running'):break
                        time.sleep(1)
                    save(f'run-{step}.json',view);check('actual annual succeeded '+str(step),view['status']=='succeeded');runs[step]=rid
                    check('hourly complete '+str(step),view['metrics']['hourly_thermal']['summary']['hour_count']==8760)
                b={'name':'Declared three-step annual sensitivity','purpose':frozen['purpose'],'run_ids':list(runs.values()),'include_ideal':True,'thresholds':frozen['thresholds']}
                r=c.post(base+'/timestep-studies',json=b);save('create-response.json',r.json());check('actual study created',r.status_code==201);record=r.json();route=base+'/timestep-studies/'+record['timestep_id'];summary=record['summary'];check('all annual hours and three pairs',summary['hours']==8760 and len(summary['pairs'])==3)
                series={};independent=[]
                for step,rid in runs.items():
                    with sqlite3.connect((runtime/'server/runs'/rid/'output/eplusout.sql').as_uri()+'?mode=ro',uri=True) as con:
                        for metric,name in [('temperature_C','Zone Air Temperature'),('heating_W','Zone Air System Sensible Heating Rate'),('cooling_W','Zone Air System Sensible Cooling Rate')]:
                            rows=con.execute('SELECT r.Value FROM ReportData r JOIN ReportDataDictionary d USING(ReportDataDictionaryIndex) JOIN Time t USING(TimeIndex) JOIN EnvironmentPeriods e USING(EnvironmentPeriodIndex) WHERE d.Name=? AND d.KeyValue=? AND d.ReportingFrequency=? AND COALESCE(t.WarmupFlag,0)=0 AND e.EnvironmentType=3 ORDER BY r.TimeIndex',(name,'BOX','Hourly')).fetchall();check('independent coverage '+str(step)+metric,len(rows)==8760);series[(step,'zone',metric)]=[x[0] for x in rows]
                        for group,label in {'zone':'Zone','supply':'Supply Air','outdoor':'Outdoor Air','recovery':'Heat Recovery'}.items():
                            for part in ('sensible','latent','total'):
                                for mode in ('heating','cooling'):
                                    metric=f'{group}_{part}_{mode}_W';name=f'Zone Ideal Loads {label} {part.title()} {mode.title()} Rate';rows=con.execute('SELECT r.Value FROM ReportData r JOIN ReportDataDictionary d USING(ReportDataDictionaryIndex) JOIN Time t USING(TimeIndex) JOIN EnvironmentPeriods e USING(EnvironmentPeriodIndex) WHERE d.Name=? AND d.KeyValue=? AND d.ReportingFrequency=? AND COALESCE(t.WarmupFlag,0)=0 AND e.EnvironmentType=3 ORDER BY r.TimeIndex',(name,'IDEAL','Hourly')).fetchall();assert len(rows)==8760;series[(step,'ideal',metric)]=[x[0] for x in rows]
                for pair in summary['pairs']:
                    for row in pair['results']:
                        scope=row['scope'].replace('_aggregate','');metric=row['metric'];a=series[(pair['coarse_steps_per_hour'],scope,metric)];f=series[(pair['fine_steps_per_hour'],scope,metric)];temp=metric=='temperature_C';diff=[abs(x-y) for x,y in zip(a,f)];limits=[b['thresholds']['temperature_absolute_K'] if temp else max(b['thresholds']['load_absolute_W'],abs(y)*b['thresholds']['load_relative_pct']/100 if abs(y)>=b['thresholds']['near_zero_W'] else 0) for y in f];count=sum(e>limit for e,limit in zip(diff,limits));energy=None if temp else (math.fsum(a)-math.fsum(f))/1000
                        ok=math.isclose(row['maximum_absolute_difference'],max(diff),rel_tol=1e-10,abs_tol=1e-9) and row['hours_exceeding_threshold']==count and (row['energy_difference_kWh'] is None if temp else math.isclose(row['energy_difference_kWh'],energy,rel_tol=1e-10,abs_tol=1e-9));check('independent '+str(pair['coarse_steps_per_hour'])+'-'+str(pair['fine_steps_per_hour'])+' '+row['scope']+' '+metric,ok);independent.append({'scope':row['scope'],'metric':metric,'coarse_steps':pair['coarse_steps_per_hour'],'fine_steps':pair['fine_steps_per_hour'],'maximum_difference':max(diff),'hours_exceeding':count,'integral_difference_kWh':energy})
                save('independent-sql-check.json',independent);r=c.get(route);check('current same source JSON',r.status_code==200 and r.json()['summary']==summary);save('study.json',r.json());r=c.get(route+'/report.html');check('same source HTML',r.status_code==200 and record['source_runs'][0]['sql_sha256'] in r.text);(out/'report.html').write_text(r.text,encoding='utf-8')
                r=c.get(base+'/files/'+original['file_id']);check('original unchanged',r.content==raw)
                other=c.post('/api/projects',json=project).json()['project_id'];r=c.post('/api/projects/'+other+'/timestep-studies',json=b);check('foreign project runs rejected',r.status_code==409)
                token=c.headers.pop('X-CSRF-Token');check('CSRF rejected',c.post(base+'/timestep-studies',json=b).status_code==403);c.headers['X-CSRF-Token']=token
                e=ev[12];r=c.patch(base+'/evidence/'+e['evidence_id'],json={'expected_revision':e['revision'],'review_state':'rejected','responsible_person':'Acceptance author','review_note':'Deliberate source withdrawal after completed numerical acceptance'});check('withdraw model',r.status_code==200)
                r=c.get(route);save('stale.json',r.json());check('current numbers withdrawn',r.json()['status']=='stale' and r.json()['summary'] is None);r=c.get(route+'/report.html');check('HTML withdrawn',r.status_code==200 and 'maximum_absolute_difference' not in r.text);check('new study rejected after withdrawal',c.post(base+'/timestep-studies',json=b).status_code==409)
                with httpx.Client(base_url=str(c.base_url)) as anonymous:check('anonymous denied',anonymous.get(route).status_code==401)
                complete=True
        except Exception as exc:error=type(exc).__name__+': '+str(exc);raise
        finally:
            process.terminate()
            try:process.wait(timeout=15)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
            save('summary.json',{'all_passed':complete and all(x['passed'] for x in checks),'checks':checks,'http_responses':responses,'server_stopped':process.poll() is not None,'runtime_path':str(runtime),'error':error,'scope':'Actual annual HTTP integration and independent SQL propagation; frozen new design-day physical answers are separate. No browser or field acceptance.'})
    print(json.dumps({'all_passed':complete,'checks':len(checks),'responses':len(responses),'server_stopped':process.poll() is not None}))

if __name__=='__main__':main(Path(sys.argv[1]).resolve(),Path(sys.argv[2]).resolve())