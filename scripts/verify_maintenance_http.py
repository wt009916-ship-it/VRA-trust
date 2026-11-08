"""Synthetic local HTTP acceptance; no model, browser or production runtime."""
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import httpx
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]


def main():
    out=Path(sys.argv[1]).resolve();out.mkdir(parents=True,exist_ok=False)
    runtime=Path(tempfile.mkdtemp(prefix='vra-maintenance-http-'))
    os.environ['VRA_DATA_DIR']=str(runtime/'oracle-runtime')
    from test_maintenance_api import setup, close, payload
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    responses=[];checks=[]
    def check(name,condition):
        checks.append({'name':name,'passed':bool(condition)})
        if not condition:raise AssertionError(name)
    with (out/'server.log').open('w',encoding='utf-8') as log:
        process=subprocess.Popen([sys.executable,'-B','-m','uvicorn','backend.api:app','--host','127.0.0.1','--port',str(port)],cwd=ROOT,env={**os.environ,'VRA_DATA_DIR':str(runtime/'server'),'PYTHONDONTWRITEBYTECODE':'1'},stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            with httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=30,event_hooks={'response':[lambda r:responses.append({'method':r.request.method,'path':r.request.url.path,'status':r.status_code})]}) as client:
                for _ in range(100):
                    try:
                        if client.get('/api/health').status_code==200:break
                    except httpx.ConnectError:time.sleep(.1)
                else:raise RuntimeError('Server unavailable')
                login=client.post('/api/auth/register',json={'username':'maintenance_http_test','display_name':'Synthetic workflow test','password':secrets.token_urlsafe(32)})
                check('isolated registration',login.status_code==200);client.headers['X-CSRF-Token']=login.json()['csrf_token']
                pid,base,ops,ev,order=setup(client,runtime)
                check('event source opening',order['state']=='open' and order['source_event']['observed_span_seconds']==120)
                closed=close(client,base,order,ops,ev)
                check('real workflow closed under declared rule',closed['state']=='closed_under_declared_rule' and closed['revision']==5)
                check('separate identity and stated responsible person',closed['actions'][0]['actor_user_id']!='Technician')
                check('no diagnosis or health certification',closed['equipment_health']=='NOT_ASSESSED' and closed['cause_confirmed'] is False and closed['data_nature']=='synthetic')
                route=base+'/maintenance-orders/'+closed['maintenance_id']
                report=client.get(route+'/report.html');check('same source report',report.status_code==200 and closed['hash'] in report.text)
                (out/'closed.json').write_text(json.dumps(closed,ensure_ascii=False,indent=2),encoding='utf-8');(out/'report.html').write_text(report.text,encoding='utf-8')
                check('old revision cannot overwrite',client.post(route+'/actions',json=payload(order,'triage')).status_code==409)
                csrf=client.headers.pop('X-CSRF-Token');check('CSRF enforced',client.post(route+'/actions',json=payload(closed,'reopen')).status_code==403);client.headers['X-CSRF-Token']=csrf
                withdrawn=client.patch(base+'/evidence/'+ev['evidence_id'],json={'expected_revision':1,'review_state':'rejected','responsible_person':'Auditor','review_note':'Synthetic maintenance evidence withdrawn for acceptance'})
                check('source withdrawal',withdrawn.status_code==200)
                stale=client.get(route).json();check('current conclusion revoked',stale['status']=='stale' and stale['recheck'] is None)
                (out/'stale.json').write_text(json.dumps(stale,ensure_ascii=False,indent=2),encoding='utf-8')
                check('withdrawn order cannot advance',client.post(route+'/actions',json=payload(closed,'reopen')).status_code==409)
                client.cookies.clear();check('anonymous report denied',client.get(route+'/report.html').status_code==401)
        finally:
            process.terminate();process.wait(timeout=15)
            receipt={'checks':checks,'all_passed':len(checks)==12 and all(c['passed'] for c in checks),'http_responses':responses,'server_stopped':process.poll() is not None,'scope':'synthetic local HTTP, not actual field repair or browser acceptance'}
            (out/'summary.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps({'checks':len(checks),'all_passed':receipt['all_passed'],'http_responses':len(responses),'server_stopped':receipt['server_stopped']}))


if __name__=='__main__':main()
