"""Independent cross-record arithmetic, real services; scripted wire is not model proof."""
import copy
from fractions import Fraction
import pytest
from backend import agent_comparisons as comp
from backend.agent import Chat
from backend.agent_semantics import inspection
from test_api import create_project
from test_agent_professional import thermal_input, lifecycle_input, create_record
from test_agent_artifacts import cost_input, create_cost
from test_agent_select_before_read import selected_wire


def wall(second=False):
    body=thermal_input();body.update(rsi_m2k_w=.12,rse_m2k_w=.08)
    for layer,(d,k) in zip(body['layers'],[(.25,.5),(.06,.04)] if second else [(.2,.5),(.04,.04)]):
        layer.update(thickness=d,thickness_unit='m',conductivity=k,conductivity_unit='W/(m K)',correction_factor=1.)
    return body


def pair(client,kind='thermal',change=None):
    pid=create_project(client)['project_id']
    if kind=='thermal':a,b=wall(),wall(True)
    elif kind=='cost':
        a=cost_input();a['lines']=a['lines'][:1];a['lines'][0]['measure']['quantity']=0.;a['lines'][0]['quote']['unit_price']=7.5;a['lines'][0]['waste_ratio']=0.
        b=copy.deepcopy(a);b['lines'][0]['measure']['quantity']=1.
    else:
        a=lifecycle_input();b=copy.deepcopy(a);b['activities'][0]['quantity']=2.5
    if change:change(b)
    create=create_cost if kind=='cost' else lambda c,p,body:create_record(c,p,kind,body)
    return pid,create(client,pid,a),create(client,pid,b)


def request(a,b,metric,**kw):
    kind=next(k for k in comp.KINDS if k+'_id' in a)
    return comp.Comparison(baseline_id=a[kind+'_id'],baseline_hash=a['hash'],candidate_id=b[kind+'_id'],
        candidate_hash=b['hash'],fact_key=metric,outputs=['difference','relative_change_percent'],finish=True,**kw)


def read_task(client,pid,a,b,key):
    kind=next(k for k in comp.KINDS if k+'_id' in a);spec=inspection(kind);agent=client.app.state.agent
    return {'events':[{'tool':spec.read_tool,'status':'succeeded','result':agent.call(pid,spec.read_tool,{spec.argument:s[spec.record_key],'fact_keys':[key]},False)} for s in (a,b)],'professional_deliveries':[]}


@pytest.mark.parametrize('key,base,other', [('total_resistance_m2k_w',Fraction(8,5),Fraction(11,5)),('u_w_m2k',Fraction(5,8),Fraction(5,11))])
@pytest.mark.parametrize('reverse',[False,True])
def test_frozen_fraction_oracle_and_reverse_baseline(client,key,base,other,reverse):
    pid,a,b=pair(client)
    if reverse:a,b,base,other=b,a,other,base
    task=read_task(client,pid,a,b,key)
    result=comp.evaluate(client.app.state.agent.domain,pid,task,request(a,b,key))
    assert result['status']=='verified'
    assert float(result['values']['difference'])==pytest.approx(float(other-base),rel=1e-10,abs=1e-8)
    assert float(result['values']['relative_change_percent'])==pytest.approx(float((other-base)/base*100),rel=1e-10,abs=1e-8)
    assert result['baseline']==str(a['result'][key])
    assert len(task['professional_deliveries'])==2


def test_zero_cost_baseline_preserves_absolute_difference_and_unknown_percent(client):
    pid,a,b=pair(client,'cost');key='material_total';task=read_task(client,pid,a,b,key)
    r=comp.evaluate(client.app.state.agent.domain,pid,task,request(a,b,key))
    assert r['status']=='verified' and r['values']=={'difference':'7.50','relative_change_percent':None}
    assert r['unavailable_reason']=='zero_baseline_relative_change_undefined'


def test_lifecycle_same_basis_independent_quantity_difference(client):
    pid,a,b=pair(client,'lifecycle');key='stage.production';task=read_task(client,pid,a,b,key)
    r=comp.evaluate(client.app.state.agent.domain,pid,task,request(a,b,key))
    assert float(r['values']['difference'])==525. and float(r['values']['relative_change_percent'])==100.
    assert r['context']['study_years']==12


@pytest.mark.parametrize('kind,key,field,value',[
    ('thermal','u_w_m2k','rsi_m2k_w',.2),('thermal','u_w_m2k','application','Different declared application'),
    ('cost','material_total','functional_scope','Different materials and procurement boundary'),
    ('cost','material_total','as_of','2026-12-01'),
    ('lifecycle','stage.production','study_years',25),
    ('lifecycle','stage.production','functional_unit','Different declared building function'),
])
def test_context_conflict_is_formal_unavailable_not_a_number(client,kind,key,field,value):
    pid,a,b=pair(client,kind,lambda body:body.update({field:value}));task=read_task(client,pid,a,b,key)
    r=comp.evaluate(client.app.state.agent.domain,pid,task,request(a,b,key))
    assert r['status']=='unavailable' and r['values'] is None and r['baseline'] is None and field in r['mismatches']


def test_currency_conflict_not_silent_conversion(client):
    def change(body):
        body['currency']='EUR'
        for line in body['lines']:line['quote']['currency']='EUR'
    pid,a,b=pair(client,'cost',change);key='material_total'
    r=comp.evaluate(client.app.state.agent.domain,pid,read_task(client,pid,a,b,key),request(a,b,key))
    assert r['values'] is None and 'currency' in r['mismatches']


def test_lifecycle_wrong_area_is_already_rejected_before_record_creation(client):
    pid=create_project(client)['project_id'];body=lifecycle_input();body['area_m2']=800.
    response=client.post(f'/api/projects/{pid}/lifecycle',json=body)
    assert response.status_code==409 and 'region/area' in response.json()['detail']


def test_factor_version_conflict_is_not_carbon_reduction(client):
    def change(body):body['activities'][0]['factor']['version']='unreviewed-3'
    pid,a,b=pair(client,'lifecycle',change);key='boundary_total_kgco2e'
    r=comp.evaluate(client.app.state.agent.domain,pid,read_task(client,pid,a,b,key),request(a,b,key))
    assert r['values'] is None and 'factor_bases' in r['mismatches'] and 'factor_identity_conflict' in r['mismatches']


@pytest.mark.parametrize('fault',['unread','wrong_hash','unselected','cross_project','incomplete'])
def test_no_unread_forged_omitted_or_unavailable_source_can_compare(client,fault):
    pid,a,b=pair(client);key='u_w_m2k';task=read_task(client,pid,a,b,key);req=request(a,b,key)
    if fault=='unread':task['events'].pop()
    elif fault=='wrong_hash':req=req.model_copy(update={'candidate_hash':'0'*64})
    elif fault=='unselected':req=req.model_copy(update={'fact_key':'total_resistance_m2k_w'})
    elif fault=='cross_project':pid=create_project(client)['project_id']
    else:
        body=wall(True);body['rsi_m2k_w']=None;b=create_record(client,pid,'thermal',body)
        task=read_task(client,pid,a,b,key);req=request(a,b,key)
    with pytest.raises((ValueError,KeyError)):
        comp.evaluate(client.app.state.agent.domain,pid,task,req)
    assert not task.get('professional_comparisons') and not task['professional_deliveries']


def model_comparison(client,monkeypatch,pid,a,b,key,outputs=None):
    agent=client.app.state.agent;req=request(a,b,key).model_dump(mode='json')
    if outputs:req['outputs']=outputs
    steps=[('professional_read_many',{'selections':[{'record_id':s['thermal_id'],'fact_keys':[key]} for s in (a,b)]}),
           ('professional_compare',{'comparison':req})]
    seen=selected_wire(agent,monkeypatch,steps)
    result=agent.start(pid,Chat(message='Compare '+key+' of '+a['thermal_id']+' baseline to '+b['thermal_id']+' candidate',mode='provider'),background=False)
    assert result['status']=='succeeded',result.get('error')
    assert len(result['events'])<=15 and len(seen)==2
    assert 'professional_compare' not in {t['function']['name'] for t in seen[0]}
    assert 'professional_compare' in {t['function']['name'] for t in seen[1]}
    return result


def test_model_wire_actual_persistence_final_recheck_and_withdrawal(client,monkeypatch):
    pid,a,b=pair(client);task=model_comparison(client,monkeypatch,pid,a,b,'u_w_m2k')
    assert task['answer']['checked_comparisons'][0]['status']=='verified'
    agent=client.app.state.agent;before=copy.deepcopy(agent.store.get('agent',task['agent_id']))
    project=agent.store.get('project',pid)
    assert client.put(f'/api/projects/{pid}/building',json={'expected_revision':project['revision'],'building':{**project['building'],'area_m2':997.}}).status_code==200
    current=client.get(f'/api/projects/{pid}/agent/{task["agent_id"]}').json()
    row=current['answer']['checked_comparisons'][0]
    assert row['status']=='stale' and row['values'] is row['baseline'] is row['candidate'] is None
    assert agent.store.get('agent',task['agent_id'])==before


def test_difference_only_does_not_add_unrequested_percentage(client,monkeypatch):
    pid,a,b=pair(client);task=model_comparison(client,monkeypatch,pid,a,b,'total_resistance_m2k_w',['difference'])
    assert set(task['answer']['checked_comparisons'][0]['values'])=={'difference'}


def test_direct_call_without_task_cannot_forge_read_receipt(client):
    pid,a,b=pair(client)
    with pytest.raises(ValueError,match='bounded task'):
        client.app.state.agent.call(pid,'professional_compare',{'comparison':request(a,b,'u_w_m2k').model_dump(mode='json')},False)


@pytest.mark.parametrize('mutation',[{'baseline_id':'thermal_'+'a'*32,'candidate_id':'cost_'+'b'*32},
    {'baseline_id':'thermal_'+'a'*32,'candidate_id':'thermal_'+'a'*32}, {'outputs':['difference','difference']},
    {'baseline':'12345'}])
def test_comparison_contract_has_no_model_numbers_or_mixed_dimensions(mutation):
    raw={'baseline_id':'thermal_'+'a'*32,'candidate_id':'thermal_'+'b'*32,'baseline_hash':'1'*64,'candidate_hash':'2'*64,
         'fact_key':'u_w_m2k','outputs':['difference'],'finish':True,**mutation}
    with pytest.raises(ValueError):comp.Comparison.model_validate(raw)


def test_real_model_redundant_delivery_sequence_reserves_each_source_once(client,monkeypatch):
    import json
    from backend import agent_actions
    pid,a,b=pair(client);agent=client.app.state.agent;key='u_w_m2k'
    comparison=request(a,b,key).model_dump(mode='json');comparison['finish']=False
    reads=[{'tool':'thermal_read','arguments':{'thermal_id':s['thermal_id'],'fact_keys':[key]}} for s in (a,b)]
    repeated=[{'tool':'professional_deliver','arguments':{'delivery':{'kind':'thermal','record_id':s['thermal_id'],
        'record_hash':s['hash'],'fact_keys':[key],'finish':finish}}} for finish in (False,True) for s in (a,b)]
    responses=iter([reads,[{'tool':'professional_compare','arguments':{'comparison':comparison}}],repeated])
    monkeypatch.setattr(agent.gateway,'public',lambda:{'enabled':True,'key_configured':True})
    monkeypatch.setattr(agent.gateway,'complete',lambda messages,tools,**options:agent_actions.decode(
        {'role':'assistant','content':json.dumps({'actions':next(responses)})},tools))
    task=agent.start(pid,Chat(message='Compare U '+a['thermal_id']+' baseline to '+b['thermal_id'],mode='provider'),background=False)
    assert task['status']=='succeeded',task.get('error')
    assert len(task['events'])==13 and task['answer']['checked_comparisons'][0]['status']=='verified'
    assert len(task['professional_deliveries'])==2


def test_unique_source_budget_still_reserves_distinct_records():
    from backend.agent_delivery_budget import additional_reads
    refs=[{'record_id':'thermal_'+x*32,'record_hash':'1'*64,'kind':'thermal','fact_keys':['u_w_m2k'],'finish':False} for x in ('a','b','c')]
    calls=[{'function':{'name':'professional_deliver','arguments':{'delivery':r}}} for r in [refs[0],refs[1],refs[0],refs[2]]]
    assert additional_reads({},calls)==3
    assert additional_reads({'professional_deliveries':[refs[0]]},calls)==2
    assert additional_reads({'professional_deliveries':refs},calls)==0
