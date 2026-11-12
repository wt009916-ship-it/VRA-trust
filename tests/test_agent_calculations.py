"""Protocol fault injection plus real calculator persistence, not model intelligence."""
import copy
import json
from decimal import Decimal, ROUND_HALF_UP, ROUND_CEILING
from fractions import Fraction

import pytest

from backend.agent import Chat
from backend.agent_semantics import inspection
from test_api import create_project
from test_agent_professional import thermal_input, lifecycle_input
from test_agent_artifacts import cost_input
from test_agent_contract import scripted, call, DONE


def plan(kind='thermal', key='a'):
    return {'plan_key': key, 'kind': kind, 'input': {'thermal': thermal_input, 'lifecycle': lifecycle_input, 'cost': cost_input}[kind]()}


def chat(plans=None, **kw):
    return Chat(message='Execute supplied plans, read and deliver', mode='provider', allow_compute=True,
                calculation_plans=plans or [plan()], **kw)


def tool(name, args):
    return call(name, json.dumps(args))


def batch(pairs):
    return {'role':'assistant','tool_calls':[call(n, json.dumps(a), str(i))['tool_calls'][0] for i,(n,a) in enumerate(pairs)]}


def response_driver(agent, monkeypatch, plans, *, duplicate=False):
    captured=[]
    def complete(messages, tools, **response_options):
        captured.append(copy.deepcopy(tools))
        turn=len(captured)
        if turn==1:
            return batch([('calculation_execute',{'plan_key':p['plan_key']}) for p in plans])
        records=[agent.store.list(p['kind'])[0] for p in plans]
        if turn==2:
            pairs=[(inspection(p['kind']).read_tool,{inspection(p['kind']).argument:r[p['kind']+'_id']}) for p,r in zip(plans,records)]
            if duplicate:pairs.insert(0,('calculation_execute',{'plan_key':plans[0]['plan_key']}))
            return batch(pairs)
        deliveries=[]
        for p,r in zip(plans,records):
            kind=p['kind']
            # Independently specified expected values, not taken from calculator output.
            f={'thermal':('total_resistance_m2k_w','1.97','m2 K/W','steady_state',None),
               'lifecycle':('boundary_total_kgco2e','1597.6','kgCO2e','study_period',12),
               'cost':('material_total','156.72','USD','quote_date',None)}[kind]
            deliveries.append(('professional_deliver',{'delivery':{'kind':kind,'record_id':r[kind+'_id'],'record_hash':r['hash'],
                'statements':[{'fact':f[0],'value':f[1],'unit':f[2],'period':f[3],'study_years':f[4],'area_m2':None}],
                'finish':True}}))
        return batch(deliveries)
    monkeypatch.setattr(agent.gateway,'public',lambda:{'enabled':True,'key_configured':True})
    monkeypatch.setattr(agent.gateway,'complete',complete)
    return captured


@pytest.mark.parametrize('kind',['thermal','lifecycle','cost'])
def test_actual_save_read_delivery_and_independent_arithmetic(client,monkeypatch,kind):
    pid=create_project(client)['project_id'];a=client.app.state.agent;p=plan(kind)
    captured=response_driver(a,monkeypatch,[p],duplicate=True)
    t=a.start(pid,chat([p]),background=False)
    assert t['status']=='succeeded',t.get('error')
    assert t['answer']['task_completion']=='partial'
    assert len(a.store.list(kind,pid))==1 and any(e.get('reused') for e in t['events'])
    assert t['calculation_progress'][0]['state']=='verified'
    saved=a.store.list(kind,pid)[0]
    r=inspection(kind).service(a.domain).view(pid,saved[kind+'_id'])['result']
    if kind=='thermal':
        expected=Fraction(17,100)+Fraction(130,1000)/Fraction(65,100)+Fraction(6,100)/(Fraction(30,1000)*Fraction(5,4))
        assert r['total_resistance_m2k_w']==pytest.approx(float(expected))
        assert r['u_w_m2k']==pytest.approx(float(1/expected))
    elif kind=='lifecycle':
        expected=Fraction(5,4)*1000*Fraction(42,100)+75*Fraction(8,100)+240*Fraction(37,100)*12+50*Fraction(2,100)
        assert r['boundary_total_kgco2e']==pytest.approx(float(expected))
        assert r['issued_credits_t'] is None
    else:
        expected=(Decimal('19.5')*Decimal('1.04')*Decimal('7.2')).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
        expected+=(Decimal('3')*Decimal('1.1')).to_integral_value(rounding=ROUND_CEILING)*Decimal('2.675')
        assert Decimal(r['material_total'])==expected
    definition=next(x['function'] for x in captured[0] if x['function']['name']=='calculation_execute')
    assert definition['parameters']['properties']=={'plan_key':{'type':'string','enum':['a']}}
    assert len(t['events'])<=15


def test_two_plans_fit_existing_budget_and_later_stale(client,monkeypatch):
    project=create_project(client);pid=project['project_id'];a=client.app.state.agent
    plans=[plan('thermal','wall'),plan('lifecycle','carbon')]
    response_driver(a,monkeypatch,plans)
    t=a.start(pid,chat(plans),background=False)
    assert t['status']=='succeeded',t.get('error')
    assert len(t['events'])==12 and all(p['state']=='verified' for p in t['calculation_progress'])
    old=a.store.get('agent',t['agent_id'])
    assert client.put(f'/api/projects/{pid}/building',json={'expected_revision':project['revision'],
        'building':{**project['building'],'area_m2':1000.}}).status_code==200
    current=a.view(pid,t['agent_id'])
    assert current['answer']['task_completion']=='incomplete'
    assert all(p['state']=='saved_unverified' for p in current['calculation_progress'])
    assert a.store.get('agent',t['agent_id'])==old


@pytest.mark.parametrize('change',[{'allow_compute':False},{'mode':'local'},{'objective':'inspect_thermal'},
    {'calculation_plans':[plan(),plan()]},{'calculation_plans':[plan(key=str(i)) for i in range(3)]}])
def test_invalid_task_authorization_or_capacity_rejected(change):
    data=chat().model_dump(mode='json');data.update(change)
    with pytest.raises(ValueError):Chat.model_validate(data)


@pytest.mark.parametrize('field,value',[('thickness',-1.),('conductivity',0.),('thickness_unit','ft')])
def test_engineering_invalid_inputs_rejected_before_start(client,field,value):
    pid=create_project(client)['project_id'];p=plan();p['input']['layers'][0][field]=value
    r=client.post(f'/api/projects/{pid}/agent/chat',json={'message':'compute','mode':'provider','allow_compute':True,'calculation_plans':[p]})
    assert r.status_code==422
    assert not client.app.state.agent.store.list('thermal',pid)


@pytest.mark.parametrize('args',[{'plan_key':'invented'},{'plan_key':'a','input':{'thickness':999}},{}])
def test_model_cannot_substitute_inputs_or_keys(client,monkeypatch,args):
    pid=create_project(client)['project_id'];a=client.app.state.agent
    scripted(a,monkeypatch,[tool('calculation_execute',args)])
    t=a.start(pid,chat(),background=False)
    assert t['status']=='failed' and not a.store.list('thermal',pid)
    assert t['calculation_progress'][0]['state']=='not_executed'


def test_missing_parameter_saved_incomplete_never_verified(client,monkeypatch):
    pid=create_project(client)['project_id'];a=client.app.state.agent;p=plan();p['input']['layers'][0]['conductivity']=None
    scripted(a,monkeypatch,[tool('calculation_execute',{'plan_key':'a'}),DONE])
    t=a.start(pid,chat([p]),background=False)
    assert t['status']=='succeeded' and t['answer']['task_completion']=='not_assessed'
    r=a.store.list('thermal',pid)[0]
    assert r['result']['u_w_m2k'] is None and t['calculation_progress'][0]['state']=='saved_unverified'


def test_project_changed_between_submission_and_write_refused(client,monkeypatch):
    p=create_project(client);pid=p['project_id'];a=client.app.state.agent
    def complete(*args, **response_options):
        assert client.put(f'/api/projects/{pid}/building',json={'expected_revision':p['revision'],
            'building':{**p['building'],'area_m2':1000.}}).status_code==200
        return tool('calculation_execute',{'plan_key':'a'})
    monkeypatch.setattr(a.gateway,'public',lambda:{'enabled':True,'key_configured':True})
    monkeypatch.setattr(a.gateway,'complete',complete)
    t=a.start(pid,chat(),background=False)
    assert t['status']=='failed' and 'changed' in t['error'] and not a.store.list('thermal',pid)


def test_history_does_not_restore_calculation_authorization(client,monkeypatch):
    pid=create_project(client)['project_id'];a=client.app.state.agent
    scripted(a,monkeypatch,[tool('calculation_execute',{'plan_key':'a'}),DONE,tool('calculation_execute',{'plan_key':'a'})])
    old=a.start(pid,chat(),background=False)
    new=a.start(pid,Chat(message='continue and do again',mode='provider',previous_agent_id=old['agent_id']),background=False)
    assert new['status']=='failed' and len(a.store.list('thermal',pid))==1
    with pytest.raises(ValueError):a.call(pid,'calculation_execute',{'plan_key':'a'},True)


def test_partial_write_then_failure_is_preserved_and_visible(client,monkeypatch):
    pid=create_project(client)['project_id'];a=client.app.state.agent
    plans=[plan('thermal'),plan('lifecycle','b')];plans[1]['input']['area_m2']=999.
    scripted(a,monkeypatch,[batch([('calculation_execute',{'plan_key':p['plan_key']}) for p in plans])])
    t=a.start(pid,chat(plans),background=False)
    assert t['status']=='failed' and len(a.store.list('thermal',pid))==1 and not a.store.list('lifecycle',pid)
    assert [p['state'] for p in t['calculation_progress']]==['saved_unverified','not_executed']


@pytest.mark.parametrize('foreign',[False,True])
def test_bound_evidence_cannot_be_foreign_or_withdrawn(client,monkeypatch,foreign):
    pid=create_project(client)['project_id'];other=create_project(client)['project_id'];a=client.app.state.agent
    source_pid=other if foreign else pid
    ev=client.post(f'/api/projects/{source_pid}/evidence',json={'type':'literature','name':'Synthetic source',
        'source_locator':'Synthetic row 1','authority':'Auditor','permission':'test only','acquisition_method':'test',
        'responsible_person':'auditor','status':'IMPORTED'}).json()
    p=plan();p['input']['layers'][0]['evidence_id']=ev['evidence_id']
    def complete(*args, **response_options):
        assert client.patch(f'/api/projects/{pid}/evidence/'+ev['evidence_id'],json={'expected_revision':1,
            'review_state':'rejected','responsible_person':'auditor','review_note':'Withdrawn in test'}).status_code==200
        return tool('calculation_execute',{'plan_key':'a'})
    monkeypatch.setattr(a.gateway,'public',lambda:{'enabled':True,'key_configured':True})
    monkeypatch.setattr(a.gateway,'complete',complete)
    if foreign:
        with pytest.raises(ValueError,match='Foreign'):a.start(pid,chat([p]),background=False)
    else:
        t=a.start(pid,chat([p]),background=False)
        assert t['status']=='failed' and 'rejected' in t['error']
    assert not a.store.list('thermal',pid)


def test_snapshot_and_input_tampering_refused(client):
    from backend import agent_calculations as calc
    pid=create_project(client)['project_id'];a=client.app.state.agent;b=chat()
    frozen=calc.snapshot(a.domain,pid,b.calculation_plans)
    b.calculation_plans[0].input.layers[0].thickness=999.
    with pytest.raises(ValueError,match='explicit'):calc.execute(a.domain,pid,'a',b.calculation_plans,frozen)
    b=chat();frozen['items'][0]['plan']['input']['layers'][0]['thickness']=999.
    with pytest.raises(ValueError,match='integrity'):calc.execute(a.domain,pid,'a',b.calculation_plans,frozen)
    assert not a.store.list('thermal',pid)


def test_plan_task_cannot_substitute_old_record_or_unrelated_write(client,monkeypatch):
    from test_agent_professional import create_record
    pid=create_project(client)['project_id'];a=client.app.state.agent
    old=create_record(client,pid,'thermal')
    for name,args in [('thermal_read',{'thermal_id':old['thermal_id']}),('carbon_calculate',{'run_id':'run_'+'a'*32})]:
        scripted(a,monkeypatch,[tool(name,args)])
        t=a.start(pid,chat(),background=False)
        assert t['status']=='failed' and not t['professional_deliveries']
        assert t['calculation_progress'][0]['state']=='not_executed'
    assert len(a.store.list('thermal',pid))==1 and not a.store.jobs(pid)
