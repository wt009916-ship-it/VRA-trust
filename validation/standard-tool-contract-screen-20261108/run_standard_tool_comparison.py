"""Frozen actual application comparison; no scripted model responses or prompt changes."""
from pathlib import Path
import argparse,copy,hashlib,json,os,secrets,socket,subprocess,sys,time
from io import BytesIO
parser=argparse.ArgumentParser();parser.add_argument('--variant',choices=['baseline','candidate'],required=True);args=parser.parse_args()
work=Path(__file__).parent
repo=Path('C:/Users/18483/AppData/Local/Temp')/('vra-semantic-standards-20261108' if args.variant=='baseline' else 'vra-standard-tool-contract-20261108')
out=Path('C:/Users/18483/AppData/Local/Temp/vra-standard-tool-model-20261108')/args.variant
assert not out.exists();out.mkdir(parents=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
fixture=work/'standard-tool-frozen.json';assert sha(fixture)=='23a926f3f0d95361ea16726b201def21850ab330cae825eb2afd7d9a51f10e48'
frozen=json.loads(fixture.read_text(encoding='utf-8'))
sys.path.insert(0,str(repo));os.environ.update(VRA_DATA_DIR=str(out/'private/api'),PYTHONDONTWRITEBYTECODE='1',VRA_LOCAL_MODEL_TOKEN=secrets.token_urlsafe(32))
from backend.private_storage import private_mkdir
private_mkdir(out/'private')
from backend.api import create_app
from backend.local_model import LocalModelGateway,LocalModelSettings
from backend.agent import WRITE_TOOLS
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas
import httpx
def save(name,obj):(out/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
sources={p.relative_to(repo).as_posix():sha(p) for p in sorted((repo/'backend').glob('*.py'))}
save('frozen.json',{'definition':frozen,'fixture_sha256':sha(fixture),'source_hashes':sources,'runner_sha256':sha(Path(__file__))})
pdfs={}
for source in frozen['sources']:
    buf=BytesIO();c=canvas.Canvas(buf,invariant=1)
    for clause,page,text in source['clauses']:
        c.drawString(35,760,source['code']+' synthetic fixture, not a real regulation')
        c.drawString(35,720,clause+' '+text);c.showPage()
    c.save();pdfs[source['code']]=buf.getvalue()
    (out/(source['code'].replace(' ','-')+'.pdf')).write_bytes(buf.getvalue())
runtime=json.loads((work.parents[1]/'vra-trust/validation/local-model-20261106/prepared-runtime.json').read_text())
cache=Path(runtime['root']);exe=cache/'runtime/llama-server.exe';model=cache/'models/Qwen3-4B-Q4_K_M.gguf'
for entry in runtime['extracted']:assert sha(cache/entry['path'])==entry['sha256']
assert sha(model)==runtime['verified'][2]['sha256']
with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
alias='vra-standard-contract';env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','TEMP','TMP','COMSPEC','SYSTEMDRIVE'}}
env.update(PATH=str(exe.parent)+os.pathsep+str(Path(os.environ['SystemRoot'])/'System32'),LLAMA_API_KEY=os.environ['VRA_LOCAL_MODEL_TOKEN'])
command=[str(exe),'-m',str(model),'--host','127.0.0.1','--port',str(port),'--alias',alias,'-c','8192','-np','1','-t','4','-ngl','99','--fit','off','--cache-ram','0','--no-context-shift','--offline','--no-webui','--no-agent','--no-webui-mcp-proxy','--no-slots','--jinja','--reasoning','off','--timeout','120']
receipt={'variant':args.variant,'source_hashes':sources,'fixture_sha256':sha(fixture),'model_sha256':sha(model),'runtime_commit':runtime['runtime_commit'],'cases':[],'training':False,'prototype_touched':False,'server_arguments':command}
app=create_app(out/'private/api',start_worker=False)
log=(out/'server.log').open('xb');proc=subprocess.Popen(command,cwd=exe.parent,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
receipt['server_pid']=proc.pid;save('results.json',receipt)
original=LocalModelGateway.complete;capture={'case':None,'index':0}
def observed(self,messages,tools,**kwargs):
    started=time.monotonic();entry={'case':capture['case'],'messages':copy.deepcopy(messages),'tools':copy.deepcopy(tools)}
    try:response=original(self,messages,tools,**kwargs);entry['response']=response;return response
    except Exception as exc:entry['error_type']=type(exc).__name__;raise
    finally:
        capture['index']+=1;entry['seconds']=round(time.monotonic()-started,3);save(f"model-call-{capture['index']:03}.json",entry)
LocalModelGateway.complete=observed
try:
    with httpx.Client(timeout=5,trust_env=False) as net:
        for _ in range(120):
            assert proc.poll() is None,'Server terminated during startup'
            try:
                if net.get(f'http://127.0.0.1:{port}/health').status_code==200:break
            except httpx.HTTPError:pass
            time.sleep(1)
        else:raise TimeoutError('Server readiness timeout')
        assert net.post(f'http://127.0.0.1:{port}/v1/chat/completions',json={'model':alias,'messages':[]}).status_code==401
    listener_command='Get-NetTCPConnection -State Listen | Where-Object OwningProcess -eq '+str(proc.pid)+' | Select-Object LocalAddress,LocalPort | ConvertTo-Json -Compress'
    listeners=json.loads(subprocess.check_output(['powershell.exe','-NoProfile','-NonInteractive','-Command',listener_command],timeout=30,creationflags=subprocess.CREATE_NO_WINDOW))
    listeners=[listeners] if isinstance(listeners,dict) else listeners
    assert listeners and all(x['LocalAddress']=='127.0.0.1' and x['LocalPort']==port for x in listeners)
    receipt.update(loopback_verified=True,unauthenticated_status=401)
    with TestClient(app) as client:
        auth=client.post('/api/auth/register',json={'username':'contract_model_test','display_name':'Isolated contract test','password':secrets.token_urlsafe(32)});assert auth.status_code==200
        client.headers['X-CSRF-Token']=auth.json()['csrf_token']
        app.state.agent.local_model.save(LocalModelSettings(enabled=True,port=port,model=alias))
        for case in frozen['cases']:
            capture['case']=case['id'];before=capture['index'];started=time.monotonic()
            p=client.post('/api/projects',json={'name':'Contract '+case['id'],'building':{'use':'office','location':'Synthetic','region':'US-CO','area_m2':840.}});assert p.status_code==201
            pid=p.json()['project_id'];base='/api/projects/'+pid;records=[]
            for source in frozen['sources']:
                upload=client.post(base+'/files',files={'file':(source['code']+'.pdf',pdfs[source['code']],'application/pdf')});assert upload.status_code==201
                data={'file_id':upload.json()['file_id'],'standard_code':source['code'],'edition':'2025','title':'Synthetic test source '+source['code'],'publisher':'Independent developer test author','source_url':'https://example.org/synthetic-contract-test','permission':'Created synthetic source for testing; not an actual standard','jurisdiction':'TEST ONLY','scope':'Synthetic office source reading; no engineering regulation','effective_from':'2025-01-01','retired_on':None,'status_checked_on':'2026-10-01','status_basis':'Synthetic validity declarations fixed before actual model inference','clauses':[{'clause_id':clause,'pdf_page':page,'printed_page':str(page),'coverage':'whole_clause','transcription':'text_layer','topic':text,'text':text} for clause,page,text in source['clauses']]}
                for version in ['2025','2026'] if case.get('conflict') and source['code']=='TEST 811' else ['2025']:
                    record=client.post(base+'/standards',json={**data,'edition':version});assert record.status_code==201,record.text;r=record.json()
                    review=client.post(base+'/standards/'+r['standard_id']+'/review',json={'expected_revision':r['revision'],'state':'confirmed','basis':'Checked fixed synthetic document and exact page text before inference.'});assert review.status_code==200;records.append(review.json())
            response=client.post(base+'/agent/chat',json={'message':case['question']+' 查询适用日期'+frozen['as_of']+'。仅使用本项目已复核资料。','mode':'local_model','allow_compute':False});assert response.status_code==202,response.text
            aid=response.json()['agent_id'];deadline=time.monotonic()+700
            while time.monotonic()<deadline:
                response=client.get(base+'/agent/'+aid);assert response.status_code==200;task=response.json()
                if task['status']!='running':break
                time.sleep(.25)
            else:raise TimeoutError('Existing Agent task still running; inspect handle before any restart')
            answer=task.get('answer') or {};results=[r['result'] for r in answer.get('checked_standards',[])];citations=[c for r in results for c in r['citations']]
            actual={(c['standard_code'],c['clause_id'],c['pdf_page']) for c in citations};targets=[t for r in results for t in r.get('targets',[r])]
            golden={(s['code'],clause):(page,text) for s in frozen['sources'] for clause,page,text in s['clauses']}
            checks={'task_succeeded':task['status']=='succeeded','exact_citation_set':actual=={tuple(x) for x in case['citations']},'real_model_called':capture['index']>before,'within_event_budget':len(task['events'])<=15,'no_write_tools':not any(e['tool'] in WRITE_TOOLS for e in task['events']),'source_text_exact':all(golden.get((c['standard_code'],c['clause_id']))==(c['pdf_page'],c['text']) for c in citations),'not_compliance':answer.get('task_completion')!='verified','queries_not_persisted':not app.state.agent.store.list('normquery',pid)}
            for field,status in [('missing','NOT_FOUND_IN_REVIEWED_INDEX'),('conflict','VERSION_CONFLICT')]:
                for code,clause in case.get(field,[]):checks[field+'_'+code]=any(t['query']['standard_code']==code and t['query']['clause_id']==clause and t['status']==status for t in targets)
            save(case['id']+'-raw.json',{'case':case,'records':records,'task':task})
            if results:
                for r in records:
                    revoke=client.post(base+'/standards/'+r['standard_id']+'/review',json={'expected_revision':r['revision'],'state':'rejected','basis':'Withdraw all synthetic sources after delivery to test historical answer currentness.'});assert revoke.status_code==200
                current=client.get(base+'/agent/'+aid).json();save(case['id']+'-withdrawn.json',current);checks['withdrawn_after_source_revocation']=not (current.get('answer') or {}).get('checked_standards')
            else:checks['withdrawn_after_source_revocation']=False
            row={'id':case['id'],'passed':all(checks.values()),'checks':checks,'model_calls':capture['index']-before,'seconds':round(time.monotonic()-started,3),'batch_used':any(r.get('targets') for r in results)}
            receipt['cases'].append(row);save('results.json',receipt);print(json.dumps(row,ensure_ascii=False),flush=True)
    receipt['completed']=True
finally:
    proc.terminate()
    try:proc.wait(timeout=30)
    except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=10)
    log.close();receipt['server_exit_code']=proc.returncode
    receipt['source_unchanged']=sources=={p.relative_to(repo).as_posix():sha(p) for p in sorted((repo/'backend').glob('*.py'))}
    receipt['fixture_unchanged']=sha(fixture)=='23a926f3f0d95361ea16726b201def21850ab330cae825eb2afd7d9a51f10e48'
    save('results.json',receipt)
