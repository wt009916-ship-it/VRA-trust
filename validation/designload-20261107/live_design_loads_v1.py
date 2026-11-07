"""Actual local model + authenticated API + one fresh native annual run per model. No training."""
import copy, hashlib, json, os, secrets, socket, subprocess, sys, time
from pathlib import Path
out = Path(__file__).parent; repo = out.parents[1]
variant = sys.argv[1]; assert variant in {'4b', '8b'}
snapshot = json.loads((out / 'final-source-v1.json').read_text())
source = Path(snapshot['root']); sys.path.insert(0, str(source))
for item in snapshot['files']:
    assert hashlib.sha256((source / item['path']).read_bytes()).hexdigest() == item['sha256']
from backend.private_storage import private_mkdir
root = private_mkdir(Path(snapshot['base']) / ('live-' + variant))
runtime = json.loads((repo / 'validation/local-model-20261106/prepared-runtime.json').read_text())
cache = Path(runtime['root'])
model_info = runtime['verified'][2] if variant == '4b' else json.loads((repo / 'validation/model-comparison-20261106/prepared-candidate.json').read_text())
model = cache / 'models/Qwen3-4B-Q4_K_M.gguf' if variant == '4b' else Path(model_info['local_path'])
for item in runtime['extracted']:
    with (cache / item['path']).open('rb') as handle: assert hashlib.file_digest(handle, 'sha256').hexdigest() == item['sha256']
with model.open('rb') as handle: assert hashlib.file_digest(handle, 'sha256').hexdigest() == model_info['sha256']
os.environ.update(VRA_DATA_DIR=str(root / 'bootstrap'), VRA_LOCAL_MODEL_TOKEN=secrets.token_urlsafe(32),
                  ENERGYPLUS_EXE='F:/EnergyPlusV9-0-1/energyplus.exe', PYTHONDONTWRITEBYTECODE='1')
port = 18773; alias = 'vra-designload-acceptance'
with socket.socket() as sock: sock.bind(('127.0.0.1', port))
env = {k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','TEMP','TMP','COMSPEC','SYSTEMDRIVE'}}
env.update(PATH=str(cache/'runtime') + os.pathsep + str(Path(os.environ['SystemRoot'])/'System32'), LLAMA_API_KEY=os.environ['VRA_LOCAL_MODEL_TOKEN'])
exe = cache/'runtime/llama-server.exe'
args = [str(exe), '-m', str(model), '--host','127.0.0.1','--port',str(port),'--alias',alias,
        '-c','8192','-np','1','-t','4','-ngl','99','--fit','off','--cache-ram','0','--no-context-shift',
        '--offline','--no-webui','--no-agent','--no-webui-mcp-proxy','--no-slots','--jinja','--reasoning','off','--timeout','120']
receipt = {'application_commit':snapshot['application_commit'], 'variant':variant, 'model_sha256':model_info['sha256'],
           'root':str(root), 'server_arguments':args, 'training':False, 'cases':[], 'requests':[],
           'protocol_fixture':False, 'original_prototype_used':False}
summary = out / ('live-' + variant + '-v1.json')
assert not summary.exists()
def save(): summary.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
log = (root/'server.log').open('xb')
process = subprocess.Popen(args,cwd=exe.parent,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
receipt['server_pid'] = process.pid; save()
try:
    import httpx
    with httpx.Client(timeout=5,trust_env=False) as net:
        for _ in range(120):
            assert process.poll() is None
            try:
                if net.get(f'http://127.0.0.1:{port}/health').status_code == 200: break
            except httpx.HTTPError: pass
            time.sleep(1)
        else: raise RuntimeError('Local model readiness timeout')
        assert net.post(f'http://127.0.0.1:{port}/v1/chat/completions',json={'model':alias,'messages':[]}).status_code == 401
    from fastapi.testclient import TestClient
    from backend.api import create_app
    from backend.local_model import LocalModelGateway
    from backend import core
    active = {'case':None}; original = LocalModelGateway.complete
    def observed(self,messages,tools,**kwargs):
        start=time.monotonic(); entry={'case':active['case'], 'messages':copy.deepcopy(messages), 'tools':copy.deepcopy(tools)}
        try:
            result=original(self,messages,tools,**kwargs); entry['response']=result; return result
        except Exception as exc:
            entry['error']={'type':type(exc).__name__,'message':str(exc)}; raise
        finally:
            path=root/f'model-call-{len(receipt["requests"])+1:03}.json'
            entry['seconds']=round(time.monotonic()-start,3); core.write_json(path,entry)
            receipt['requests'].append({'case':active['case'],'path':str(path),'sha256':core.sha(path),'seconds':entry['seconds'],
                                        'message_characters':len(json.dumps(messages,ensure_ascii=False)),
                                        'response':entry.get('response'),'error':entry.get('error')}); save()
    LocalModelGateway.complete=observed  # Passive recording; original real HTTP output unchanged.
    app=create_app(root/'api',start_worker=False)
    with TestClient(app) as client:
        r=client.post('/api/auth/register',json={'username':'isolated_design_loads','display_name':'Public reference verifier','password':secrets.token_urlsafe(32)})
        assert r.status_code==200; client.headers['X-CSRF-Token']=r.json()['csrf_token']
        assert client.put('/api/developer/local-model',json={'enabled':True,'port':port,'model':alias}).status_code==200
        r=client.post('/api/reference-projects'); assert r.status_code==201; pid=r.json()['project_id']; base='/api/projects/'+pid
        for ev in client.get(base+'/evidence').json():
            r=client.patch(base+'/evidence/'+ev['evidence_id'],json={'expected_revision':ev['revision'],'review_state':'confirmed',
                'responsible_person':'Isolated verifier','review_note':'Public reference scenario, not real building validation'})
            assert r.status_code==200
        r=client.post('/api/runs',json={'project_id':pid,'scheme_id':'baseline'}); assert r.status_code==202; rid=r.json()['run_id']
        job=app.state.domain.store.claim_job(); assert job['run_id']==rid; app.state.domain.execute(job)
        report=client.get('/api/runs/'+rid+'/report.json').json(); core.write_json(root/'native-report.json',report)
        view=report['run']; assert view['status']=='succeeded'; sizing=view['metrics']['zone_design_loads']; assert len(sizing['rows'])==10
        receipt.update(run_id=rid,project_id=pid,new_native_runs=1,physics_code_hash=core.code_hash(),native_report_sha256=core.sha(root/'native-report.json'))
        cases=[('DL-L1','复核这个运行的分区供暖和制冷设计负荷，列齐每条记录的分区、显热计算值、用户调整值、峰值设计日与时刻，说明倍率口径和适用范围。不要把分区峰值相加当作全楼同时峰值。'),
               ('DL-L2','只核查SPACE5-1分区的制冷记录，给出计算显热W、用户调整值W和峰值时刻，并说明能否直接把它当成北京项目的设备总冷量。请读取实际结果。'),
               ('DL-L3','复核同一个运行目前是否有效；若已经失效，说明不能继续作为当前设计负荷，不要从历史数字补成有效结果。')]
        receipt['predeclared_cases']=cases; save()
        for ident,message in cases:
            if ident=='DL-L3':
                ev=client.get(base+'/evidence').json()[0]
                assert client.patch(base+'/evidence/'+ev['evidence_id'],json={'expected_revision':ev['revision'],'review_state':'pending','responsible_person':'Isolated verifier','review_note':'Withdraw for stale acceptance'}).status_code==200
                current=client.get('/api/runs/'+rid).json(); assert current['status']=='stale' and current['metrics'] is None
            active['case']=ident; before=len(receipt['requests']); started=time.monotonic()
            r=client.post(base+'/agent/chat',json={'message':message,'mode':'local_model','objective':'inspect_results','target_run_id':rid})
            assert r.status_code==202,r.text; aid=r.json()['agent_id']
            for _ in range(660):
                task=client.get(base+'/agent/'+aid).json()
                if task['status']!='running': break
                time.sleep(1)
            else: raise RuntimeError('Task timeout')
            path=root/(ident+'-task.json'); core.write_json(path,task)
            pages=[e['result'] for e in task['events'] if e.get('origin')=='model' and e['tool']=='simulation_result' and e['status']=='succeeded' and isinstance(e.get('result'),dict) and e['result'].get('schema_version')=='vra.agent.design-load-page.v1']
            rows=[r for p in pages for r in p['rows']]; actual={r['locator']['row_id']:r for r in rows}
            wanted=sizing['rows'] if ident=='DL-L1' else [r for r in sizing['rows'] if r['zone_name']=='SPACE5-1' and r['load_type']=='Cooling'] if ident=='DL-L2' else []
            checks={'task_succeeded':task['status']=='succeeded','event_budget':len(task['events'])<=15,'real_model_called':len(receipt['requests'])>before,
                    'requested_rows_read':all(actual.get(r['locator']['row_id'])==r for r in wanted),
                    'no_write_calls':not any(e['tool'] in {'simulation_create','carbon_calculate','counterexample_search'} for e in task['events'])}
            if ident=='DL-L3':checks['stale_rejected']=not pages and (task.get('answer') or {}).get('task_completion')=='incomplete'
            receipt['cases'].append({'id':ident,'seconds':round(time.monotonic()-started,3),'task_status':task['status'],'task_error':task.get('error'),
                'page_offsets':[p['offset'] for p in pages], 'row_ids':sorted(actual),'model_requests':len(receipt['requests'])-before,
                'checks':checks,'automated_pass':all(checks.values()),'task_path':str(path),'task_sha256':core.sha(path),
                'llm_commentary':task.get('llm_commentary'),'answer':task.get('answer'),'manual_review':'pending'})
            save(); print(json.dumps({'case':ident,'variant':variant,'checks':checks}),flush=True)
    receipt['completed']=True
except Exception as exc:
    receipt['harness_error']={'type':type(exc).__name__,'message':str(exc)[:700]}; raise
finally:
    if process.poll() is None: process.terminate()
    process.wait(timeout=30); log.close(); receipt.update(server_stopped=True,server_exit=process.returncode)
    receipt['server_log_sha256']=hashlib.sha256((root/'server.log').read_bytes()).hexdigest(); save()
