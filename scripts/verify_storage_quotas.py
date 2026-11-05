"""Bounded local concurrent ASGI upload experiment; no production load claims."""
import argparse
import hashlib
import json
import secrets
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from fastapi.testclient import TestClient
from backend.api import create_app
from backend.domain import Domain
from backend.store import Store
from backend.encrypted_backup import create_encrypted,restore_encrypted


def main():
    parser=argparse.ArgumentParser();parser.add_argument('output');args=parser.parse_args()
    out=Path(args.output).resolve();out.mkdir(parents=True,exist_ok=False)
    app=create_app(out/'source',start_worker=False)
    limits=replace(app.state.domain.storage.limits,project_bytes=5*256*1024,total_bytes=8*256*1024,project_files=5,total_files=8)
    app.state.domain.storage.limits=limits
    inputs=[(str(i)+'\n').encode().ljust(256*1024,b'x') for i in range(24)]
    expected={hashlib.sha256(x).hexdigest() for x in inputs}
    checks=[]
    def check(value,name):
        checks.append({'name':name,'passed':bool(value)})
        (out/'checks.json').write_text(json.dumps(checks,indent=2),encoding='utf-8')
        if not value:raise AssertionError(name)
    with TestClient(app) as client:
        login=client.post('/api/auth/register',json={'username':'quota_reference','display_name':'Isolated quota test','password':secrets.token_urlsafe(32)})
        check(login.status_code==200,'isolated account')
        client.headers['X-CSRF-Token']=login.json()['csrf_token']
        projects=[]
        for n in range(2):
            response=client.post('/api/projects',json={'name':'Synthetic quota '+str(n),'building':{'use':'test','location':'synthetic','region':'test','area_m2':100}})
            check(response.status_code==201,'create project '+str(n));projects.append(response.json()['project_id'])
        barrier=threading.Barrier(24)
        def upload(i):
            barrier.wait(timeout=30);start=time.perf_counter()
            r=client.post('/api/projects/'+projects[i%2]+'/files',files={'file':('source-'+str(i)+'.csv',inputs[i])})
            return {'input':i,'status':r.status_code,'code':r.json().get('code'),'seconds':time.perf_counter()-start}
        start=time.perf_counter()
        with ThreadPoolExecutor(max_workers=24) as pool:results=list(pool.map(upload,range(24)))
        elapsed=time.perf_counter()-start
        (out/'requests.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
        check(sum(x['status']==201 for x in results)==8,'exactly eight accepted')
        check(sum(x['status']==507 for x in results)==16,'remaining sixteen refused')
        records=app.state.domain.store.list('file')
        physical=list((out/'source/files').iterdir())
        check(len(records)==len(physical)==8,'record and physical file counts agree')
        check(sum(p.stat().st_size for p in physical)==2097152,'independent physical byte sum equals budget')
        actual={hashlib.sha256(p.read_bytes()).hexdigest() for p in physical}
        check(len(actual)==8 and actual<=expected and actual=={r['hash'] for r in records},'original bytes match independent submitted hashes')
        for i,pid in enumerate(projects):
            usage=client.get('/api/projects/'+pid+'/storage').json()
            check(usage['project_files']<=5 and usage['project_bytes']<=1310720,'project bound '+str(i))
            check('total_bytes' not in usage and not usage['shared_capacity_available'],'no shared usage disclosure '+str(i))
        check(client.post('/api/reference-projects').status_code==507,'reference batch refused at capacity')
        check(len(app.state.domain.store.list('project'))==2,'no partial reference project')
        with app.state.domain.store.connect() as con:
            check(con.execute('SELECT COUNT(*) FROM project_owners').fetchone()[0]==2,'no partial ownership')
    password=secrets.token_urlsafe(40).encode()
    backup=create_encrypted(out/'source',out/'quota.vraenc',password)
    restore_encrypted(out/'quota.vraenc',out/'restored',password,backup['archive_sha256'])
    restored=Domain(Store(out/'restored'));restored.storage.limits=limits
    check(len(restored.store.list('file'))==8,'encrypted restore retains originals')
    check(all(not restored.storage.usage(pid)['shared_capacity_available'] for pid in projects),'restore rechecks shared quota')
    check({hashlib.sha256(p.read_bytes()).hexdigest() for p in (out/'restored/files').iterdir()}==actual,'restored original hashes unchanged')
    times=sorted(x['seconds'] for x in results)
    summary={'checks_passed':len(checks),'requests':24,'concurrent_clients':24,'accepted':8,'rejected':16,
             'stored_bytes':2097152,'elapsed_seconds':elapsed,'request_median_seconds':statistics.median(times),'request_p95_seconds':times[22],
             'scope':'one local ASGI process; real disk and SQLite; not a TCP/proxy or long-duration production stress test',
             'encrypted_restore':True,'passphrase_retained':False,'score_claim':None}
    (out/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary))


if __name__=='__main__':main()
