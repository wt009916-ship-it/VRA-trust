"""Real services and independent inputs; scripted tool messages are not model evidence."""
import copy
from fractions import Fraction as F

import pytest

from backend import agent_calculations as calculations
from backend.agent import Chat
from backend.agent_semantics import Delivery, check, facts, inspection
from backend.agent_inspections import INSPECTIONS
from test_agent_calculations import batch
from test_api import create_project
from test_engineering import beam
from test_operations import contract


def inputs(client,pid,kind):
    if kind=='engineering':
        b=beam();b.update(name='Independent 5m beam',span=5.,width=250.,depth=400.,elastic_modulus=32.)
        b['loads'][0].update(magnitude=6.,end=5.);return b
    if kind=='schedule':
        tasks=[]
        for key,duration,deps in [('A',2.5,[]),('B',4.25,[('A',.5)]),('C',1.25,[('A',0.)]),('D',.75,[('B',0.),('C',0.)])]:
            tasks.append(dict(task_id=key,name='Task '+key,duration_days=duration,duration_source='Independent synthetic input',
                predecessors=[dict(task_id=p,lag_days=lag,source='Independent declared precedence') for p,lag in deps]))
        return dict(name='Independent lagged diamond',scope='Synthetic four-task network, no site approval',calendar='continuous_elapsed_days',time_origin='Independent elapsed day zero',tasks=tasks)
    b=contract();b.update(name='Independent temperature window',channels=[dict(channel_id='t',column='t',name='Temperature',unit='degC',source='Independent synthetic unit')],
        rules=[dict(rule_id='hot',name='Declared upper band',kind='range',channel_id='t',unit='degC',upper=22.,minimum_duration_seconds=60.,source='Synthetic threshold, not a diagnosis')])
    text='time,t\n'+''.join(f'2026-02-02T00:0{i}:00Z,{v}\n' for i,v in enumerate([20,23,24,21,25,26,20]))
    response=client.post(f'/api/projects/{pid}/files',files={'file':('independent.csv',text.encode())});assert response.status_code==201
    b['file_id']=response.json()['file_id'];return b


def make_plan(client,pid,kind):return {'plan_key':'new_'+kind,'kind':kind,'input':inputs(client,pid,kind)}


EXPECTED={'engineering':[('left_reaction_n','15000','N','static_load_case'),('max_abs_moment_nm','18750','N m','static_load_case')],
          'schedule':[('planned_duration_days','8','day','elapsed_days')],
          'operation':[('sample_count','7','count','observed_window'),('rule_event_sum','2','count','observed_window')]}


def driver(a,monkeypatch,plans):
    turns=[]
    def complete(messages,tools):
        turns.append(copy.deepcopy(tools))
        if len(turns)==1:return batch([('calculation_execute',{'plan_key':p['plan_key']}) for p in plans])
        records=[a.store.list(p['kind'])[0] for p in plans]
        if len(turns)==2:return batch([(inspection(p['kind']).read_tool,{inspection(p['kind']).argument:r[inspection(p['kind']).record_key]}) for p,r in zip(plans,records)])
        return batch([('professional_deliver',{'delivery':{'kind':p['kind'],'record_id':r[inspection(p['kind']).record_key],'record_hash':r['hash'],
            'statements':[dict(fact=k,value=v,unit=u,period=period,study_years=None,area_m2=None) for k,v,u,period in EXPECTED[p['kind']]],'finish':True}}) for p,r in zip(plans,records)])
    monkeypatch.setattr(a.gateway,'public',lambda:{'enabled':True,'key_configured':True})
    monkeypatch.setattr(a.gateway,'complete',complete);return turns


@pytest.mark.parametrize('kind',['engineering','schedule','operation'])
def test_actual_plan_save_deliver_report_and_independent_answers(client,monkeypatch,kind):
    pid=create_project(client)['project_id'];a=client.app.state.agent;p=make_plan(client,pid,kind)
    driver(a,monkeypatch,[p]);t=a.start(pid,Chat(message='Actually calculate and deliver',mode='provider',allow_compute=True,calculation_plans=[p]),background=False)
    assert t['status']=='succeeded',t.get('error')
    assert t['calculation_progress'][0]['state']=='verified' and len(a.store.list(kind,pid))==1
    artifact=t['answer']['artifacts'][0];r=artifact['result'];assert not t['answer']['can_recommend']
    assert client.get(artifact['report_path']).status_code==200
    if kind=='engineering':
        inertia=F(1,4)*F(2,5)**3/12
        independent=F(5)*6000*5**4/(384*32000000000*inertia)
        assert r['metrics']['max_deflection_m']==pytest.approx(float(independent),rel=1e-12)
        assert r['structural_safety']=='NOT_ASSESSED'
    elif kind=='schedule':
        assert r['planned']['critical_tasks']==['A','B','D']
        assert r['planned']['duration_days']==str(F(5,2)+F(1,2)+F(17,4)+F(3,4))
        assert r['site_safety']=='NOT_ASSESSED'
    else:
        assert [(x['first_line'],x['last_line'],x['observed_span_seconds']) for x in r['rules'][0]['events']]==[(3,4,60.),(6,7,60.)]
        assert r['diagnosis']=='NOT_CONFIRMED' and r['control_action']=='NONE'


@pytest.mark.parametrize('kind',['engineering','schedule','operation'])
def test_readonly_objective_current_record_and_cross_project_refusal(client,kind):
    pid=create_project(client)['project_id'];a=client.app.state.agent;p=make_plan(client,pid,kind)
    body=Chat(message='typed input',mode='provider',allow_compute=True,calculation_plans=[p]);plan=body.calculation_plans[0]
    spec=inspection(kind);r=spec.service(a.domain).save(pid,plan.input)
    objective=next(k for k,v in INSPECTIONS.items() if v.kind==kind)
    t=a.start(pid,Chat(message='Read current result',objective=objective),background=False)
    assert t['answer']['artifact']['record_id']==r[spec.record_key] and t['answer']['task_completion']=='verified'
    other=create_project(client)['project_id']
    with pytest.raises(ValueError,match='Cross-project'):a.call(other,spec.read_tool,{spec.argument:r[spec.record_key]},False)
    project=a.store.get('project',pid);project['name']='Updated declaration';a.store.put('project',project,project['revision'])
    saved=a.store.get('agent',t['agent_id']);assert a.view(pid,t['agent_id'])['answer']['artifact']['result'] is None
    assert a.store.get('agent',t['agent_id'])==saved


@pytest.mark.parametrize('kind',['engineering','schedule','operation'])
def test_period_units_and_invented_certification_fact_rejected(client,kind):
    pid=create_project(client)['project_id'];a=client.app.state.agent;p=make_plan(client,pid,kind)
    plan=Chat(message='input',mode='provider',allow_compute=True,calculation_plans=[p]).calculation_plans[0]
    spec=inspection(kind);r=spec.service(a.domain).save(pid,plan.input);f=facts(r,kind)[0]
    base={k:f[k] for k in ('fact','value','unit','period','study_years','area_m2')}
    for edit in [{'unit':'kWh/year'},{'period':'study_period','study_years':1},{'fact':'certified_safe','value':'1'}]:
        d=Delivery(kind=kind,record_id=r[spec.record_key],record_hash=r['hash'],statements=[base|edit])
        with pytest.raises(ValueError):check(r,d)


def test_operation_file_binding_and_cross_project_plan_rejected(client):
    pid=create_project(client)['project_id'];a=client.app.state.agent;p=make_plan(client,pid,'operation')
    plans=Chat(message='input',mode='provider',allow_compute=True,calculation_plans=[p]).calculation_plans
    other=create_project(client)['project_id']
    with pytest.raises(ValueError):calculations.snapshot(a.domain,other,plans)
    frozen=calculations.snapshot(a.domain,pid,plans);_,path=a.domain.file_record(pid,p['input']['file_id'])
    path.write_text('changed source',encoding='utf-8')
    with pytest.raises(ValueError):calculations.execute(a.domain,pid,p['plan_key'],plans,frozen)
    assert not a.store.list('operation',pid)


def test_outside_beam_model_does_not_offer_deliverable_engineering_numbers(client):
    pid=create_project(client)['project_id'];a=client.app.state.agent;p=make_plan(client,pid,'engineering');p['input']['depth']=1000.
    plan=Chat(message='input',mode='provider',allow_compute=True,calculation_plans=[p]).calculation_plans[0]
    spec=inspection('engineering');r=spec.service(a.domain).save(pid,plan.input)
    assert r['status']=='outside_model_screen' and facts(r,'engineering')==[] and not spec.artifact(r)['verified']


@pytest.mark.parametrize('kind',['engineering','schedule'])
def test_missing_parameters_remain_null_and_unfinished(client,kind):
    pid=create_project(client)['project_id'];a=client.app.state.agent;p=make_plan(client,pid,kind)
    if kind=='engineering':p['input']['elastic_modulus']=None
    else:p['input']['tasks'][1]['duration_days']=None
    plan=Chat(message='input',mode='provider',allow_compute=True,calculation_plans=[p]).calculation_plans[0]
    spec=inspection(kind);r=spec.service(a.domain).save(pid,plan.input)
    assert r['status']=='incomplete' and all(f['value'] is None for f in facts(r,kind))
    assert not spec.artifact(r)['verified']


def test_schedule_resource_conflict_is_not_a_complete_plan(client):
    pid=create_project(client)['project_id'];a=client.app.state.agent;p=make_plan(client,pid,'schedule')
    p['input']['resources']=[dict(resource_id='crew',name='One declared crew',capacity=1.,unit='crew',source='Independent capacity declaration')]
    for i in (1,2):p['input']['tasks'][i]['demands']=[dict(resource_id='crew',units=1.)]
    plan=Chat(message='input',mode='provider',allow_compute=True,calculation_plans=[p]).calculation_plans[0]
    spec=inspection('schedule');r=spec.service(a.domain).save(pid,plan.input)
    assert r['status']=='constraints_unresolved' and not spec.artifact(r)['verified']
    assert facts(r,'schedule')[0]['value']=='8'  # Valid arithmetic does not resolve resource conflict.


def test_overlapping_operation_events_are_rule_sum_not_distinct_faults(client):
    pid=create_project(client)['project_id'];a=client.app.state.agent;p=make_plan(client,pid,'operation')
    p['input']['rules'].append(p['input']['rules'][0]|{'rule_id':'overlap'})
    plan=Chat(message='input',mode='provider',allow_compute=True,calculation_plans=[p]).calculation_plans[0]
    r=inspection('operation').service(a.domain).save(pid,plan.input)
    f=next(f for f in facts(r,'operation') if f['fact']=='rule_event_sum')
    assert f['value']=='4' and '非故障数' in f['label'] and f['source_path'].startswith('derived:sum(')
    assert r['result']['rules'][0]['events']==r['result']['rules'][1]['events']


def test_missing_operation_sample_is_not_normal_health(client):
    pid=create_project(client)['project_id'];a=client.app.state.agent;p=make_plan(client,pid,'operation')
    _,source=a.domain.file_record(pid,p['input']['file_id']);text=source.read_text(encoding='utf-8').replace('00:01:00Z,23','00:01:00Z,')
    uploaded=client.post(f'/api/projects/{pid}/files',files={'file':('missing.csv',text.encode())});assert uploaded.status_code==201
    p['input']['file_id']=uploaded.json()['file_id'];plan=Chat(message='input',mode='provider',allow_compute=True,calculation_plans=[p]).calculation_plans[0]
    spec=inspection('operation');r=spec.service(a.domain).save(pid,plan.input);f={f['fact']:f for f in facts(r,'operation')}
    assert f['cell_issue_count']['value']=='1' and f['rule_unknown_sample_sum']['value']=='1'
    assert not spec.artifact(r)['verified'] and r['result']['diagnosis']=='NOT_CONFIRMED'


def test_two_different_new_plans_remain_within_existing_event_budget(client,monkeypatch):
    pid=create_project(client)['project_id'];a=client.app.state.agent;plans=[make_plan(client,pid,k) for k in ('engineering','operation')]
    driver(a,monkeypatch,plans);t=a.start(pid,Chat(message='Calculate both',mode='provider',allow_compute=True,calculation_plans=plans),background=False)
    assert t['status']=='succeeded',t.get('error')
    assert len(t['events'])<=15 and len(t['answer']['artifacts'])==2
    assert all(r['state']=='verified' for r in t['calculation_progress'])
