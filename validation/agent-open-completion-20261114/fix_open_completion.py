from pathlib import Path
p=Path('backend/agent_recovery.py');s=p.read_text(encoding='utf-8')
s=s.replace("from .agent_semantics import inspection", "from .agent_semantics import inspection\nfrom .agent_inspections import INSPECTIONS")
s=s.replace("    delivered={r['record_id']", """    # A successful model-selected leaf read also creates an observed target.
    # Catalog discovery is a read receipt, but has no delivered numeric facts.
    read_specs = {spec.read_tool: spec for spec in INSPECTIONS.values()}
    events = record['events']
    for event in events:
        spec = read_specs.get(event['tool'])
        if spec is None or event['status'] != 'succeeded':
            continue
        origin = event.get('origin')
        parent = event.get('parent_event')
        if parent is not None and 0 <= parent < len(events):
            origin = events[parent].get('origin')
        if origin != 'model':
            continue
        ident = event.get('result', {}).get(spec.record_key)
        if ident:
            selected.add(ident)
    delivered={r['record_id']""")
s=s.replace("    return sorted(selected-delivered)", """    delivered.update(r.get('record_id') for r in record.get('professional_reviews', []))
    return sorted(selected-delivered)""")
p.write_text(s,encoding='utf-8')
p=Path('tests/test_agent_metric_reads.py')
with p.open('a',encoding='utf-8') as f:f.write('''

def test_successful_catalog_read_cannot_be_dropped_on_early_finish(client,native,monkeypatch):
    from backend import agent_recovery
    pid,r,_=create_utility(client,native,monkeypatch)
    agent=client.app.state.agent
    wall=create_record(client,pid,'thermal')
    numeric=lambda kind,source,key:tool('professional_deliver',{'delivery':{
        'kind':kind,'record_id':source[kind+'_id'],'record_hash':source['hash'],
        'fact_keys':[key],'finish':True}})
    history=scripted(agent,monkeypatch,[
        tool('utility_comparison_read',{'utility_id':r['utility_id']}),
        tool('thermal_read',{'thermal_id':wall['thermal_id']}),
        numeric('thermal',wall,'u_w_m2k'),
        tool('utility_comparison_read',{'utility_id':r['utility_id'],'fact_keys':['cvrmse_percent']}),
        numeric('utility',r,'cvrmse_percent')])
    task=agent.start(pid,Chat(message='Read CV and wall U '+r['utility_id']+' '+wall['thermal_id'],
        mode='provider'),background=False)
    assert task['status']=='succeeded',task.get('error')
    assert task['early_finish_with_unresolved_reads']==[r['utility_id']]
    assert len(history)==5
    assert {row['record_id'] for row in task['answer']['checked_statements']}=={r['utility_id'],wall['thermal_id']}
    assert not agent_recovery.unresolved(task)
    assert len(task['events'])<=15


def test_controller_recheck_does_not_create_an_extra_model_selected_target():
    from backend import agent_recovery
    ident='utility_'+'a'*32
    record={'events':[{'tool':'utility_comparison_read','status':'succeeded',
        'origin':'controller','result':{'utility_id':ident}}]}
    assert agent_recovery.unresolved(record)==[]
    record['events'][0]['origin']='model'
    assert agent_recovery.unresolved(record)==[ident]
''')
