"""Real localhost HTTP smoke on a unique isolated runtime; synthetic inputs only."""
import copy
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import httpx

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from test_lifecycle_replacements import replacement_inventory


def main():
    output=Path(sys.argv[1]).resolve();output.mkdir(parents=True,exist_ok=True)
    runtime=Path(tempfile.mkdtemp(prefix='vra-replacement-http-'))
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    env={**os.environ,'VRA_DATA_DIR':str(runtime),'PYTHONDONTWRITEBYTECODE':'1'}
    events=[]
    with (output/'server.log').open('w',encoding='utf-8') as log:
        proc=subprocess.Popen([sys.executable,'-B','-m','uvicorn','backend.api:app','--host','127.0.0.1','--port',str(port)],cwd=ROOT,env=env,stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            address=f'http://127.0.0.1:{port}'
            for _ in range(100):
                try:
                    with urllib.request.urlopen(address+'/api/health',timeout=1) as response:
                        if response.status==200:break
                except OSError:
                    if proc.poll() is not None:raise RuntimeError('Isolated server exited')
                    time.sleep(.1)
            else:raise RuntimeError('Isolated server did not start')
            with httpx.Client(base_url=address,timeout=30) as client:
                def check(label,value):
                    events.append({'check':label,'passed':bool(value)})
                    if not value:raise AssertionError(label)
                login=client.post('/api/auth/register',json={'username':'replacement_test','display_name':'Isolated replacement test','password':secrets.token_urlsafe(32)})
                check('isolated registration',login.status_code==200)
                client.headers['X-CSRF-Token']=login.json()['csrf_token']
                project=client.post('/api/projects',json={'name':'Synthetic replacement verification','building':{'use':'office','location':'Golden','region':'US-CO','area_m2':927.2}})
                check('project created',project.status_code==201);pid=project.json()['project_id'];base='/api/projects/'+pid
                f=client.post(base+'/files',files={'file':('lifetime.json',b'{"synthetic_life":20}','application/json')})
                check('original preserved',f.status_code==201);source=f.json()
                ev=client.post(base+'/evidence',json={'type':'literature','name':'Synthetic lifetime source','source_file':source['file_id'],'source_locator':'synthetic_life','authority':'Test only','permission':'synthetic test','acquisition_method':'invented arithmetic fixture','responsible_person':'test runner','status':'ASSUMED'})
                check('source evidence created',ev.status_code==201);evidence=ev.json()
                body=replacement_inventory();body['replacements'][0]['life_evidence_id']=evidence['evidence_id']
                r=client.post(base+'/lifecycle',json=body);check('replacement persisted',r.status_code==201);record=r.json();lid=record['lifecycle_id'];route=base+'/lifecycle/'+lid
                (output/'input.json').write_text(json.dumps(body,ensure_ascii=False,indent=2),encoding='utf-8')
                (output/'record.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
                check('exact schedule',[20,40]==record['result']['replacement']['components'][0]['years'])
                check('independent total',abs(record['result']['boundary_total_kgco2e']-31549.216)<1e-8)
                html=client.get(route+'/report.html');check('HTML agrees with JSON',html.status_code==200 and '459.216' in html.text and '替换事件账' in html.text)
                (output/'report.html').write_text(html.text,encoding='utf-8')
                altered=copy.deepcopy(body);altered['replacements'][0]['service_life_years']=30
                second=client.post(base+'/lifecycle',json=altered);check('new alternative',second.status_code==201)
                comparison=client.post(base+'/lifecycle-comparisons',json={'lifecycle_ids':[lid,second.json()['lifecycle_id']]})
                check('same-boundary comparison',comparison.status_code==200 and abs(comparison.json()['results'][1]['reduction_kgco2e']-229.608)<1e-8)
                (output/'comparison.json').write_text(json.dumps(comparison.json(),ensure_ascii=False,indent=2),encoding='utf-8')
                invalid=copy.deepcopy(body);invalid['activities'][0]['replacement_overlap']='unknown'
                check('unknown overlap rejected',client.post(base+'/lifecycle',json=invalid).status_code==422)
                missing=copy.deepcopy(body);missing['replacements'][0]['service_life_years']=None
                mr=client.post(base+'/lifecycle',json=missing);check('missing lifetime stays unknown',mr.status_code==201 and mr.json()['result']['boundary_total_kgco2e'] is None)
                csrf=client.headers.pop('X-CSRF-Token');check('CSRF write guard',client.post(base+'/lifecycle',json=body).status_code==403);client.headers['X-CSRF-Token']=csrf
                revoked=client.patch(base+'/evidence/'+evidence['evidence_id'],json={'expected_revision':1,'review_state':'rejected','responsible_person':'test runner','review_note':'Synthetic source withdrawn to verify stale propagation'})
                check('source revoked',revoked.status_code==200)
                stale=client.get(route).json();check('current result suppressed',stale['status']=='stale' and stale['result'] is None)
                (output/'stale.json').write_text(json.dumps(stale,ensure_ascii=False,indent=2),encoding='utf-8')
                check('revoked source cannot be reused',client.post(base+'/lifecycle',json=body).status_code==409)
                client.cookies.clear();check('unauthenticated report denied',client.get(route+'/report.html').status_code==401)
        finally:
            proc.terminate()
            try:proc.wait(timeout=15)
            except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=10)
            result={'checks':events,'all_passed':bool(events) and all(x['passed'] for x in events),'server_stopped':proc.poll() is not None,'runtime':str(runtime),'browser_acceptance':'pending; user declined browser control','source':'synthetic independent arithmetic, no real building calibration'}
            (output/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps({'checks':len(events),'all_passed':result['all_passed'],'server_stopped':result['server_stopped']},ensure_ascii=False))


if __name__=='__main__':main()
