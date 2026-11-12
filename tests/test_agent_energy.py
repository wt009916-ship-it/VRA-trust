"""Energy source semantics and Agent protocol; scripted models are not inference evidence."""
import copy
import pytest
from backend import core,agent_energy,agent_missing,end_use_records
from backend.agent import Chat
from backend.agent_semantics import Statement,Delivery,SemanticMismatch,facts,check,model_projection
from test_utility_comparison import templates as templates,native as native,prepare,body
from test_agent_contract import scripted
from test_agent_capabilities import tool
from test_end_use import native_template as native_template
from test_api import create_project


def create_utility(client,native,monkeypatch):
    pid,ev,service,snapshot=prepare(client,native,monkeypatch)
    source=service.sources.source
    monkeypatch.setattr(end_use_records.Ledgers,'source',lambda self,p,r:source(p,r))
    record=service.create(pid,body(bill_evidence_id=ev['evidence_id']),'test')
    return pid,record,snapshot


def claim(record,kind,keys):
    chosen={f['fact']:f for f in facts(record,kind)}
    return {'kind':kind,'record_id':record[kind+'_id'],'record_hash':record['hash'],'statements':[{k:chosen[key][k] for k in Statement.model_fields} for key in keys]}


@pytest.mark.parametrize('field,value',[
 ('native_year',2020),('native_start','2020-01-01T00:00'),('bill_start','2020-01-01T00:00'),('bill_end','2021-01-01T00:00'),('carrier','Gas'),('boundary','ElectricityPurchased:Facility'),('data_nature','measured'),('basis','native_table_rounded'),('alignment','calendar_pattern'),('uses_daylight_saving',True),('weather_calendar_matches_native',False),('run_id','run_'+'0'*32)])
def test_equal_number_wrong_energy_context_refused(client,native,monkeypatch,field,value):
    _,record,_=create_utility(client,native,monkeypatch);d=claim(record,'utility',['bill_total_kwh']);assert check(record,Delivery.model_validate(d))['status']=='verified'
    d['statements'][0]['energy_context'][field]=value
    with pytest.raises(SemanticMismatch):check(record,Delivery.model_validate(d))


def test_energy_context_cannot_be_omitted(client,native,monkeypatch):
    _,r,_=create_utility(client,native,monkeypatch);d=claim(r,'utility',['mbe_percent']);d['statements'][0].pop('energy_context')
    with pytest.raises(SemanticMismatch):check(r,Delivery.model_validate(d))


def test_zero_bill_percent_is_source_undefined_not_zero(client,native,monkeypatch):
    (native/'matched.csv').write_bytes((native/'zero.csv').read_bytes());_,r,_=create_utility(client,native,monkeypatch);d=claim(r,'utility',['mbe_percent','cvrmse_percent','rmse_kwh']);checked=check(r,Delivery.model_validate(d));assert checked['statements'][0]['value'] is None and checked['statements'][0]['unavailable_reason']
    d['statements'][0]['value']='0'
    with pytest.raises(SemanticMismatch):check(r,Delivery.model_validate(d))


def test_selected_energy_projection_is_bounded_and_catalog_has_no_values(client,native,monkeypatch):
    pid,r,_=create_utility(client,native,monkeypatch);agent=client.app.state.agent
    value=agent.call(pid,'utility_comparison_read',{'utility_id':r['utility_id']},False)
    projected=model_projection(value,'utility');assert projected['explanation_facts']==[] and len(projected['available_fact_catalog'])==8
    assert all('value' not in f and 'source_value' not in f for f in projected['available_fact_catalog'])
    value=agent.call(pid,'utility_comparison_read',{'utility_id':r['utility_id'],'fact_keys':['mbe_percent']},False)
    assert [f['fact'] for f in model_projection(value,'utility')['explanation_facts']]==['mbe_percent']
    with pytest.raises(core.ValidationError):agent.call(pid,'utility_comparison_read',{'utility_id':r['utility_id'],'fact_keys':['issued_carbon_credits']},False)


def test_energy_catalog_pages_names_without_reading_numeric_detail(client,native,monkeypatch):
    pid,r,_=create_utility(client,native,monkeypatch);store=client.app.state.domain.store
    for i in range(1,14):
        row=copy.deepcopy(r);row['utility_id']='utility_'+format(i,'032x');row['input']['name']='Name '+str(i);store.put('utility',row)
    monkeypatch.setattr(agent_energy.UtilityReads,'view',lambda *a:pytest.fail('Catalog must not inspect numeric detail'))
    spec=next(s for s in __import__('backend.agent_inspections',fromlist=['INSPECTIONS']).INSPECTIONS.values() if s.kind=='utility');rows=[];cursor=None
    while True:
        page=agent_missing.catalog(client.app.state.domain,pid,spec,cursor);assert len(page['records'])<=6 and page['total_count']==14
        rows+=page['records'];cursor=page['next_before']
        if cursor is None:break
    assert len({x['utility_id'] for x in rows})==14 and all(set(x)=={'utility_id','name','status'} for x in rows)
    records,_=agent_missing.snapshot(client.app.state.domain,pid,'utility');assert all('result' not in x and 'evidence_snapshot' not in x for x in records)


def test_model_protocol_reads_selected_fact_and_delivers_context(client,native,monkeypatch):
    pid,r,_=create_utility(client,native,monkeypatch);agent=client.app.state.agent
    history=scripted(agent,monkeypatch,[tool('utility_comparison_read',{'utility_id':r['utility_id'],'fact_keys':['bill_total_kwh','mbe_percent']}),tool('professional_deliver',{'delivery':{**claim(r,'utility',['bill_total_kwh','mbe_percent']),'finish':True}})])
    task=agent.start(pid,Chat(message='Read bill and bias from '+r['utility_id'],mode='provider',infer_outputs=False,read_requests=[{'request_key':'bill','kind':'utility','purpose':'results','record_id':r['utility_id']}]),background=False)
    assert task['status']=='succeeded',task.get('error')
    assert len(task['answer']['checked_statements'][0]['facts'])==2 and task['read_request_progress'][0]['state']=='result_verified'
    assert len(history)==2 and all(e['tool'] not in {'simulation_create','calculation_execute'} for e in task['events'])


def test_withdrawal_between_read_and_delivery_never_revives_numeric_result(client,native,monkeypatch):
    pid,r,snapshot=create_utility(client,native,monkeypatch);agent=client.app.state.agent
    scripted(agent,monkeypatch,[tool('utility_comparison_read',{'utility_id':r['utility_id'],'fact_keys':['mbe_percent']}),tool('professional_deliver',{'delivery':{**claim(r,'utility',['mbe_percent']),'finish':True}})])
    original=agent.gateway.complete;count=0
    def withdraw(*args):
        nonlocal count
        count+=1
        if count>1:snapshot['sql_sha256']='changed'
        return original(*args)
    monkeypatch.setattr(agent.gateway,'complete',withdraw)
    task=agent.start(pid,Chat(message='Read '+r['utility_id'],mode='provider',infer_outputs=False,read_requests=[{'request_key':'bill','kind':'utility','purpose':'results','record_id':r['utility_id']}]),background=False)
    assert any(e['tool']=='professional_deliver' and e['status']=='failed' and 'stale' in e['error'].lower() for e in task['events'])
    assert not (task['answer'] or {}).get('checked_statements') and not task.get('professional_deliveries')


def test_application_read_execution_copies_context_but_is_not_model_tool_selection(client,native,monkeypatch):
    pid,r,_=create_utility(client,native,monkeypatch);agent=client.app.state.agent
    scripted(agent,monkeypatch,[tool('requested_output_plan',{'output_plan':[{'request_key':'r','question_fragment_ids':['q1'],'fact_keys':['bill_total_kwh','mbe_percent'],'explanation_topics':['period']} ]})])
    t=agent.start(pid,Chat(message='读取账单总量和平均偏差并说明期间。',mode='provider',read_requests=[{'request_key':'r','kind':'utility','purpose':'results','record_id':r['utility_id']}]),background=False)
    assert t['status']=='succeeded',t.get('error')
    assert t['answer']['output_contract_coverage']=='fulfilled'
    facts=t['answer']['checked_statements'][0]['facts'];assert all(f['energy_context']['native_year']==2019 for f in facts)
    assert not t['answer'].get('intent_verified',False)


def test_enduse_adapter_binds_native_calendar_and_distinguishes_rounding(client,native_template,monkeypatch):
    pid=create_project(client)['project_id'];rid='run_'+'3'*32
    source={'run_id':rid,'sql_sha256':core.sha(native_template/'output/eplusout.sql'),'mtd_sha256':core.sha(native_template/'output/eplusout.mtd')}
    monkeypatch.setattr(end_use_records.Ledgers,'source',lambda self,p,r:(source.copy(),native_template))
    ledger=end_use_records.Ledgers(client.app.state.domain).create(pid,end_use_records.LedgerInput(name='Native energy source',purpose='Read actual native clock and source rounding',run_id=rid),'test')
    record=agent_energy.EndUseReads(client.app.state.domain).view(pid,ledger['enduse_id']);assert record['energy_clock']['native_year']==2017
    rows={f['fact']:f for f in facts(record,'enduse')}
    assert rows['end_use.Fans.Electricity']['energy_context']['basis']=='hourly_meter_integral'
    assert rows['end_use.Pumps.Electricity']['energy_context']['basis']=='native_table_rounded'
    assert rows['end_use.Cooling.DistrictCooling']['energy_context']['carrier']=='District Cooling'
    claim_data=claim(record,'enduse',['end_use.Fans.Electricity']);assert check(record,Delivery.model_validate(claim_data))['status']=='verified'
    claim_data['statements'][0]['energy_context']['native_year']=2001
    with pytest.raises(SemanticMismatch):check(record,Delivery.model_validate(claim_data))
    source['sql_sha256']='changed';assert agent_energy.EndUseReads(client.app.state.domain).view(pid,ledger['enduse_id'])['result'] is None


def test_native_catalog_selection_does_not_leak_all_facts_into_pending_context(client,native_template,monkeypatch):
    import json
    from backend import agent_requests
    pid=create_project(client)['project_id'];rid='run_'+'4'*32
    source={'run_id':rid,'sql_sha256':core.sha(native_template/'output/eplusout.sql'),'mtd_sha256':core.sha(native_template/'output/eplusout.mtd')}
    monkeypatch.setattr(end_use_records.Ledgers,'source',lambda self,p,r:(source.copy(),native_template))
    ledger=end_use_records.Ledgers(client.app.state.domain).create(pid,end_use_records.LedgerInput(name='Selection regression',purpose='Exercise catalog then selective delivery with full native ledger',run_id=rid),'test')
    current=agent_energy.EndUseReads(client.app.state.domain).view(pid,ledger['enduse_id']);agent=client.app.state.agent
    scripted(agent,monkeypatch,[tool('end_use_read',{'enduse_id':ledger['enduse_id']}),
        tool('end_use_read',{'enduse_id':ledger['enduse_id'],'fact_keys':['native_hours']}),
        tool('professional_deliver',{'delivery':{**claim(current,'enduse',['native_hours']),'finish':True}})])
    original=agent.gateway.complete;seen=[]
    def capture(messages,tools):
        seen.append((copy.deepcopy(messages),copy.deepcopy(tools)));return original(messages,tools)
    monkeypatch.setattr(agent.gateway,'complete',capture)
    task=agent.start(pid,Chat(message='Read native hours',mode='provider',infer_outputs=False,read_execution='model',read_requests=[{'request_key':'hours','kind':'enduse','purpose':'results','record_id':ledger['enduse_id']}]),background=False)
    assert task['status']=='succeeded',task.get('error')
    assert len(seen)==3 and all(len(json.dumps(m,ensure_ascii=False))<64000 for m,_ in seen)
    assert 'professional_deliver' not in [t['function']['name'] for t in seen[1][1]]
    assert 'professional_deliver' in [t['function']['name'] for t in seen[2][1]]
    request=task['read_requests'][0]
    reads=[e for e in task['events'] if e['tool']=='end_use_read' and e['status']=='succeeded']
    record={'read_requests':[request],'events':[reads[0]],'professional_deliveries':[]}
    first=agent_requests.next_actions(record)[0]
    assert first['tool']=='end_use_read' and 'available_facts' not in first
    record['events']=[reads[1]];second=agent_requests.next_actions(record)[0]
    assert [f['fact'] for f in second['available_facts']]==['native_hours']
    # Audit retains all native facts; only model-facing messages are selected.
    assert len(reads[0]['result']['explanation_facts'])==77
