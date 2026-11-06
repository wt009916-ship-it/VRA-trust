"""New independent inputs and current-source checks for professional task delivery."""
import copy
import json
from fractions import Fraction

import pytest

from backend.agent import Chat
from test_api import create_project


def thermal_input():
    return {'name':'Independent mixed-unit assembly','rsi_m2k_w':.12,'rse_m2k_w':.05,
            'surface_basis':'Synthetic declared films, not a standard default','application':'Uniform opaque test layers',
            'layers':[{'name':name,'thickness':d,'thickness_unit':u,'conductivity':k,'conductivity_unit':ku,
                       'correction_factor':c,'correction_basis':'Synthetic declared correction','source':'Independent test input'}
                      for name,d,u,k,ku,c in [('Layer A',130.,'mm',.65,'W/(m K)',1.),('Layer B',6.,'cm',30.,'mW/(m K)',1.25)]]}


def lifecycle_input():
    values=[('production',1.25,'t',.42,'kg','whole_period'),('transport',75.,'tkm',.08,'tkm','whole_period'),
            ('operation',240.,'kWh',.37,'kWh','annual'),('end_of_life',50.,'kg',.02,'kg','whole_period')]
    return {'name':'Independent bounded inventory','area_m2':927.2,'study_years':12,'region':'US-CO',
            'method':'Synthetic GWP arithmetic','functional_unit':'Declared office area over twelve years',
            'boundaries':[{'stage':s,'included':s!='construction','reason':'Explicit synthetic boundary, construction excluded'}
                          for s in ['production','transport','construction','operation','end_of_life']],
            'activities':[{'activity_id':s,'name':s,'stage':s,'quantity':q,'unit':u,'period':p,'source':'Independent activity input',
                           'factor':{'factor_id':s+'-f','value':v,'denominator':d,'stage':s,'source':'Synthetic factor; not certified',
                                     'publisher':'Audit fixture','version':'new-2','year':2026,'region':'*','method':'Synthetic GWP arithmetic'}}
                          for s,q,u,v,d,p in values]}


def create_record(client, pid, kind, body=None):
    body = body or (thermal_input() if kind=='thermal' else lifecycle_input())
    response=client.post(f'/api/projects/{pid}/{kind}',json=body)
    assert response.status_code==201,response.text
    return response.json()


def task(client,pid,kind,**kw):
    return client.app.state.agent.start(pid,Chat(message='Read the current declared record',objective='inspect_'+kind,**kw),background=False)


def test_thermal_task_independent_fraction_and_not_annual_savings(client):
    pid=create_project(client)['project_id'];record=create_record(client,pid,'thermal');t=task(client,pid,'thermal')
    a=t['answer']['artifact'];r=a['result'];expected=Fraction(12,100)+Fraction(5,100)+Fraction(130,1000)/Fraction(65,100)+Fraction(6,100)/(Fraction(30,1000)*Fraction(5,4))
    assert expected==Fraction(197,100)
    assert r['u_w_m2k']==pytest.approx(float(1/expected),rel=1e-12)
    assert r['total_resistance_m2k_w']==pytest.approx(float(expected))
    assert r['layers'][1]['effective_conductivity_w_mk']==pytest.approx(.0375)
    assert r['energy_saving_rate'] is None and r['compliance_status']=='NOT_ASSESSED'
    assert a['source_status']=='USER_DECLARED' and a['record_hash']==record['hash']
    assert t['answer']['task_completion']=='verified' and t['target_thermal_id']==record['thermal_id']
    assert [e['tool'] for e in t['events']]==['project_get','thermal_list','thermal_read','thermal_read']


def test_lifecycle_task_independent_fraction_boundary_and_credits(client):
    pid=create_project(client)['project_id'];create_record(client,pid,'lifecycle');t=task(client,pid,'lifecycle')
    a=t['answer']['artifact'];r=a['result']
    total=Fraction(5,4)*1000*Fraction(42,100)+75*Fraction(8,100)+240*Fraction(37,100)*12+50*Fraction(2,100)
    assert total==Fraction(7988,5)
    assert r['boundary_total_kgco2e']==pytest.approx(float(total),rel=1e-12)
    assert r['kgco2e_m2_over_study_period']==pytest.approx(float(total/Fraction(9272,10)),rel=1e-12)
    assert r['rows'][0]['quantity_in_factor_unit']==1250 and r['rows'][2]['period_multiplier']==12
    assert r['stages']['construction']['kgco2e'] is None and not r['all_five_stages_entered']
    assert r['certification']=='NOT_ASSESSED' and r['issued_credits_t'] is None
    assert a['input']['activities'][0]['factor']['version']=='new-2'
    assert t['answer']['task_completion']=='verified' and not t['answer']['can_recommend']


@pytest.mark.parametrize('kind',['thermal','lifecycle'])
@pytest.mark.parametrize('missing',['record','value'])
def test_missing_professional_result_is_incomplete(client,kind,missing):
    pid=create_project(client)['project_id']
    if missing=='value':
        b=thermal_input() if kind=='thermal' else lifecycle_input()
        if kind=='thermal':b['rsi_m2k_w']=None
        else:b['activities'][0]['factor']['value']=None
        create_record(client,pid,kind,b)
    t=task(client,pid,kind)
    assert t['status']=='succeeded' and t['answer']['task_completion']=='incomplete'
    assert 'IDF' not in t['answer']['summary']
    if missing=='value':assert not t['answer']['artifact']['verified']
    else:assert t['answer']['artifact'] is None


@pytest.mark.parametrize('kind',['thermal','lifecycle'])
def test_target_continuation_and_cross_topic_do_not_drift(client,kind):
    pid=create_project(client)['project_id'];first=create_record(client,pid,kind);t=task(client,pid,kind)
    second=create_record(client,pid,kind)
    continued=task(client,pid,kind,previous_agent_id=t['agent_id'])
    assert continued['target_'+kind+'_id']==first[kind+'_id']
    assert continued[kind+'_selection_basis']=='previous_task'
    fresh=task(client,pid,kind);assert fresh['target_'+kind+'_id']==second[kind+'_id']
    other='thermal' if kind=='lifecycle' else 'lifecycle';different=create_record(client,pid,other)
    switched=task(client,pid,other,previous_agent_id=t['agent_id'])
    assert switched['target_'+other+'_id']==different[other+'_id']
    assert switched[other+'_selection_basis']=='latest_at_start'


@pytest.mark.parametrize('kind',['thermal','lifecycle'])
def test_current_history_invalidates_without_rewriting_snapshot(client,kind):
    project=create_project(client);pid=project['project_id'];create_record(client,pid,kind);t=task(client,pid,kind)
    store=client.app.state.agent.store;before=copy.deepcopy(store.get('agent',t['agent_id']))
    building={**project['building'],'area_m2':1000.}
    assert client.put(f'/api/projects/{pid}/building',json={'expected_revision':project['revision'],'building':building}).status_code==200
    current=client.get(f'/api/projects/{pid}/agent/{t["agent_id"]}').json()
    assert current['answer']['task_completion']=='incomplete' and current['answer']['artifact']['result'] is None
    assert current['historical_task_completion']=='verified'
    assert store.get('agent',t['agent_id'])==before
    history=client.get(f'/api/projects/{pid}/agent-tasks').json()
    assert history[0]['answer']['task_completion']=='incomplete'


@pytest.mark.parametrize('kind',['thermal','lifecycle'])
def test_factor_or_material_withdrawal_invalidates_task(client,kind):
    pid=create_project(client)['project_id'];base=f'/api/projects/{pid}'
    ev=client.post(base+'/evidence',json={'type':'literature','name':'Withdrawable declared source','source_locator':'Synthetic table row',
        'authority':'Audit fixture','permission':'test only','acquisition_method':'test','responsible_person':'auditor','status':'IMPORTED'}).json()
    b=thermal_input() if kind=='thermal' else lifecycle_input()
    if kind=='thermal':b['layers'][0]['evidence_id']=ev['evidence_id']
    else:b['activities'][0]['factor']['evidence_id']=ev['evidence_id']
    create_record(client,pid,kind,b);t=task(client,pid,kind)
    assert client.patch(base+'/evidence/'+ev['evidence_id'],json={'expected_revision':1,'review_state':'rejected',
        'responsible_person':'auditor','review_note':'Source withdrawn after task completion'}).status_code==200
    current=client.app.state.agent.view(pid,t['agent_id'])
    assert current['answer']['task_completion']=='incomplete' and current['answer']['artifact']['status']=='stale'


@pytest.mark.parametrize('kind',['thermal','lifecycle'])
def test_foreign_target_and_tools_reject_before_model_or_any_write(client,kind,monkeypatch):
    pid=create_project(client)['project_id'];foreign=create_project(client)['project_id'];r=create_record(client,foreign,kind)
    agent=client.app.state.agent
    with pytest.raises(ValueError,match='Cross-project'):
        task(client,pid,kind,**{'target_'+kind+'_id':r[kind+'_id']})
    with pytest.raises(ValueError,match='Cross-project'):
        agent.call(pid,kind+'_read',{kind+'_id':r[kind+'_id']},False)
    assert not agent.store.list('agent',pid)
    assert client.post(f'/api/projects/{pid}/agent/chat',json={'message':'Read','objective':'inspect_'+kind,
        'target_run_id':'run_'+'0'*32}).status_code==422
    create_record(client,pid,kind)
    monkeypatch.setattr(agent.gateway,'public',lambda:{'enabled':True,'key_configured':True})
    def unsafe(messages,tools):
        assert {t['function']['name'] for t in tools}=={'project_get',kind+'_list',kind+'_read'}
        return {'role':'assistant','tool_calls':[{'id':'unsafe','type':'function','function':{'name':'simulation_create','arguments':'{}'}}]}
    monkeypatch.setattr(agent.gateway,'complete',unsafe)
    out=task(client,pid,kind,mode='provider',allow_compute=True)
    assert out['status']=='failed' and out['answer'] is None and not agent.store.jobs(pid)


@pytest.mark.parametrize('kind',['thermal','lifecycle'])
def test_false_model_certification_and_values_are_audit_only(client,kind,monkeypatch):
    pid=create_project(client)['project_id'];create_record(client,pid,kind);agent=client.app.state.agent
    monkeypatch.setattr(agent.gateway,'public',lambda:{'enabled':True,'key_configured':True})
    monkeypatch.setattr(agent.gateway,'complete',lambda *a:{'role':'assistant','content':'全年节能率99%，已签发9999吨信用，已经安全认证。'})
    t=task(client,pid,kind,mode='provider')
    assert t['answer']['task_completion']=='verified' and t['llm_commentary_policy']=='audit_only'
    assert '9999' not in json.dumps(t['answer']) and '9999' in t['llm_commentary']
    assert agent.context(pid,t['agent_id'])[0]['model_commentary_unverified']==''


def test_final_validation_and_model_requests_fit_total_event_budget(client,monkeypatch):
    pid=create_project(client)['project_id'];r=create_record(client,pid,'thermal');agent=client.app.state.agent
    monkeypatch.setattr(agent.gateway,'public',lambda:{'enabled':True,'key_configured':True})
    monkeypatch.setattr(agent.gateway,'complete',lambda *a:{'role':'assistant','tool_calls':[
        {'id':str(i),'type':'function','function':{'name':'thermal_read','arguments':json.dumps({'thermal_id':r['thermal_id']})}} for i in range(4)]})
    t=task(client,pid,'thermal',mode='provider')
    assert t['status']=='failed' and 'budget' in t['error'].lower() and len(t['events'])<=15
