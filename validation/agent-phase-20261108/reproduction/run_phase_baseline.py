"""Fixed 24-task application comparison. Gold never enters model messages."""
import copy
from decimal import Decimal
from fractions import Fraction as F
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import uuid

REPO = Path('C:/Users/18483/AppData/Local/Temp/vra-drawing-components-20261108')
BASE = Path(__file__).resolve().parent
OUT = Path(tempfile.gettempdir()) / 'vra-phase-baseline-20261108'
FIXTURE = BASE / 'phase-intent-frozen-20261108.json'
FROZEN_SHA = 'b007838890a74dd8df0e2728b4cf8eae20616108c1612bcfa3f3fe31531c7753'
sys.path.insert(0, str(REPO))
from backend.private_storage import private_mkdir


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def seeds():
    thermal = dict(name='New independent wall', rsi_m2k_w=.11, rse_m2k_w=.05,
        surface_basis='Explicit synthetic films', application='Homogeneous test layers only',
        layers=[dict(name=n, thickness=d, thickness_unit=u, conductivity=k,
            conductivity_unit='W/(m K)', source='Independent synthetic data',
            correction_basis='Explicit unity factor')
            for n,d,u,k in [('core',180,'mm',.9), ('insulation',4.5,'cm',.045)]])
    stage_inputs = [('production',1.6,'t',.5,'kg','whole_period'),
        ('transport',140,'tkm',.07,'tkm','whole_period'),
        ('construction',90,'kWh',.4,'kWh','whole_period'),
        ('operation',320,'kWh',.35,'kWh','annual'),
        ('end_of_life',25,'kg',.08,'kg','whole_period')]
    lifecycle = dict(name='New all-five-stage synthetic inventory', area_m2=800,
        study_years=15, region='US-CO', method='Synthetic GWP arithmetic',
        functional_unit='800 declared square metres over fifteen years',
        boundaries=[dict(stage=s,included=True,reason='Explicit synthetic scope') for s,*_ in stage_inputs],
        activities=[dict(activity_id=s,name=s,stage=s,quantity=q,unit=u,period=p,
            source='Independent synthetic activity',factor=dict(factor_id=s+'-fixed',value=v,
                denominator=d,stage=s,source='Synthetic test factor only',publisher='Application comparison',
                version='fixed-next-20261108',year=2026,region='*',method='Synthetic GWP arithmetic'))
            for s,q,u,v,d,p in stage_inputs])
    engineering = dict(name='New cantilever',support='cantilever',span=3,span_unit='m',
        width=200,depth=300,section_unit='mm',elastic_modulus=30,modulus_unit='GPa',
        geometry_source='Synthetic geometry',material_source='Synthetic modulus',
        support_basis='Ideal fixed left and free right',analysis_basis='Linear elastic small deflection only',
        loads=[dict(type='point',name='Free-end load',magnitude=4,unit='kN',position=3,
            position_unit='m',source='Synthetic point load, excludes self weight')])
    tasks=[dict(task_id=k,name='Task '+k,duration_days=d,duration_source='Synthetic duration',
        predecessors=[dict(task_id=p,lag_days=0,source='Synthetic precedence') for p in deps])
        for k,d,deps in [('A',3,[]),('B',4,['A']),('C',2,['A']),('D',1,['B','C'])]]
    schedule=dict(name='New forecast network',scope='Synthetic network, not site instructions',
        calendar='continuous_elapsed_days',time_origin='Synthetic day zero',tasks=tasks,
        progress=dict(as_of_day=4,source='Synthetic progress',observations=[
            dict(task_id=k,state=s,source='Synthetic observation',**v) for k,s,v in [
                ('A','completed',dict(actual_start_day=0,actual_finish_day=3)),
                ('B','in_progress',dict(actual_start_day=3,remaining_days=5)),
                ('C','in_progress',dict(actual_start_day=3,remaining_days=1)),
                ('D','not_started',{})]]))
    csv='time,t\n'+''.join(f'2026-06-06T00:{m:02}:00Z,{v}\n'
        for m,v in [(0,20),(1,24),(2,25),(3,''),(6,27),(7,20)])
    operation=dict(name='New quality window',file_id='{{file}}',equipment='Synthetic FCU',
        data_nature='synthetic',source='New independent synthetic CSV',time_column='time',
        time_format='iso8601',clock_basis='offset_aware',clock_source='Explicit UTC',
        expected_interval_seconds=60,maximum_gap_seconds=90,
        channels=[dict(channel_id='t',column='t',name='Temperature',unit='degC',source='Declared synthetic units')],
        rules=[dict(rule_id='hot',name='Upper band',kind='range',channel_id='t',unit='degC',
            upper=22,minimum_duration_seconds=60,source='Synthetic threshold, not a fault diagnosis')])
    return dict(thermal=thermal,lifecycle=lifecycle,engineering=engineering,
        schedule=schedule,operation=operation,csv=csv)


def oracles():
    # Arithmetic independent of production normalization/calculation/formatting.
    r=F(18,100)/F(9,10)+F(45,1000)/F(45,1000)+F(16,100)
    carbon=dict(production=F(16,10)*1000*F(1,2),transport=140*F(7,100),
        construction=90*F(4,10),operation=320*F(35,100)*15,end_of_life=25*F(8,100))
    total=sum(carbon.values())
    inertia=F(2,10)*F(3,10)**3/12
    values=dict(thermal=dict(total_resistance_m2k_w=r,layer_resistance_m2k_w=r-F(16,100),u_w_m2k=1/r),
        lifecycle={'boundary_total_kgco2e':total,'kgco2e_m2_over_study_period':total/800,
            **{'stage.'+k:v for k,v in carbon.items()}},
        engineering=dict(left_reaction_n=4000,left_reaction_moment_nm=12000,
            max_abs_moment_nm=12000,max_deflection_m=4000*F(3)**3/(3*30000000000*inertia)),
        # A finishes3; B finishes7; C finishes5; D finishes8. At4, B remains5 => D ends10.
        schedule=dict(planned_duration_days=8,forecast_as_of_day=4,forecast_finish_day=10,forecast_finish_variance_days=2),
        # Six rows; one blank; 3->6min gap; one >=60s hot event at1->2; minute6 isolated.
        operation=dict(sample_count=6,cell_issue_count=1,gap_count=1,rule_event_sum=1,rule_unknown_sample_sum=1))
    return {k:{f:str(Decimal(F(v).numerator)/Decimal(F(v).denominator)) for f,v in vs.items()} for k,vs in values.items()}


def create_source(client, kind, data):
    from backend.agent import Chat
    from backend.agent_semantics import inspection
    r=client.post('/api/projects',json=dict(name='Independent '+kind,
        building=dict(use='office',location='Synthetic comparison',region='US-CO',area_m2=800)))
    assert r.status_code==201, r.text
    pid=r.json()['project_id'];body=copy.deepcopy(data[kind])
    if kind in {'thermal','lifecycle'}:
        r=client.post(f'/api/projects/{pid}/{kind}',json=body)
        assert r.status_code==201, r.text
        return pid,r.json()
    if kind=='operation':
        upload=client.post(f'/api/projects/{pid}/files',files={'file':('new-window.csv',data['csv'].encode())})
        assert upload.status_code==201,upload.text
        body['file_id']=upload.json()['file_id']
    plan=Chat(message='Synthetic input',mode='provider',allow_compute=True,
        calculation_plans=[dict(plan_key='fixture',kind=kind,input=body)]).calculation_plans[0]
    return pid,inspection(kind).service(client.app.state.agent.domain).save(pid,plan.input)


def near(actual, expected):
    return actual is not None and abs(Decimal(actual)-Decimal(expected)) <= max(Decimal('1e-10'),abs(Decimal(expected))*Decimal('1e-11'))


def source_check(record,kind,expected):
    from backend.agent_semantics import facts
    actual={f['fact']:f for f in facts(record,kind)}
    checks={k:k in actual and near(actual[k]['value'],v) for k,v in expected.items()}
    assert all(checks.values()), {'kind':kind,'checks':checks,'actual':actual}
    return actual


def main():
    mode=sys.argv[1];assert mode in {'prepare','4b','9b'}
    assert sha(FIXTURE)==FROZEN_SHA
    cases=json.loads(FIXTURE.read_text(encoding='utf-8'))['cases']
    if not OUT.exists():
        private_mkdir(OUT)
    source_hashes={p.relative_to(REPO).as_posix():sha(p) for p in sorted((REPO/'backend').glob('*.py'))}
    manifest=dict(fixture_sha256=FROZEN_SHA,application_commit='c7cbf76 baseline',
        source_hashes=source_hashes,seeds=seeds(),oracles=oracles(),
        method='One fixed application run per question per model. Existing bounded tool recovery is retained. No gold sent to model.',
        gate='Candidate must improve supported-task strict end-to-end count by >=2 with no previously-passing supported case regressed. Compatibility/security must pass. Unsupported I07/I08 stay in denominator24 and are reviewed separately; they cannot earn success for a tool error.',
        semantics='Developer-designed single-record contrast tasks, not third-party blind testing or broad Agent certification.',
        parameters=dict(context=8192,max_tokens=1400,temperature=0,enable_thinking=False,app_event_limit=15,app_model_round_limit=5))
    frozen=OUT/'frozen-application.json'
    if mode=='prepare':
        assert not frozen.exists(),'Already frozen; do not replace'
        write(frozen,manifest)
    else:
        assert json.loads(frozen.read_text(encoding='utf-8'))==manifest,'Frozen inputs/source changed'
    resumed = mode == '4b' and (OUT/'recovered-I01.json').exists()
    label=mode+'-continuation' if resumed else mode
    out=OUT/label
    if resumed and out.exists():
        out=OUT/(label+'-2')
    out.mkdir(exist_ok=False)
    root=private_mkdir(Path(tempfile.gettempdir())/('vra-intent-api-'+uuid.uuid4().hex))
    os.environ.update(VRA_DATA_DIR=str(root/'api'),VRA_LOCAL_MODEL_TOKEN=secrets.token_urlsafe(32),
        ENERGYPLUS_EXE='F:/EnergyPlusV9-0-1/energyplus.exe')
    from fastapi.testclient import TestClient
    from backend.api import app
    from backend.agent import Chat
    from backend.local_model import LocalModelGateway,LocalModelSettings
    if mode=='prepare':
        with TestClient(app) as client:
            r=client.post('/api/auth/register',json=dict(username='isolated_intent',display_name='Synthetic',password=secrets.token_urlsafe(32)))
            assert r.status_code==200;client.headers['X-CSRF-Token']=r.json()['csrf_token']
            rows={}
            for kind,expected in manifest['oracles'].items():
                pid,record=create_source(client,kind,manifest['seeds'])
                rows[kind]=dict(project_id=pid,record=record,facts=source_check(record,kind,expected))
            write(out/'source-check.json',dict(frozen_sha256=sha(frozen),rows=rows,model_called=False))
            print(json.dumps({'source_check':list(rows),'model_calls':0}),flush=True)
        return
    runtime=json.loads((BASE.parents[1]/'vra-trust/validation/local-model-20261106/prepared-runtime.json').read_text())
    cache=Path(runtime['root']);exe=cache/'runtime/llama-server.exe'
    for entry in runtime['extracted']:assert sha(cache/entry['path'])==entry['sha256']
    if mode=='4b':
        model=cache/'models/Qwen3-4B-Q4_K_M.gguf';model_hash=runtime['verified'][2]['sha256']
    else:
        model=Path(tempfile.gettempdir())/'vra-qwen35-9b-20261108/Qwen3.5-9B-Q4_K_M.gguf'
        model_hash='03b74727a860a56338e042c4420bb3f04b2fec5734175f4cb9fa853daf52b7e8'
    assert sha(model)==model_hash
    port=18773;alias='vra-intent-pair'
    with socket.socket() as sock:sock.bind(('127.0.0.1',port))
    env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','TEMP','TMP','COMSPEC','SYSTEMDRIVE'}}
    env.update(PATH=str(exe.parent)+os.pathsep+str(Path(os.environ['SystemRoot'])/'System32'),LLAMA_API_KEY=os.environ['VRA_LOCAL_MODEL_TOKEN'])
    args=[str(exe),'-m',str(model),'--host','127.0.0.1','--port',str(port),'--alias',alias,
        '-c','8192','-np','1','-t','4','-ngl','99','--fit','off','--cache-ram','0',
        '--no-context-shift','--offline','--no-webui','--no-agent','--no-webui-mcp-proxy','--no-slots',
        '--jinja','--reasoning','off','--timeout','120']
    receipt=dict(variant=mode,frozen_sha256=sha(frozen),model_sha256=model_hash,runtime_commit=runtime['runtime_commit'],
        source_hashes=source_hashes,server_arguments=args,training=False,formal_prototype_touched=False,cases=[],
        runtime_root=str(root),resumed_without_repeating_I01=resumed)
    save=lambda:write(out/'results.json',receipt)
    log=(out/'server.log').open('xb');started=time.monotonic()
    proc=subprocess.Popen(args,cwd=exe.parent,env=env,stdin=subprocess.DEVNULL,
        stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
    receipt['server_pid']=proc.pid;save()
    original=LocalModelGateway.complete;capture=dict(case=None,index=0)
    def observed(self,messages,tools,**kwargs):
        began=time.monotonic();entry=dict(case=capture['case'],messages=copy.deepcopy(messages),tools=copy.deepcopy(tools))
        try:
            result=original(self,messages,tools,**kwargs);entry['response']=result;return result
        except Exception as exc:
            entry['error_type']=type(exc).__name__;raise
        finally:
            entry['seconds']=round(time.monotonic()-began,3);capture['index']+=1
            write(out/f"model-call-{capture['index']:03}.json",entry)
    LocalModelGateway.complete=observed
    try:
        import httpx
        with httpx.Client(timeout=5,trust_env=False) as net:
            for _ in range(120):
                assert proc.poll() is None,'Model exited before readiness'
                try:
                    if net.get(f'http://127.0.0.1:{port}/health').status_code==200:break
                except httpx.HTTPError:pass
                time.sleep(1)
            else:raise RuntimeError('Model startup exceeded120seconds')
            receipt['startup_seconds']=round(time.monotonic()-started,3)
            command='Get-NetTCPConnection -State Listen | Where-Object OwningProcess -eq '+str(proc.pid)+' | Select-Object LocalAddress,LocalPort | ConvertTo-Json -Compress'
            listeners=json.loads(subprocess.check_output(['powershell.exe','-NoProfile','-NonInteractive','-Command',command],timeout=30,creationflags=subprocess.CREATE_NO_WINDOW))
            listeners=[listeners] if isinstance(listeners,dict) else listeners
            assert listeners and all(x['LocalAddress']=='127.0.0.1' and x['LocalPort']==port for x in listeners)
            receipt['loopback_verified']=True
            assert net.post(f'http://127.0.0.1:{port}/v1/chat/completions',json={'model':alias,'messages':[]}).status_code==401
            receipt['unauthenticated_status']=401;save()
        with TestClient(app) as client:
            r=client.post('/api/auth/register',json=dict(username='isolated_intent',display_name='Synthetic',password=secrets.token_urlsafe(32)))
            assert r.status_code==200;client.headers['X-CSRF-Token']=r.json()['csrf_token']
            app.state.agent.local_model.save(LocalModelSettings(enabled=True,port=port,model=alias))
            for case in cases:
                capture['case']=case['id'];calls_before=capture['index'];began=time.monotonic()
                kind=case['kind'];recovered=resumed and case['id']=='I01'
                if recovered:
                    saved=json.loads((OUT/'recovered-I01.json').read_text(encoding='utf-8'))
                    record=saved['source'];t=saved['task'];rid=record[kind+'_id']
                    record={**record,'status':next(a['status'] for a in t['answer']['artifacts'] if a['record_id']==rid)}
                else:
                    pid,record=create_source(client,kind,manifest['seeds']);rid=record[kind+'_id']
                    request=dict(request_key=kind,kind=kind,purpose='results',record_id=rid)
                    t=app.state.agent.start(pid,Chat(message=case['question'],mode='local_model',read_requests=[request]),background=False)
                    t=app.state.agent.view(pid,t['agent_id'])
                write(out/(case['id']+'-raw.json'),dict(case_id=case['id'],source=record,task=t,recovered=recovered))
                source_facts=source_check(record,kind,manifest['oracles'][kind])
                answer=t.get('answer') or {};plan=answer.get('output_plan') or t.get('output_plan') or {}
                items=plan.get('items',[]);selected=items[0] if len(items)==1 else {}
                facts=case['expected_fact_keys'];topics=case['expected_explanation_topics']
                statements=[s for r in answer.get('checked_statements',[]) for s in r['facts']]
                selected_fields=set(selected.get('fact_keys',[]));selected_topics=set(selected.get('explanation_topics',[]))
                delivered={s['fact']:s for s in statements}
                output=answer.get('requested_outputs',[])
                checks=dict(task_succeeded=t['status']=='succeeded',one_plan=len(items)==1,
                    exact_fields=selected_fields==set(facts),exact_topics=selected_topics==set(topics),
                    exact_delivered_fields=set(delivered)==set(facts),
                    delivered_values=all(k in delivered and near(delivered[k]['value'],manifest['oracles'][kind][k]) for k in facts),
                    delivered_dimensions=all(k in delivered and all(delivered[k][x]==source_facts[k][x] for x in ['unit','period','study_years','area_m2']) for k in facts),
                    current_source=bool(answer.get('checked_statements')) and all(r['record_id']==rid for r in answer.get('checked_statements',[])) and any(a.get('record_id')==rid and a.get('record_hash')==record['hash'] for a in answer.get('artifacts',[])) and all(v['passed'] for v in answer.get('verification',[])),
                    requested_explanations=bool(output) and {e['topic'] for o in output for e in o.get('explanations',[])}==set(topics),
                    no_engineering_overclaim=answer.get('can_recommend') is False and plan.get('intent_verified') is False,
                    no_new_calculation=not any(e['tool']=='calculation_execute' for e in t['events']),bounded_events=len(t['events'])<=15)
                # Unsupported intents cannot pass through an empty plan/error. Manual review retained.
                supported=case['disposition']=='supported'
                row=dict(id=case['id'],kind=kind,disposition=case['disposition'],source=record,
                    task=t,checks=checks,semantic_selection_pass=bool(items) and checks['exact_fields'] and checks['exact_topics'],
                    strict_pass=supported and all(checks.values()),unsupported_review='pending' if not supported else None,
                    model_calls=1 if recovered else capture['index']-calls_before,
                    seconds=None if recovered else round(time.monotonic()-began,3),recovered=recovered)
                receipt['cases'].append(row);save()
                print(json.dumps({k:row[k] for k in ['id','semantic_selection_pass','strict_pass','model_calls','seconds']}),flush=True)
        receipt['completed']=True
    except Exception as exc:
        receipt['harness_error']=dict(type=type(exc).__name__,message=str(exc)[:500]);raise
    finally:
        LocalModelGateway.complete=original
        if proc.poll() is None:proc.terminate()
        try:proc.wait(timeout=30)
        except subprocess.TimeoutExpired:proc.kill();proc.wait(timeout=10)
        log.close();receipt['server_stopped']=True;receipt['server_exit']=proc.returncode;save()


if __name__=='__main__':main()
