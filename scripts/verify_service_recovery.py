"""Real HTTP/ASGI/EnergyPlus crash probe. Test identity never written to logs.

The only harness instrumentation records Windows staging ownership and supplies
a private stdin shutdown signal. It does not replace calculations or recovery.
"""
import argparse
from contextlib import contextmanager, closing
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import threading
import time

parser=argparse.ArgumentParser()
parser.add_argument('output');parser.add_argument('--serve',action='store_true')
parser.add_argument('--site');parser.add_argument('--port',type=int)
parser.add_argument('--parser-kind',choices=('cad','drawing','standards'))
args=parser.parse_args()
repo=Path(__file__).resolve().parents[1];sys.path.insert(0,str(repo))
if args.site:sys.path.insert(0,args.site)
out=Path(args.output).resolve()

if args.serve:
    if sys.platform=='win32':
        from backend import native_windows
        original=native_windows.staging
        def observe(kind,scope):
            data={'event':kind,**{key:str(scope[key]) for key in ('root','work','sid','profile','profile_root')}}
            with (out/'observer.jsonl').open('a',encoding='utf-8') as stream:
                stream.write(json.dumps(data)+'\n');stream.flush();os.fsync(stream.fileno())
        @contextmanager
        def observed():
            with original() as scope:
                observe('created',scope)
                yield scope
            observe('closed',scope)
        native_windows.staging=observed
    import uvicorn
    from backend.api import create_app
    server=uvicorn.Server(uvicorn.Config(create_app(out/'runtime'),host='127.0.0.1',port=args.port,log_level='warning'))
    def stop():
        sys.stdin.buffer.read(1)
        server.should_exit=True
    threading.Thread(target=stop,daemon=True).start()
    server.run()
    raise SystemExit(0)

import httpx
from backend.private_storage import private_temporary
from backend.runtime_lock import safe_path
from tests.lifetime_probe import ProcessHandle

out.mkdir(parents=True,exist_ok=False)
checks=[];process=None;handles=[];before={};observations={}
def check(name,condition):
    checks.append({'name':name,'passed':bool(condition)})
    (out/'checks.json').write_text(json.dumps(checks,indent=2),encoding='utf-8')
    if not condition:raise AssertionError(name)
def identities():
    return {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (out/'runtime/files').iterdir() if p.is_file()}
def stop_server():
    if process is not None and process.poll() is None:
        process.stdin.close()
        try:process.wait(timeout=25)
        except subprocess.TimeoutExpired:
            process.kill();process.wait(timeout=5)
            raise AssertionError('Isolated service graceful shutdown timed out')
def native_profiles():
    path=out/'observer.jsonl'
    if not path.exists():return []
    records=[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
    return [r for r in records if r['event']=='created']
def resources(temp):
    old=list(temp.glob('vra-private-*'))
    managed=[entry for root in temp.glob('vra-native-v1-*') for entry in root.iterdir() if entry.is_dir()]
    return [str(path.relative_to(temp)) for path in old+managed]
def start_server(temp):
    global process
    with socket.socket() as probe:
        probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
    import sysconfig
    python=getattr(sys,'_base_executable',sys.executable) if sys.platform=='win32' else sys.executable
    env=dict(os.environ);env.update(TMP=str(temp),TEMP=str(temp),TMPDIR=str(temp),PYTHONUTF8='1')
    log=out/('server-'+str(time.time_ns())+'.log')
    with log.open('xb') as stream:
        process=subprocess.Popen([python,str(Path(__file__).resolve()),str(out),'--serve','--site',sysconfig.get_paths()['purelib'],'--port',str(port)],
            cwd=repo,env=env,stdin=subprocess.PIPE,stdout=stream,stderr=stream,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    client=httpx.Client(base_url=f'http://127.0.0.1:{port}',trust_env=False,timeout=30)
    deadline=time.monotonic()+30
    while time.monotonic()<deadline:
        if process.poll() is not None:raise AssertionError('Isolated server failed to start; see private probe log')
        try:
            response=client.get('/api/health')
            if response.status_code==200 and response.json()['worker_alive']:return client
        except httpx.TransportError:pass
        time.sleep(.05)
    raise AssertionError('Isolated server readiness timeout')
def request(client,method,path,**kwargs):
    response=client.request(method,path,**kwargs)
    if not 200<=response.status_code<300:raise AssertionError(method+' '+path+' status '+str(response.status_code))
    return response.json()


def parser_probe(kind):
    """Kill the real service while a real parser subprocess is running."""
    import io
    global handles
    route={'cad':'cad-inspections','drawing':'drawings','standards':'standards-preview'}[kind]
    if kind=='cad':
        import ezdxf
        doc=ezdxf.new('R2010');doc.units=4
        doc.modelspace().add_line((0,0),(3000,4000))
        stream=io.StringIO();doc.write(stream);name='original.dxf';raw=stream.getvalue().encode()
    elif kind=='drawing':
        name='original.png';raw=(repo/'fixtures/drawing_gold/clean.png').read_bytes()
    else:
        from reportlab.pdfgen.canvas import Canvas
        stream=io.BytesIO();canvas=Canvas(stream,pagesize=(360,240))
        canvas.drawString(30,120,'Independent recovery reference');canvas.showPage();canvas.save()
        name='original.pdf';raw=stream.getvalue()
    password=secrets.token_urlsafe(32);pending=None;response={}
    with private_temporary(Path(tempfile.gettempdir())) as temp:
        try:
            with closing(start_server(temp)) as client:
                client.timeout=httpx.Timeout(240)
                auth=request(client,'POST','/api/auth/register',json={'username':'crash_reference','display_name':'Isolated parser test','password':password})
                client.headers['X-CSRF-Token']=auth['csrf_token'];auth=None
                pid=request(client,'POST','/api/projects',json={'name':'Synthetic crash reference',
                    'building':{'use':'office','location':'synthetic','region':'synthetic','area_m2':100}})['project_id']
                fid=request(client,'POST',f'/api/projects/{pid}/files',files={'file':(name,raw)})['file_id']
                before=identities();path=f'/api/projects/{pid}/{route}'
                def parse():
                    try:response['result']=request(client,'POST',path,json={'file_id':fid})
                    except Exception as error:response['error_type']=type(error).__name__
                pending=threading.Thread(target=parse,daemon=True);pending.start()
                deadline=time.monotonic()+180;receipt=None
                while time.monotonic()<deadline:
                    for control in temp.glob('vra-native-v1-*/*/data/engine-request.receipt.json'):
                        try:
                            value=json.loads(control.read_text())
                            if value.get('state')=='launched':receipt=value;break
                        except (OSError,ValueError):pass
                    if receipt is not None:break
                    if not pending.is_alive():raise AssertionError('Parser completed before crash point; no crash acceptance claimed')
                    time.sleep(.005)
                check('real parser launched before crash',receipt is not None)
                handles=[ProcessHandle(receipt[key]) for key in ('supervisor_pid','engine_pid')]
                check('both exact parser processes alive before crash',not any(h.exited() for h in handles))
                process.kill();process.wait(timeout=5);process.stdin.close();pending.join(timeout=5)
                check('interrupted HTTP request completed without success',not pending.is_alive() and 'result' not in response)
                deadline=time.monotonic()+5
                while time.monotonic()<deadline and not all(h.exited() for h in handles):time.sleep(.01)
                check('parser process chain exited after service kill',all(h.exited() for h in handles))
                observations.update(kind=kind,receipt=receipt,private_dirs_after_crash=resources(temp),
                    profiles_after_crash=[r['profile'] for r in native_profiles() if Path(r['profile_root']).exists()],response=response)
            with closing(start_server(temp)) as client:
                client.timeout=httpx.Timeout(240)
                auth=request(client,'POST','/api/auth/login',json={'username':'crash_reference','password':password})
                client.headers['X-CSRF-Token']=auth['csrf_token'];auth=None
                observations['private_dirs_after_restart']=resources(temp)
                observations['profiles_after_restart']=[r['profile'] for r in native_profiles() if Path(r['profile_root']).exists()]
                check('restart recovered all inactive parser resources',not observations['private_dirs_after_restart'] and not observations['profiles_after_restart'])
                check('uploaded original survives service crash unchanged',identities()==before)
                if kind!='standards':check('interrupted extraction did not publish a result',request(client,'GET',path)==[])
                result=request(client,'POST',path,json={'file_id':fid})
                value=result if kind=='standards' else result['result']
                if kind=='cad':
                    check('new DXF parse independently matches one 5 m line',value['counts']=={'LINE':1} and len(value['objects'])==1 and value['objects'][0]['length_m']==5)
                elif kind=='drawing':
                    check('new OCR matches five independent reference labels',{c['text'] for c in value['candidates']}=={'平面图','6000 mm','办公室','会议室','LEVEL 1'})
                else:check('new PDF extraction matches independent source text',value['page_count']==1 and 'Independent recovery reference' in value['pages'][0]['text'])
                check('new parser has three verified workspace leases',value['resource_limits']['execution_receipt']['workspace_leases']=={'verified':True,'count':3})
                check('original unchanged after successful retry',identities()==before)
                observations['retry']=result
            stop_server();check('parser service graceful shutdown',process.returncode==0)
            observations['private_dirs_after_stop']=resources(temp)
            observations['profiles_after_stop']=[r['profile'] for r in native_profiles() if Path(r['profile_root']).exists()]
            check('normal shutdown removed parser cache and task resources',not observations['private_dirs_after_stop'] and not observations['profiles_after_stop'])
            (out/'observations.json').write_text(json.dumps(observations,ensure_ascii=False,indent=2),encoding='utf-8')
        finally:
            stop_server()
            if pending is not None:pending.join(timeout=5)
            for handle in handles:
                try:handle.stop()
                finally:handle.close()
            # A failure retains its journal for product recovery on next startup.
            # Do not delete profiles by name-prefix or claim harness cleanup.
            from backend.native_ownership import recover
            observations['final_cleanup']=recover(temp)
            password=None
    check('outer owned fixture removed',not temp.exists())
    print(json.dumps({'kind':kind,'checks':len(checks),'retained_resources':len(observations['private_dirs_after_stop'])}))


if args.parser_kind:
    parser_probe(args.parser_kind)
    raise SystemExit(0)

password=secrets.token_urlsafe(32)  # ephemeral, only this fresh test DB; never existing UI credentials
with private_temporary(Path(tempfile.gettempdir())) as temp:
    try:
        with closing(start_server(temp)) as client:
            auth=request(client,'POST','/api/auth/register',json={'username':'crash_reference','display_name':'Isolated crash verification','password':password})
            client.headers['X-CSRF-Token']=auth['csrf_token'];auth=None
            pid=request(client,'POST','/api/reference-projects')['project_id']
            for item in request(client,'GET',f'/api/projects/{pid}/evidence'):
                request(client,'PATCH',f"/api/projects/{pid}/evidence/{item['evidence_id']}",json={
                    'expected_revision':item['revision'],'review_state':'confirmed','responsible_person':'Automated public-reference check',
                    'review_note':'Public reference only; not a measured building or professional signoff.'})
            before=identities()
            rid=request(client,'POST','/api/runs',json={'project_id':pid,'scheme_id':'baseline','factor_profile_id':'reference_scenario'})['run_id']
            deadline=time.monotonic()+60;receipt=None
            while time.monotonic()<deadline:
                receipts=list(temp.glob('vra-private-*/engine-request.receipt.json'))+list(temp.glob('vra-native-v1-*/*/data/engine-request.receipt.json'))
                for path in receipts:
                    try:
                        candidate=json.loads(path.read_text())
                        command=json.loads(path.with_name('engine-request.json').read_text())['command']
                        if candidate.get('state')=='launched' and '-d' in command:
                            receipt=candidate;break
                    except (ValueError,OSError):pass
                if receipt is not None:break
                time.sleep(.01)
            check('real annual engine launched before crash',receipt is not None)
            for name in ('supervisor_pid','engine_pid'):handles.append(ProcessHandle(receipt[name]))
            check('both exact native processes alive before crash',not any(h.exited() for h in handles))
            process.kill();process.wait(timeout=5);process.stdin.close()
            deadline=time.monotonic()+5
            while time.monotonic()<deadline and not all(h.exited() for h in handles):time.sleep(.01)
            check('native process chain exited after real service kill',all(h.exited() for h in handles))
            observations.update(project_id=pid,interrupted_run_id=rid,receipt=receipt,
                private_dirs_after_crash=resources(temp),
                profiles_after_crash=[r['profile'] for r in native_profiles() if Path(r['profile_root']).exists()])
        with closing(start_server(temp)) as client:
            auth=request(client,'POST','/api/auth/login',json={'username':'crash_reference','password':password})
            client.headers['X-CSRF-Token']=auth['csrf_token'];auth=None
            interrupted=request(client,'GET',f'/api/runs/{rid}')
            observations['interrupted_view']=interrupted
            check('interrupted run failed visibly after restart',interrupted['status']=='failed' and 'interrupted' in interrupted['error'].lower())
            check('interrupted run publishes no metrics or carbon',interrupted['metrics'] is None and interrupted['carbon'] is None)
            observations['private_dirs_after_restart']=resources(temp)
            observations['profiles_after_restart']=[r['profile'] for r in native_profiles() if Path(r['profile_root']).exists()]
            check('restart recovered all inactive engine resources',not observations['private_dirs_after_restart'] and not observations['profiles_after_restart'])
            next_id=request(client,'POST','/api/runs',json={'project_id':pid,'scheme_id':'baseline','factor_profile_id':'reference_scenario'})['run_id']
            deadline=time.monotonic()+180
            while time.monotonic()<deadline:
                fresh=request(client,'GET',f'/api/runs/{next_id}')
                if fresh['status'] not in {'queued','running'}:break
                time.sleep(.1)
            check('new real reference completes after restart',fresh['status']=='succeeded' and fresh['metrics']['annual_energy_kwh']==57193.23)
            check('new run has a distinct identity',next_id!=rid)
            check('original uploaded reference files preserved',identities()==before)
            observations['recovery_run_id']=next_id
            observations['recovery_view']=fresh
        stop_server()
        check('service graceful stop after recovery',process.returncode==0)
        observations['private_dirs_after_stop']=resources(temp)
        observations['profiles_after_stop']=[r['profile'] for r in native_profiles() if Path(r['profile_root']).exists()]
        check('normal shutdown leaves no native task resources',not observations['private_dirs_after_stop'] and not observations['profiles_after_stop'])
        (out/'observations.json').write_text(json.dumps(observations,ensure_ascii=False,indent=2),encoding='utf-8')
    finally:
        stop_server()
        for handle in handles:
            try:handle.stop()
            finally:handle.close()
        # Only profiles recorded by this harness for children of its NEW temp
        # directory. Never enumerate or delete historical VRA profiles.
        if sys.platform=='win32':
            from backend.native_windows import api
            _,_,userenv,_=api()
            for record in native_profiles():
                root=safe_path(record['root']);profile=safe_path(record['profile_root'])
                assert root.is_relative_to(temp) and (root.name.startswith('vra-private-') or root.name=='data')
                assert profile.parent==safe_path(Path(os.environ['LOCALAPPDATA'])/'Packages') and profile.name.casefold()==record['profile'].casefold()
                assert record['profile'].startswith('VRA.Engine.') and len(record['profile'].split('.')[-1])==32
                if profile.exists():
                    result=userenv.DeleteAppContainerProfile(record['profile'])
                    assert result>=0,'Owned probe profile cleanup failed'
        password=None
check('outer harness cleaned its own new temp root',not temp.exists())
print(json.dumps({'checks':len(checks),'retained_private_dirs':len(observations['private_dirs_after_stop']),
                  'retained_profiles':len(observations['profiles_after_stop']),'scope':'real ASGI crash; harness cleanup is not product recovery'}))
