"""Real project catalogs and scripted tool messages; not evidence of model intelligence."""
import pytest

from backend.agent import Chat
from test_api import create_project
from test_agent_capabilities import tool
from test_agent_contract import scripted
from test_agent_professional import create_record
from test_agent_calculations import batch, chat, plan
from test_agent_semantics import delivery
from backend.agent_missing import Missing
from backend.agent_inspections import INSPECTIONS


KINDS=['thermal','lifecycle','cost','engineering','schedule','operation']


def test_empty_project_has_formal_missing_delivery_without_inventing_record(client, monkeypatch):
    pid=create_project(client)['project_id'];agent=client.app.state.agent
    scripted(agent,monkeypatch,[tool('professional_inventory',{'kinds':['thermal']}),tool('professional_missing',{'missing':{'kind':'thermal','finish':True}})])
    task=agent.start(pid,Chat(message='Check absent wall record; do not invent an ID or value',mode='provider'),background=False)
    assert task['status']=='succeeded',task.get('error')
    answer=task['answer'];assert answer['task_completion']=='incomplete'
    assert answer['checked_missing'][0]['reason_code']=='no_records_in_project'
    assert not answer.get('checked_statements') and not agent.store.list('thermal',pid)
    assert [e['tool'] for e in task['events']].count('professional_missing')==1
    assert [e['tool'] for e in task['events']].count('professional_missing_recheck')==1


def test_catalog_reports_truncation_and_does_not_prove_older_record_absent(client):
    pid=create_project(client)['project_id'];agent=client.app.state.agent
    records=[create_record(client,pid,'thermal') for _ in range(7)]
    listing=agent.call(pid,'thermal_list',{},False)
    assert listing['total_count']==7 and listing['returned_count']==6 and listing['truncated']
    assert records[0]['thermal_id'] not in {r['thermal_id'] for r in listing['records']}
    with pytest.raises(ValueError,match='available'):
        agent.call(pid,'professional_missing',{'missing':{'kind':'thermal','record_id':records[0]['thermal_id']}},False)


@pytest.mark.parametrize('kind',KINDS)
def test_entire_scope_absence_has_no_record_id_or_engineering_values(client,kind):
    pid=create_project(client)['project_id'];agent=client.app.state.agent
    result=agent.call(pid,'professional_missing',{'missing':{'kind':kind}},False)
    assert result['missing']['project_record_count']==0 and result['missing']['record_id'] is None
    assert result['missing']['scope']=='entire_project_kind' and 'result' not in result
    listing=agent.call(pid,next(s.list_tool for s in INSPECTIONS.values() if s.kind==kind),{},False)
    assert listing['records']==[] and listing['total_count']==listing['returned_count']==0 and not listing['truncated']


def test_foreign_and_nonexistent_ids_are_indistinguishable_within_owned_project(client):
    own=create_project(client)['project_id'];foreign=create_project(client)['project_id'];agent=client.app.state.agent
    record=create_record(client,foreign,'thermal')
    receipts=[agent.call(own,'professional_missing',{'missing':{'kind':'thermal','record_id':rid}},False)
              for rid in [record['thermal_id'],'thermal_'+'0'*32]]
    for receipt in receipts:
        assert receipt['missing']['reason_code']=='record_not_available_in_project'
        assert receipt['missing']['project_record_count']==0
        assert foreign not in str(receipt) and record['hash'] not in str(receipt)
    assert receipts[0]['reference']['catalog_hash']==receipts[1]['reference']['catalog_hash']


@pytest.mark.parametrize('mutation',['record_created','project_revised'])
def test_history_rechecks_absence_without_rewriting_stored_task(client,monkeypatch,mutation):
    project=create_project(client);pid=project['project_id'];agent=client.app.state.agent
    scripted(agent,monkeypatch,[tool('professional_missing',{'missing':{'kind':'thermal','finish':True}})])
    task=agent.start(pid,Chat(message='Check absent record',mode='provider'),background=False)
    assert len(task['answer']['checked_missing'])==1
    old=agent.store.get('agent',task['agent_id'])
    if mutation=='record_created':create_record(client,pid,'thermal')
    else:agent.store.put('project',{**project,'name':'Revised'},project['revision'])
    current=agent.view(pid,task['agent_id'])
    assert current['answer']['checked_missing']==[]
    assert not current['answer']['verification'][-1]['passed']
    assert agent.store.get('agent',task['agent_id'])==old


def test_final_read_catches_concurrent_record_creation(client,monkeypatch):
    pid=create_project(client)['project_id'];agent=client.app.state.agent;original=agent.call;calls=0
    def call(*args,**kw):
        nonlocal calls
        result=original(*args,**kw)
        if args[1]=='professional_missing':
            calls+=1
            if calls==1:create_record(client,pid,'thermal')
        return result
    monkeypatch.setattr(agent,'call',call)
    scripted(agent,monkeypatch,[tool('professional_missing',{'missing':{'kind':'thermal','finish':True}})])
    task=agent.start(pid,Chat(message='Check absence',mode='provider'),background=False)
    assert task['status']=='succeeded' and not task['answer']['checked_missing']
    assert any(e['tool']=='professional_missing_recheck' and e['origin']=='controller' and not e['result']['checks'][0]['passed'] for e in task['events'])
    assert not task['answer']['verification'][-1]['passed']


def test_all_six_absence_scopes_fit_existing_budget_with_real_final_reads(client,monkeypatch):
    pid=create_project(client)['project_id'];agent=client.app.state.agent
    scripted(agent,monkeypatch,[batch([('professional_missing',{'missing':{'kind':k,'finish':False}}) for k in KINDS[:3]]),
                               batch([('professional_missing',{'missing':{'kind':k,'finish':True}}) for k in KINDS[3:]])])
    task=agent.start(pid,Chat(message='Check missing records for all six professional kinds',mode='provider'),background=False)
    assert task['status']=='succeeded',task.get('error')
    assert len(task['events'])==10 and len(task['answer']['checked_missing'])==6
    checks=[e for e in task['events'] if e['tool']=='professional_missing_recheck' and e['origin']=='controller']
    assert len(checks)==1 and len(checks[0]['result']['checks'])==6 and checks[0]['result']['snapshot_count']==1
    assert task['answer']['task_completion']=='incomplete'


def test_absence_does_not_replace_authorized_calculation_plan(client,monkeypatch):
    pid=create_project(client)['project_id'];agent=client.app.state.agent
    scripted(agent,monkeypatch,[tool('professional_missing',{'missing':{'kind':'thermal','finish':True}})])
    task=agent.start(pid,chat([plan()]),background=False)
    assert task['status']=='failed' and not agent.store.list('thermal',pid)
    assert not task['missing_deliveries'] and task['calculation_progress'][0]['state']=='not_executed'


def test_rejected_write_followup_checks_actual_catalog_without_retry(client,monkeypatch):
    pid=create_project(client)['project_id'];agent=client.app.state.agent;p=plan('lifecycle')
    p['input']['area_m2']=12.0
    scripted(agent,monkeypatch,[tool('calculation_execute',{'plan_key':p['plan_key']})])
    failed=agent.start(pid,chat([p]),background=False)
    assert failed['status']=='failed' and not agent.store.list('lifecycle',pid)
    captured=scripted(agent,monkeypatch,[tool('professional_inventory',{'kinds':['lifecycle']}),tool('professional_missing',{'missing':{'kind':'lifecycle','finish':True}})])
    task=agent.start(pid,Chat(message='Read previous carbon record; do not execute',mode='provider',previous_agent_id=failed['agent_id']),background=False)
    assert task['status']=='succeeded' and task['context_snapshot'][0]['previous_task_failed']
    assert task['answer']['checked_missing'][0]['kind']=='lifecycle'
    assert not any(e['tool']=='calculation_execute' for e in task['events']) and captured


def test_uncertain_write_cannot_be_reported_missing_if_record_was_saved(client,monkeypatch):
    pid=create_project(client)['project_id'];agent=client.app.state.agent;original=agent.call
    def call(*args,**kw):
        result=original(*args,**kw)
        if args[1]=='calculation_execute':raise RuntimeError('Failure after real commit')
        return result
    monkeypatch.setattr(agent,'call',call)
    scripted(agent,monkeypatch,[tool('calculation_execute',{'plan_key':'a'})])
    failed=agent.start(pid,chat([plan()]),background=False)
    assert failed['status']=='failed' and len(agent.store.list('thermal',pid))==1
    monkeypatch.setattr(agent,'call',original)
    scripted(agent,monkeypatch,[tool('professional_missing',{'missing':{'kind':'thermal','finish':True}}),{'role':'assistant','content':'Must inspect actual saved record; no retry.'}])
    task=agent.start(pid,Chat(message='Check previous outcome',mode='provider',previous_agent_id=failed['agent_id']),background=False)
    assert not task['missing_deliveries'] and len(agent.store.list('thermal',pid))==1
    assert task['events'][2]['status']=='failed'


@pytest.mark.parametrize('data',[{}, {'kind':'unknown'}, {'kind':'thermal','record_id':'cost_'+'1'*32},
    {'kind':'thermal','record_id':'../../secret'}, {'kind':'thermal','count':0}, {'kind':'thermal','finish':'true'}])
def test_missing_contract_rejects_fabricated_metadata_and_invalid_scope(data):
    with pytest.raises(ValueError):Missing.model_validate(data)


def test_model_cannot_invent_target_id_to_bypass_existing_records(client,monkeypatch):
    pid=create_project(client)['project_id'];create_record(client,pid,'thermal');agent=client.app.state.agent
    scripted(agent,monkeypatch,[tool('professional_missing',{'missing':{'kind':'thermal','record_id':'thermal_'+'0'*32,'finish':True}}),
                               {'role':'assistant','content':'Need current record lookup.'}])
    task=agent.start(pid,Chat(message='Read the current wall result',mode='provider'),background=False)
    assert not task['missing_deliveries']
    assert 'do not invent IDs' in task['events'][2]['error']


def test_numeric_delivery_and_other_missing_kind_remain_distinct(client,monkeypatch):
    pid=create_project(client)['project_id'];record=create_record(client,pid,'thermal');agent=client.app.state.agent
    scripted(agent,monkeypatch,[tool('thermal_read',{'thermal_id':record['thermal_id']}),batch([
        ('professional_deliver',{'delivery':delivery(record)}),('professional_missing',{'missing':{'kind':'cost','finish':True}})])])
    task=agent.start(pid,Chat(message='Read '+record['thermal_id']+' and check missing procurement record',mode='provider'),background=False)
    assert task['status']=='succeeded' and task['answer']['task_completion']=='partial'
    assert len(task['answer']['checked_statements'])==len(task['answer']['checked_missing'])==1


def test_explicit_unavailable_id_is_not_misrepresented_as_empty_kind(client,monkeypatch):
    pid=create_project(client)['project_id'];create_record(client,pid,'thermal');agent=client.app.state.agent
    ident='thermal_'+'1'*32
    scripted(agent,monkeypatch,[tool('professional_missing',{'missing':{'kind':'thermal','record_id':ident,'finish':True}})])
    task=agent.start(pid,Chat(message='Check this specific unavailable ID: '+ident,mode='provider'),background=False)
    receipt=task['answer']['checked_missing'][0]
    assert receipt['project_record_count']==1 and receipt['scope']=='requested_record_in_project'
    assert receipt['reason_code']=='record_not_available_in_project' and receipt['record_id']==ident


def test_malformed_missing_call_recovers_without_unbound_parser_state(client,monkeypatch):
    pid=create_project(client)['project_id'];agent=client.app.state.agent
    scripted(agent,monkeypatch,[tool('professional_missing',{'missing':{'kind':'invalid'}}),
        tool('professional_missing',{'missing':{'kind':'thermal','finish':True}})])
    task=agent.start(pid,Chat(message='Check missing wall',mode='provider'),background=False)
    assert task['status']=='succeeded' and task['recovery_attempts']==1
    assert len(task['answer']['checked_missing'])==1


def test_observed_empty_catalog_cannot_be_silently_dropped_on_numeric_finish(client,monkeypatch):
    pid=create_project(client)['project_id'];record=create_record(client,pid,'thermal');agent=client.app.state.agent
    scripted(agent,monkeypatch,[tool('professional_inventory',{'kinds':['thermal','cost']}),
        tool('thermal_read',{'thermal_id':record['thermal_id']}),tool('professional_deliver',{'delivery':{**delivery(record),'finish':True}}),
        tool('professional_missing',{'missing':{'kind':'cost','finish':True}})])
    task=agent.start(pid,Chat(message='Read thermal value and missing procurement scope',mode='provider'),background=False)
    assert task['status']=='succeeded' and task['early_finish_with_missing']==['cost']
    assert len(task['answer']['checked_statements'])==len(task['answer']['checked_missing'])==1


def test_free_prose_after_empty_inventory_receives_bounded_formal_delivery_reminder(client,monkeypatch):
    pid=create_project(client)['project_id'];agent=client.app.state.agent
    scripted(agent,monkeypatch,[tool('professional_inventory',{'kinds':['cost']}),
        {'role':'assistant','content':'No procurement records.'},tool('professional_missing',{'missing':{'kind':'cost','finish':True}})])
    task=agent.start(pid,Chat(message='Check missing procurement',mode='provider'),background=False)
    assert task['status']=='succeeded' and len(task['answer']['checked_missing'])==1
    assert any(e.get('missing_delivery_reminder')==['cost'] for e in task['events'])


def test_oversized_model_batch_executes_nothing_then_recovers_within_same_limits(client,monkeypatch):
    pid=create_project(client)['project_id'];agent=client.app.state.agent
    calls=[('professional_missing',{'missing':{'kind':k,'finish':True}}) for k in KINDS]
    first=[('professional_missing',{'missing':{'kind':k,'finish':False}}) for k in KINDS[:3]]
    scripted(agent,monkeypatch,[batch(calls),batch(first),batch(calls[3:])])
    task=agent.start(pid,Chat(message='Check all six kinds',mode='provider'),background=False)
    assert task['status']=='succeeded' and task['recovery_attempts']==1
    assert task['events'][1]['status']=='failed' and task['events'][1]['protocol_recovery']
    assert task['events'][2]['tool']=='llm.request'
    assert len(task['events'])==11 and len(task['answer']['checked_missing'])==6


def test_oversized_write_batches_are_never_partly_executed_or_retried(client,monkeypatch):
    pid=create_project(client)['project_id'];agent=client.app.state.agent
    oversized=batch([('simulation_create',{'scheme_id':'baseline'})]*5)
    scripted(agent,monkeypatch,[oversized,oversized,oversized])
    task=agent.start(pid,Chat(message='Invalid batched writes',mode='provider',allow_compute=True),background=False)
    assert task['status']=='failed' and task['recovery_attempts']==2
    assert not agent.store.jobs(pid) and all(e['tool'] in {'project_get','llm.request'} for e in task['events'])


def test_final_absence_recheck_reads_one_sqlite_snapshot_for_all_six_scopes(client,monkeypatch):
    from backend import agent_missing
    pid=create_project(client)['project_id'];domain=client.app.state.agent.domain
    references=[agent_missing.assess(domain,pid,Missing(kind=k))['reference'] for k in KINDS]
    original=domain.store.connect;statements=[];connections=[]
    def connect():
        con=original();connections.append(con);con.set_trace_callback(statements.append);return con
    monkeypatch.setattr(domain.store,'connect',connect)
    result=agent_missing.recheck(domain,pid,references)
    assert len(connections)==1 and len(result['checks'])==6 and all(c['passed'] for c in result['checks'])
    assert len([s for s in statements if s.startswith('SELECT')])==2


def test_unified_inventory_is_model_offered_but_legacy_lists_remain_for_explicit_inspections(client):
    agent=client.app.state.agent;names={t['function']['name'] for t in agent.tools()}
    assert 'professional_inventory' in names and not any(s.list_tool in names for s in INSPECTIONS.values())
    for spec in INSPECTIONS.values():
        assert spec.list_tool in {t['function']['name'] for t in agent.tools({spec.list_tool,spec.read_tool})}


def test_incomplete_final_recheck_cannot_silently_drop_a_requested_scope(client):
    from backend import agent_missing
    pid=create_project(client)['project_id'];domain=client.app.state.agent.domain
    references=[agent_missing.assess(domain,pid,Missing(kind=k))['reference'] for k in ['thermal','cost']]
    with pytest.raises(ValueError,match='Incomplete absence recheck'):
        agent_missing.attach({},domain,pid,references,reader=lambda:{'checks':[]})


def test_multiple_missing_scopes_are_one_atomic_read_with_all_scope_receipts(client,monkeypatch):
    pid=create_project(client)['project_id'];agent=client.app.state.agent
    original=agent.store.connect;connections=[];statements=[]
    def connect():
        con=original();connections.append(con);con.set_trace_callback(statements.append);return con
    monkeypatch.setattr(agent.store,'connect',connect)
    result=agent.call(pid,'professional_missing',{'missing':{'kinds':KINDS,'finish':True}},False)
    assert len(connections)==1 and len([s for s in statements if s.startswith('SELECT')])==2
    assert result['snapshot_count']==1 and len(result['references'])==len(result['missing'])==6
    assert [r['request']['kind'] for r in result['references']]==KINDS


def test_atomic_missing_delivery_fits_budget_without_hiding_suboperations(client,monkeypatch):
    pid=create_project(client)['project_id'];agent=client.app.state.agent
    scripted(agent,monkeypatch,[tool('professional_inventory',{'kinds':KINDS}),
        tool('professional_missing',{'missing':{'kinds':KINDS,'finish':True}})])
    task=agent.start(pid,Chat(message='Check all six project catalogs',mode='provider'),background=False)
    assert task['status']=='succeeded' and len(task['events'])==6
    assert len(task['answer']['checked_missing'])==6 and task['answer']['task_completion']=='incomplete'
    assert task['events'][4]['result']['snapshot_count']==task['events'][5]['result']['snapshot_count']==1


def test_atomic_missing_rejects_whole_selection_when_one_kind_exists(client,monkeypatch):
    pid=create_project(client)['project_id'];create_record(client,pid,'thermal');agent=client.app.state.agent
    scripted(agent,monkeypatch,[tool('professional_missing',{'missing':{'kinds':['cost','thermal'],'finish':True}}),
                               {'role':'assistant','content':'Read existing thermal record before proceeding.'}])
    task=agent.start(pid,Chat(message='Check availability',mode='provider'),background=False)
    assert not task['missing_deliveries'] and task['events'][2]['status']=='failed'
    assert 'Record available' in task['events'][2]['error']


@pytest.mark.parametrize('payload',[{'kinds':[]},{'kinds':['thermal','thermal']},
    {'kind':'thermal','kinds':['cost']},{'kinds':['thermal','cost'],'record_id':'thermal_'+'1'*32}])
def test_atomic_missing_selection_rejects_ambiguous_scope(payload):
    with pytest.raises(ValueError):Missing.model_validate(payload)


def test_existing_catalog_reminds_model_before_missing_only_finish(client,monkeypatch):
    pid=create_project(client)['project_id'];record=create_record(client,pid,'thermal');agent=client.app.state.agent
    scripted(agent,monkeypatch,[tool('professional_inventory',{'kinds':['thermal','cost']}),
        tool('professional_missing',{'missing':{'kind':'cost','finish':True}}),
        tool('thermal_read',{'thermal_id':record['thermal_id']}),
        tool('professional_deliver',{'delivery':{**delivery(record),'finish':True}})])
    task=agent.start(pid,Chat(message='Read thermal value and missing procurement scope',mode='provider'),background=False)
    assert task['status']=='succeeded' and task['available_delivery_reminded']==['thermal']
    assert len(task['answer']['checked_statements'])==len(task['answer']['checked_missing'])==1


def test_atomic_absence_history_rechecks_each_scope_after_one_kind_is_created(client,monkeypatch):
    pid=create_project(client)['project_id'];agent=client.app.state.agent
    scripted(agent,monkeypatch,[tool('professional_missing',{'missing':{'kinds':['thermal','cost','operation'],'finish':True}})])
    task=agent.start(pid,Chat(message='Check three missing kinds',mode='provider'),background=False)
    saved=agent.store.get('agent',task['agent_id'])
    create_record(client,pid,'thermal')
    current=agent.view(pid,task['agent_id'])
    assert [r['kind'] for r in current['answer']['checked_missing']]==['cost','operation']
    assert len(current['answer']['verification'])==3 and not current['answer']['verification'][0]['passed']
    assert agent.store.get('agent',task['agent_id'])==saved


def test_model_missing_schema_exposes_only_canonical_array_selector(client):
    definition=next(t for t in client.app.state.agent.tools() if t['function']['name']=='professional_missing')['function']['parameters']['$defs']['Missing']
    assert 'kind' not in definition['properties']
    assert definition['required']==['kinds']
    assert definition['properties']['kinds']['maxItems']==6


def test_canonical_single_kind_array_preserves_explicit_id_scope(client):
    pid=create_project(client)['project_id'];agent=client.app.state.agent;ident='thermal_'+'2'*32
    result=agent.call(pid,'professional_missing',{'missing':{'kinds':['thermal'],'record_id':ident,'finish':True}},False)
    assert result['missing'][0]['scope']=='requested_record_in_project' and result['missing'][0]['record_id']==ident


def test_explicit_requested_id_cannot_be_replaced_by_broad_empty_catalog(client,monkeypatch):
    pid=create_project(client)['project_id'];agent=client.app.state.agent;ident='thermal_'+'3'*32
    scripted(agent,monkeypatch,[tool('professional_missing',{'missing':{'kind':'thermal','finish':True}}),
        tool('professional_missing',{'missing':{'kind':'thermal','record_id':ident,'finish':True}})])
    task=agent.start(pid,Chat(message='Check this exact record '+ident,mode='provider'),background=False)
    assert task['events'][2]['status']=='failed' and task['recovery_attempts']==1
    assert task['answer']['checked_missing'][0]['record_id']==ident
