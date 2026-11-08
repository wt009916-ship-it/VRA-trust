"""Real local HTTP: diagnostic derivative, annual native run, reports and withdrawal."""
import hashlib
import io
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
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.ideal_loads import VARIABLES


def main(reference,out):
    out.mkdir(parents=True,exist_ok=False);source=(reference/'annual-source-v1.idf').read_bytes();frozen=json.loads((reference/'annual-inputs-v1.json').read_text())
    weather=(ROOT/frozen['weather_repository_path']).read_bytes()
    assert hashlib.sha256(source).hexdigest()==frozen['model_sha256'] and hashlib.sha256(weather).hexdigest()==frozen['weather_sha256']
    (out/'frozen.json').write_text(json.dumps(frozen,indent=2)+'\n',encoding='utf-8')
    runtime=Path(tempfile.mkdtemp(prefix='vra-ideal-http-'));checks=[];responses=[];complete=False
    with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    def check(name,condition):
        checks.append({'name':name,'passed':bool(condition)})
        if not condition:raise AssertionError(name)
    def save(name,obj):(out/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    with (out/'server.log').open('w',encoding='utf-8') as log:
        process=subprocess.Popen([sys.executable,'-B','-m','uvicorn','backend.api:app','--host','127.0.0.1','--port',str(port)],cwd=ROOT,env={**os.environ,'VRA_DATA_DIR':str(runtime/'server'),'PYTHONDONTWRITEBYTECODE':'1'},stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            with httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=120,event_hooks={'response':[lambda r:responses.append({'method':r.request.method,'path':r.request.url.path,'status':r.status_code})]}) as client:
                for _ in range(100):
                    try:
                        if client.get('/api/health').status_code==200:break
                    except httpx.ConnectError:time.sleep(.1)
                else:raise RuntimeError('Local server unavailable')
                r=client.post('/api/auth/register',json={'username':'ideal_load_http_test','display_name':'Isolated ideal load test','password':secrets.token_urlsafe(32)})
                check('isolated registration',r.status_code==200);client.headers['X-CSRF-Token']=r.json()['csrf_token']
                r=client.post('/api/projects',json={'name':'Synthetic moisture balance on public weather','building':{'use':'reference','location':'public reference weather, synthetic model','region':'US-CO','area_m2':25}})
                check('project created',r.status_code==201);pid=r.json()['project_id'];base='/api/projects/'+pid
                r=client.post(base+'/files',files={'file':('source.idf',source)});check('source original uploaded',r.status_code==201);original=r.json()
                r=client.get(base+'/files/'+original['file_id']+'/ideal-load-output.idf',params={'expected_source_hash':original['hash']})
                check('diagnostic download actual route',r.status_code==200);derived=r.content
                check('all diagnostic requests added',int(r.headers['x-vra-added-output-requests'])==26)
                check('original byte prefix retained',derived.startswith(source));(out/'derived.idf').write_bytes(derived)
                evidences=[]
                for kind,name,data in [('idf','diagnostic.idf',derived),('epw','reference.epw',weather)]:
                    r=client.post(base+'/files',files={'file':(name,data)});check(kind+' uploaded',r.status_code==201);file=r.json()
                    body={'type':kind,'name':name,'source_file':file['file_id'],'source_locator':'Frozen synthetic acceptance and public weather reference','authority':'Test author / public reference weather','permission':'Local reference verification','acquisition_method':'Explicit diagnostic derivative' if kind=='idf' else 'Existing public reference EPW','responsible_person':'Acceptance author','status':'ASSUMED' if kind=='idf' else 'IMPORTED'}
                    if kind=='idf':body['scheme_id']='baseline'
                    r=client.post(base+'/evidence',json=body);check(kind+' evidence saved',r.status_code==201);e=r.json()
                    r=client.patch(base+'/evidence/'+e['evidence_id'],json={'expected_revision':e['revision'],'review_state':'confirmed','responsible_person':'Acceptance author','review_note':'Synthetic controls reviewed for test only, not a surveyed building'})
                    check(kind+' explicitly reviewed',r.status_code==200);evidences.append(r.json())
                r=client.get(base+'/gate');check('native input gate',r.status_code==200 and r.json()['can_simulate'])
                r=client.post('/api/runs',json={'project_id':pid,'scheme_id':'baseline','factor_profile_id':'none'});check('real annual run accepted',r.status_code==202);rid=r.json()['run_id'];route='/api/runs/'+rid
                deadline=time.monotonic()+600
                while time.monotonic()<deadline:
                    r=client.get(route);view=r.json()
                    if view['status'] not in ('queued','running'):break
                    time.sleep(1)
                save('run.json',view);check('native annual run succeeded',view['status']=='succeeded')
                receipt=view['metrics']['ideal_loads'];check('ideal output available',receipt['status']=='calculated_model_scenario');summary=receipt['summary']
                check('complete annual hours',summary['hour_count']==8760);check('one declared system',summary['coverage']['ideal_system_count']==1)
                check('model binding',receipt['model_sha256']==hashlib.sha256(derived).hexdigest())
                sql=runtime/'server/runs'/rid/'output/eplusout.sql';check('SQL binding',receipt['sql_sha256']==hashlib.sha256(sql.read_bytes()).hexdigest())
                independent={}
                with sqlite3.connect(sql.as_uri()+'?mode=ro',uri=True) as con:
                    for key,(variable,unit) in VARIABLES.items():
                        dictionary=con.execute('SELECT ReportDataDictionaryIndex FROM ReportDataDictionary WHERE Name=? AND KeyValue=? AND ReportingFrequency=?',(variable,'IDEAL','Hourly')).fetchall();check(key+' dictionary unique',len(dictionary)==1)
                        values=[r[0] for r in con.execute('SELECT r.Value FROM ReportData r JOIN Time t ON t.TimeIndex=r.TimeIndex JOIN EnvironmentPeriods e ON e.EnvironmentPeriodIndex=t.EnvironmentPeriodIndex WHERE r.ReportDataDictionaryIndex=? AND e.EnvironmentType=3 AND COALESCE(t.WarmupFlag,0)=0 ORDER BY r.TimeIndex',(dictionary[0][0],))]
                        check(key+' independent hourly coverage',len(values)==8760)
                        expected={'peak':max(values),'integral':math.fsum(values)*(1/1000 if unit=='W' else 3600)};independent[key]=expected;actual=summary['aggregate'][key]
                        check(key+' native peak and integral',math.isclose(actual['peak']['value'],expected['peak'],rel_tol=1e-10,abs_tol=1e-8) and math.isclose(actual['energy_kWh' if unit=='W' else 'air_mass_kg'],expected['integral'],rel_tol=1e-10,abs_tol=1e-8))
                save('independent-sql-crosscheck.json',independent)
                r=client.get(route+'/report.json');check('same source JSON report',r.status_code==200 and r.json()['run']['metrics']['ideal_loads']==receipt);save('report.json',r.json())
                r=client.get(route+'/report.html');check('same source HTML report',r.status_code==200 and receipt['sql_sha256'] in r.text);(out/'report.html').write_text(r.text,encoding='utf-8')
                r=client.get(route+'/report.pdf');check('actual PDF generated',r.status_code==200 and r.content.startswith(b'%PDF'));(out/'report.pdf').write_bytes(r.content)
                text='\n'.join(p.extract_text() or '' for p in PdfReader(io.BytesIO(r.content)).pages)
                check('PDF includes load boundary section','05.5' in text and '原生数值已经包含' in text)
                (out/'pdf-text.txt').write_text(text,encoding='utf-8')
                check('original download still exact',client.get(base+'/files/'+original['file_id']).content==source)
                e=evidences[0];r=client.patch(base+'/evidence/'+e['evidence_id'],json={'expected_revision':e['revision'],'review_state':'rejected','responsible_person':'Acceptance author','review_note':'Withdraw model applicability; current results must disappear'})
                check('model evidence withdrawn',r.status_code==200);stale=client.get(route).json();save('stale.json',stale)
                check('all current metrics withdrawn',stale['status']=='stale' and stale['metrics'] is None)
                check('stale JSON has no latent numbers',client.get(route+'/report.json').json()['run']['metrics'] is None)
                check('withdrawn model cannot run',client.post('/api/runs',json={'project_id':pid,'scheme_id':'baseline'}).status_code==409)
                client.cookies.clear();check('anonymous report denied',client.get(route+'/report.pdf').status_code==401)
                complete=True
        finally:
            process.terminate()
            try:process.wait(timeout=15)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
            save('summary.json',{'checks':checks,'all_passed':complete and all(c['passed'] for c in checks),'http_responses':responses,'server_stopped':process.poll() is not None,'runtime_path':str(runtime),'scope':'Actual HTTP and annual native integration; independent physics is the separate frozen steady probes, no browser or field validation'})
            print(json.dumps({'checks':len(checks),'all_passed':complete and all(c['passed'] for c in checks),'responses':len(responses),'server_stopped':process.poll() is not None}))


if __name__=='__main__':main(Path(sys.argv[1]).resolve(),Path(sys.argv[2]).resolve())
