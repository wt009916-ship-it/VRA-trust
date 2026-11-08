import copy,hashlib,json,os,secrets,socket,subprocess,sys,time,tempfile,uuid
from pathlib import Path
R=Path('C:/Users/18483/AppData/Local/Temp/vra-agent-read-execution-20261108');REPO=R;sys.path.insert(0,str(R))
OUT=R/'validation/standard-batch-20261108/model-contract';OUT.mkdir(exist_ok=False)
def write(name,value):(OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
cases=[
 {'id':'Q02-regression','message':'对照本项目合成资料TEST 101和TEST 202的2.3.4条，均指定2024版；不存在于索引中的条款要单列未找到，不要用另一规范的同号条款替代。','expected':[('TEST 101','2.3.4',2)],'missing':('TEST 202','2.3.4'),'cohort':'regression'},
 {'id':'Q04','message':'请分别摘录合成测试资料TEST 202的2024版1.2.3条和TEST 101的2024版2.3.4条，并给出各自PDF页码。只使用本项目已复核资料。','expected':[('TEST 202','1.2.3',1),('TEST 101','2.3.4',2)],'cohort':'fresh'},
 {'id':'Q05','message':'本项目合成测试资料TEST 101（2024版）有两条需要对照：1.2.3和2.3.4。请查询这两条的原文和各自PDF页码，别只返回第一条。','expected':[('TEST 101','1.2.3',1),('TEST 101','2.3.4',2)],'cohort':'fresh'}
]
seed=json.loads((R/'validation/standard-batch-20261108/browser-seed.json').read_text(encoding='utf-8'))
building=json.loads((R/'validation/scenario-agent-20261108/frozen-fresh.json').read_text(encoding='utf-8'))['cases'][0]['building']
frozen={'cases':cases,'building':building,'seed':seed,'source_hashes':{str(p.relative_to(R)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (R/'backend').glob('*.py')},'pdf_hashes':{label:hashlib.sha256((R/'validation/standard-batch-20261108'/f'{label}.pdf').read_bytes()).hexdigest() for label in ['ALPHA','BETA']},'scope':'new developer-authored synthetic source tests, actual API and model; no regulatory validity or broad accuracy claim','runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
write('frozen.json',frozen);frozen_hash=hashlib.sha256((OUT/'frozen.json').read_bytes()).hexdigest();(OUT/'frozen.sha256').write_text(frozen_hash)
print('Frozen',frozen_hash,flush=True)
runtime = json.loads(Path('D:/稀土agent-稀土制暖全流程/vra-trust/validation/local-model-20261106/prepared-runtime.json').read_text())
cache = Path(runtime['root']); model = cache/'models/Qwen3-4B-Q4_K_M.gguf'
for entry in runtime['extracted']:
    with (cache/entry['path']).open('rb') as stream:
        assert hashlib.file_digest(stream, 'sha256').hexdigest() == entry['sha256']
with model.open('rb') as stream:
    assert hashlib.file_digest(stream, 'sha256').hexdigest() == runtime['verified'][2]['sha256']
port = 18773; alias = 'vra-intent-screen'; token = secrets.token_urlsafe(32)
with socket.socket() as sock:
    sock.bind(('127.0.0.1', port))
env = {k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','TEMP','TMP','COMSPEC','SYSTEMDRIVE'}}
env.update(PATH=str(cache/'runtime')+os.pathsep+str(Path(os.environ['SystemRoot'])/'System32'), LLAMA_API_KEY=token)
args = [str(cache/'runtime/llama-server.exe'), '-m', str(model), '--host', '127.0.0.1', '--port', str(port),
        '--alias', alias, '-c', '8192', '-np', '1', '-t', '4', '-ngl', '99', '--fit', 'off', '--cache-ram', '0',
        '--no-context-shift', '--offline', '--no-webui', '--no-agent', '--no-webui-mcp-proxy', '--no-slots',
        '--jinja', '--reasoning', 'off', '--timeout', '120']
receipt = {'frozen_sha256': frozen_hash, 'model_sha256': runtime['verified'][2]['sha256'], 'cases': [],
           'runtime_commit': runtime['runtime_commit'], 'server_arguments': args, 'training': False}
log = (OUT/'server.log').open('xb')
process = subprocess.Popen(args, cwd=cache/'runtime', env=env, stdin=subprocess.DEVNULL,
                           stdout=log, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
receipt['pid'] = process.pid
write('results.json', receipt)
try:
    import httpx
    with httpx.Client(timeout=5, trust_env=False) as client:
        for _ in range(120):
            assert process.poll() is None, 'Server exited before readiness'
            try:
                if client.get(f'http://127.0.0.1:{port}/health').status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(1)
        else:
            raise RuntimeError('Readiness timeout')
        assert client.post(f'http://127.0.0.1:{port}/v1/chat/completions', json={'model': alias, 'messages': []}).status_code == 401
    command = 'Get-NetTCPConnection -State Listen | Where-Object OwningProcess -eq '+str(process.pid)+' | Select-Object LocalAddress,LocalPort | ConvertTo-Json -Compress'
    listeners = json.loads(subprocess.check_output(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', command], timeout=30, creationflags=subprocess.CREATE_NO_WINDOW))
    listeners = [listeners] if isinstance(listeners, dict) else listeners
    assert listeners and all(x['LocalAddress'] == '127.0.0.1' and x['LocalPort'] == port for x in listeners)
    receipt.update(loopback_verified=True, unauthenticated_status=401)
    from backend.private_storage import private_mkdir
    from backend.api import create_app
    from backend.local_model import LocalModelGateway
    from fastapi.testclient import TestClient
    root=private_mkdir(Path(tempfile.gettempdir())/('vra-standard-model-'+uuid.uuid4().hex))
    os.environ['VRA_LOCAL_MODEL_TOKEN']=token
    os.environ['VRA_DATA_DIR']=str(root/'data')
    app=create_app(root/'data',start_worker=False)
    original=LocalModelGateway.complete;capture={'case':None,'count':0}
    def observed(self,messages,tools,**kw):
        entry={'case':capture['case'],'messages':copy.deepcopy(messages),'tools':copy.deepcopy(tools)};began=time.monotonic()
        try:
            value=original(self,messages,tools,**kw);entry['response']=value;return value
        except Exception as error:entry['error_type']=type(error).__name__;raise
        finally:
            entry['seconds']=round(time.monotonic()-began,3);capture['count']+=1;write('call-'+str(capture['count']).zfill(3)+'.json',entry)
    LocalModelGateway.complete=observed
    with TestClient(app) as client:
        auth=client.post('/api/auth/register',json={'username':'standards_model_test','display_name':'Synthetic standards model QA','password':secrets.token_urlsafe(32)})
        assert auth.status_code==200;client.headers['X-CSRF-Token']=auth.json()['csrf_token']
        assert client.put('/api/developer/local-model',json={'enabled':True,'port':port,'model':alias}).status_code==200
        for case in cases:
            capture['case']=case['id'];before=capture['count'];started=time.monotonic()
            p=client.post('/api/projects',json={'name':'Synthetic standards '+case['id'],'building':building});assert p.status_code==201
            pid=p.json()['project_id'];base='/api/projects/'+pid;records=[]
            for source in seed['standards']:
                label='ALPHA' if source['input']['standard_code']=='TEST 101' else 'BETA'
                raw=(R/'validation/standard-batch-20261108'/f'{label}.pdf').read_bytes()
                upload=client.post(base+'/files',files={'file':(label+'.pdf',raw,'application/pdf')});assert upload.status_code==201
                data={**source['input'],'file_id':upload.json()['file_id']}
                for version in ['2024','2025'] if case.get('conflict') and label=='ALPHA' else ['2024']:
                    response=client.post(base+'/standards',json={**data,'edition':version});assert response.status_code==201,response.text
                    record=response.json();review=client.post(base+'/standards/'+record['standard_id']+'/review',json={'expected_revision':record['revision'],'state':'confirmed','basis':'Synthetic source independently prepared for frozen API model query.'});assert review.status_code==200
                    records.append(review.json())
            question=case['message']+' 查询适用日期2026-11-08。'
            response=client.post(base+'/agent/chat',json={'message':question,'mode':'local_model','allow_compute':False});assert response.status_code==202,response.text
            task=response.json()
            while task['status']=='running':
                assert time.monotonic()-started<700;time.sleep(.2);task=client.get(base+'/agent/'+task['agent_id']).json()
            write(case['id']+'-task.json',task)
            answer=task.get('answer') or {};results=[row['result'] for row in answer.get('checked_standards',[])]
            citations=[c for r in results for c in r['citations']]
            actual={(c['standard_code'],c['clause_id'],c['pdf_page']) for c in citations}
            targets=[t for r in results for t in r.get('targets',[r])]
            checks={'task_succeeded':task['status']=='succeeded','exact_citation_set':actual==set(tuple(x) for x in case['expected']),
                    'bounded_events':len(task['events'])<=15,'model_called':capture['count']>before,'not_compliance':answer.get('task_completion')!='verified','no_write':not app.state.agent.store.list('normquery',pid)}
            for field,status in [('missing','NOT_FOUND_IN_REVIEWED_INDEX'),('conflict','VERSION_CONFLICT')]:
                if case.get(field):checks[field]=any((t['query']['standard_code'],t['query']['clause_id'])==tuple(case[field]) and t['status']==status for t in targets)
            if results:
                src=records[-1];client.post(base+'/standards/'+src['standard_id']+'/review',json={'expected_revision':src['revision'],'state':'rejected','basis':'Synthetic withdrawal after inference for historical answer recheck.'})
                current=client.get(base+'/agent/'+task['agent_id']).json();write(case['id']+'-withdrawn.json',current)
                checks['withdrawn']=not current['answer'].get('checked_standards')
            receipt['cases'].append({'id':case['id'],'checks':checks,'passed':all(checks.values()),'model_calls':capture['count']-before,'batch_used':any(r.get('targets') for r in results),'seconds':round(time.monotonic()-started,3)})
            write('results.json',receipt);print(json.dumps(receipt['cases'][-1],ensure_ascii=False),flush=True)
    receipt['completed']=True

finally:
    process.terminate()
    try:
        process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        process.kill(); process.wait(timeout=10)
    log.close(); receipt['server_exit_code'] = process.returncode
    receipt['frozen_unchanged'] = hashlib.sha256((OUT/'frozen.json').read_bytes()).hexdigest() == frozen_hash
    write('results.json', receipt)
