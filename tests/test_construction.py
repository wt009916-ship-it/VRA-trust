import copy
import itertools
from fractions import Fraction as F

import pytest
from pydantic import ValidationError
from backend.construction import ScheduleInput, calculate
from test_api import create_project


def plan():
    def task(key,duration,predecessors=()):
        return {'task_id':key,'name':'Synthetic task '+key,'duration_days':duration,'duration_source':'Independent arithmetic case',
            'predecessors':[{'task_id':p,'lag_days':lag,'source':'Independent precedence requirement'} for p,lag in predecessors]}
    return {'name':'Independent construction network','scope':'Synthetic five-task network, not a site programme',
        'calendar':'continuous_elapsed_days','time_origin':'Synthetic kickoff, elapsed day zero',
        'tasks':[task('A',2),task('B',3,[('A',0)]),task('C',4,[('A',0)]),task('D',1,[('B',0),('C',0)]),task('E',1,[('B',0)])]}


def progress():
    return {'as_of_day':4,'source':'Independent status log, synthetic', 'observations':[
        {'task_id':'A','state':'completed','actual_start_day':0,'actual_finish_day':2,'source':'Independent actual time log'},
        {'task_id':'B','state':'in_progress','actual_start_day':2,'remaining_days':1,'source':'Independent remaining duration'},
        {'task_id':'C','state':'in_progress','actual_start_day':2,'remaining_days':3,'source':'Independent remaining duration'},
        {'task_id':'D','state':'not_started','source':'Independent status observation'},
        {'task_id':'E','state':'not_started','source':'Independent status observation'}]}


def test_diamond_independent_manual_answer_and_explicit_forecast():
    b=plan();b['progress']=progress();r=calculate(ScheduleInput(**b));p=r['planned']
    assert p['duration_days']=='7' and set(p['critical_tasks'])=={'A','C','D'}
    rows={x['task_id']:x for x in p['rows']}
    assert (rows['B']['start_day'],rows['B']['finish_day'],rows['B']['total_float_days'],rows['B']['free_float_days'])==('2','5','1','0')
    assert rows['E']['total_float_days']==rows['E']['free_float_days']=='1'
    assert {(e['from'],e['to']) for e in p['critical_dependencies']}=={('A','C'),('C','D')}
    assert r['forecast']['finish_day']=='8' and r['forecast']['finish_variance_days']=='1'
    assert r['site_safety']=='NOT_ASSESSED' and r['resource_leveling']=='NOT_IMPLEMENTED'


def path_oracle(tasks):
    """Independent exhaustive root-to-leaf paths; no production ordering/CPM helper."""
    by_id={t['task_id']:t for t in tasks};successors={key:[] for key in by_id}
    for t in tasks:
        for dep in t['predecessors']:successors[dep['task_id']].append((t['task_id'],F(str(dep['lag_days']))))
    paths=[]
    def visit(key,ids,prefix):
        length=prefix+F(str(by_id[key]['duration_days']));ids=ids+[key]
        if not successors[key]:paths.append((ids,length))
        for nxt,lag in successors[key]:visit(nxt,ids,length+lag)
    for t in tasks:
        if not t['predecessors']:visit(t['task_id'],[],F(0))
    longest=max(length for _,length in paths)
    critical={k for path,length in paths if length==longest for k in path}
    return longest,critical


def test_exhaustive_small_networks_match_independent_rational_paths():
    # All 64 DAGs on four ordered vertices, including disconnected networks and ties.
    possible=list(itertools.combinations(range(4),2))
    for mask in range(1<<len(possible)):
        b=plan();b['tasks']=b['tasks'][:4]
        for i,t in enumerate(b['tasks']):
            t['duration_days']=[0,0.1,0.2,0.3][i];t['predecessors']=[]
        for bit,(a,z) in enumerate(possible):
            if mask & (1<<bit):b['tasks'][z]['predecessors'].append({'task_id':chr(65+a),'lag_days':.1,'source':'Independent enumerated arc'})
        expected,critical=path_oracle(b['tasks'])
        # Shuffled input must not change the dependency calculation.
        b['tasks'].reverse();r=calculate(ScheduleInput(**b))['planned']
        assert F(r['duration_days'])==expected
        assert set(r['critical_tasks'])==critical
        assert all(F(row['free_float_days'])>=0 and F(row['total_float_days'])>=0 for row in r['rows'])


@pytest.mark.parametrize('value',[-1,True,'3',float('inf'),float('nan'),0.0000001])
def test_invalid_or_unresolved_precision_durations(value):
    b=plan();b['tasks'][0]['duration_days']=value
    with pytest.raises(ValidationError):ScheduleInput(**b)


def test_missing_duration_and_unreported_progress_never_become_zero():
    b=plan();b['tasks'][0]['duration_days']=None
    r=calculate(ScheduleInput(**b));assert r['planned'] is None and r['missing_duration_tasks']==['A']
    b=plan();b['progress']=progress();b['progress']['observations'].pop(0)
    r=calculate(ScheduleInput(**b))
    assert r['status']=='incomplete_progress' and r['forecast']['finish_day'] is None
    assert r['forecast']['unverified_actual_dependencies']==[{'task_id':'B','predecessor':'A'},{'task_id':'C','predecessor':'A'}]
    b['progress']=progress();b['progress']['observations'][2]['remaining_days']=None
    r=calculate(ScheduleInput(**b));assert r['forecast']['finish_day'] is None
    assert {'task_id':'D','reason':'predecessor_forecast_missing'} in r['forecast']['missing']


def test_cycle_unknown_duplicates_and_calendar_are_rejected():
    edits=[lambda b:b['tasks'][0]['predecessors'].append({'task_id':'D','lag_days':0,'source':'Independent cycle injection'}),
        lambda b:b['tasks'][0]['predecessors'].append({'task_id':'missing','lag_days':0,'source':'Independent unknown reference'}),
        lambda b:b['tasks'].append(copy.deepcopy(b['tasks'][0])),lambda b:b.update(calendar='working_days'),
        lambda b:b['tasks'][1]['predecessors'].append(copy.deepcopy(b['tasks'][1]['predecessors'][0])),
        lambda b:b['tasks'][1]['predecessors'][0].update(lag_days=-1)]
    for edit in edits:
        b=plan();edit(b)
        with pytest.raises(ValidationError):ScheduleInput(**b)


@pytest.mark.parametrize('edit',[
    lambda b:b['progress']['observations'][0].update(actual_finish_day=5),
    lambda b:b['progress']['observations'][1].update(actual_start_day=1),
    lambda b:b['progress']['observations'][1].update(actual_finish_day=3),
    lambda b:b['progress']['observations'][3].update(actual_start_day=3),
    lambda b:b['progress']['observations'][0].update(actual_start_day=3),
    lambda b:b['progress']['observations'][2].update(remaining_days=0),
    lambda b:b['progress']['observations'].append(copy.deepcopy(b['progress']['observations'][0])),
    lambda b:b['progress']['observations'][0].update(state='in_progress',actual_finish_day=None,remaining_days=1)])
def test_contradictory_progress_rejected(edit):
    b=plan();b['progress']=progress();edit(b)
    with pytest.raises(ValidationError):ScheduleInput(**b)


def test_lags_milestones_zero_span_and_disconnected_tasks():
    b=plan();b['tasks'][1]['predecessors'][0]['lag_days']=2
    r=calculate(ScheduleInput(**b))['planned'];assert r['duration_days']=='8'
    assert set(r['critical_tasks'])=={'A','B','D','E'}
    for task in b['tasks']:
        task['duration_days']=0
        for dep in task['predecessors']:dep['lag_days']=0
    r=calculate(ScheduleInput(**b))['planned'];assert r['duration_days']=='0' and len(r['critical_tasks'])==5


def test_resource_conflict_capacity_unknown_and_half_open_boundaries():
    b=plan();b['resources']=[{'resource_id':'crew','name':'Test crew','capacity':1,'unit':'crew','source':'Independent capacity declaration'}]
    for task in b['tasks']:task['demands']=[{'resource_id':'crew','units':1}]
    r=calculate(ScheduleInput(**b));assert r['status']=='constraints_unresolved'
    conflicts=r['planned']['resources']['conflicts']
    assert conflicts==[{'resource_id':'crew','from_day':'2','until_day':'5','demand':'2','capacity':'1','unit':'crew','tasks':['B','C']},
        {'resource_id':'crew','from_day':'5','until_day':'6','demand':'2','capacity':'1','unit':'crew','tasks':['C','E']}]
    b['tasks']=b['tasks'][:2];r=calculate(ScheduleInput(**b))
    assert r['planned']['resources']['conflicts']==[]  # A ends exactly when B starts.
    b['resources'][0]['capacity']=None
    assert calculate(ScheduleInput(**b))['planned']['resources']['status']=='unknown'
    b['resources'][0]['capacity']=0
    assert calculate(ScheduleInput(**b))['planned']['resources']['status']=='conflict'


def test_resource_precision_cannot_silently_hide_excess_demand():
    b=plan();b['resources']=[{'resource_id':'crew','name':'Test crew','capacity':1,'unit':'crew','source':'Independent capacity declaration'}]
    b['tasks'][1]['demands']=[{'resource_id':'crew','units':1}]
    b['tasks'][2]['demands']=[{'resource_id':'crew','units':1e-100}]
    # Refuse unresolvable input precision instead of silently rounding excess away.
    with pytest.raises(ValidationError):ScheduleInput(**b)
    b['tasks'][2]['demands'][0]['units']=.000001
    r=calculate(ScheduleInput(**b))
    assert r['planned']['resources']['conflicts'][0]['demand']=='1.000001'


def test_contract_capacity_limits_and_decimal_ties():
    b=plan();b['tasks']=b['tasks'][:1]
    b['tasks']=[dict(copy.deepcopy(b['tasks'][0]),task_id=str(i),duration_days=3650,predecessors=[] if i==0 else [{'task_id':str(i-1),'lag_days':3650,'source':'Independent capacity test'}]) for i in range(250)]
    assert calculate(ScheduleInput(**b))['planned']['duration_days']==str(3650*499)
    b['tasks'].append(dict(copy.deepcopy(b['tasks'][-1]),task_id='250'))
    with pytest.raises(ValidationError):ScheduleInput(**b)


def test_api_report_source_withdrawal_and_original_retained(client):
    pid=create_project(client)['project_id'];base='/api/projects/'+pid;domain=client.app.state.domain
    file=client.post(base+'/files',files={'file':('plan.json',b'{"synthetic":true}')}).json()
    ev=client.post(base+'/evidence',json={'type':'manual_input','name':'Independent schedule source','source_file':file['file_id'],
        'source_locator':'all tasks','authority':'Auditor','permission':'synthetic test','acquisition_method':'test','responsible_person':'auditor','status':'IMPORTED'}).json()
    b=plan();b['import_file_id']=file['file_id'];b['evidence_ids']=[ev['evidence_id']]
    response=client.post(base+'/schedules',json=b);assert response.status_code==201,response.text
    record=response.json();url=base+'/schedules/'+record['schedule_id']
    assert client.get(url).json()['result']['planned']['duration_days']=='7'
    assert '7 连续经过日' in client.get(url+'/report.html').text
    assert client.get(base+'/schedules').json()[0]['schedule_id']==record['schedule_id']
    client.patch(base+'/evidence/'+ev['evidence_id'],json={'expected_revision':1,'review_state':'rejected','responsible_person':'auditor','review_note':'Withdraw synthetic source'})
    assert client.get(url).json()['result'] is None and client.post(base+'/schedules',json=b).status_code==409
    assert domain.store.get('schedule',record['schedule_id'])['result']['planned']['duration_days']=='7'
    b['evidence_ids']=[];fresh=client.post(base+'/schedules',json=b).json()
    _,path=domain.file_record(pid,file['file_id']);path.write_bytes(b'changed')
    assert client.get(base+'/schedules/'+fresh['schedule_id']).json()['status']=='stale'


def test_api_auth_project_integrity_and_agent_guards(client):
    from backend.agent import ToolRefusal
    pid=create_project(client)['project_id'];base='/api/projects/'+pid;b=plan()
    b['name']='<script>unsafe</script>';r=client.post(base+'/schedules',json=b).json();sid=r['schedule_id']
    html=client.get(base+'/schedules/'+sid+'/report.html').text
    assert '<script>' not in html and '&lt;script&gt;' in html
    other=create_project(client)['project_id']
    assert client.get('/api/projects/'+other+'/schedules/'+sid).status_code==409
    agent=client.app.state.agent
    assert agent.call(pid,'schedule_read',{'schedule_id':sid},False)['result']['planned']['duration_days']=='7'
    assert agent.call(pid,'schedule_list',{},False)[0]['schedule_id']==sid
    with pytest.raises(ToolRefusal):agent.call(other,'schedule_read',{'schedule_id':sid},False)
    with pytest.raises(ValueError):agent.call(pid,'schedule_read',{'schedule_id':sid,'duration_days':1},False)
    b['tasks'][0]['duration_days']=-1
    assert client.post(base+'/schedule-validation',json=b).status_code==422
    client.headers.pop('X-CSRF-Token');assert client.post(base+'/schedules',json=plan()).status_code==403
    client.cookies.clear();assert client.get(base+'/schedules').status_code==401


def test_foreign_import_project_change_code_change_and_record_integrity(client,monkeypatch):
    from backend import construction
    pid=create_project(client)['project_id'];other=create_project(client)['project_id'];base='/api/projects/'+pid
    file=client.post('/api/projects/'+other+'/files',files={'file':('foreign.json',b'{}')}).json()
    b=plan();b['import_file_id']=file['file_id'];assert client.post(base+'/schedules',json=b).status_code==409
    r=client.post(base+'/schedules',json=plan()).json();url=base+'/schedules/'+r['schedule_id']
    store=client.app.state.domain.store;project=store.get('project',pid);store.put('project',project,project['revision'])
    assert client.get(url).json()['status']=='stale'
    r=client.post(base+'/schedules',json=plan()).json();url=base+'/schedules/'+r['schedule_id']
    with monkeypatch.context() as patch:
        patch.setattr(construction.core,'sha',lambda path:'different calculator hash')
        assert client.get(url).json()['result'] is None
    obj=store.get('schedule',r['schedule_id']);obj['result']['planned']['duration_days']='0';store.put('schedule',obj,obj['revision'])
    response=client.get(url);assert response.status_code==409 and 'integrity' in response.text
