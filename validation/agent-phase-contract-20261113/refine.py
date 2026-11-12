exec(open('D:/稀土agent-稀土制暖全流程/outputs/agent-phase-20261113/implement.py',encoding='utf-8').read().split("(ROOT/'backend/agent_actions.py')")[0])
edit('backend/agent.py',"deferrable = [r.request_key for r in body.read_requests if r.request_key in waiting and not r.output_contract]", "deferrable = [r.request_key for r in body.read_requests if r.purpose=='results' and r.request_key in waiting and not r.output_contract]")
edit('backend/agent.py',"allowed={r.request_key for r in body.read_requests if r.request_key in requested_scopes.pending(record) and not r.output_contract}", "allowed={r.request_key for r in body.read_requests if r.purpose=='results' and r.request_key in requested_scopes.pending(record) and not r.output_contract}")
edit('tests/test_agent_energy.py',"assert [f['fact'] for f in second['available_facts']]==['native_hours']", "assert second['available_fact_keys']==['native_hours'] and 'available_facts' not in second")
edit('tests/test_agent_energy.py', 'def test_energy_delivery_schema_requires_context_after_actual_read', 'def test_energy_delivery_schema_selects_receipt_instead_of_copying_context')
edit('tests/test_agent_energy.py',"    statement=schema['$defs']['Statement']\n    assert 'energy_context' in statement['required']\n    assert statement['properties']['energy_context']=={'$ref':'#/$defs/EnergyContext'}", "    selected=schema['properties']['delivery']['oneOf'][0]['properties']\n    assert selected['fact_keys']['items']['enum']==['interval_count']\n    assert selected['record_hash']['const']==r['hash']\n    assert 'statements' not in selected and 'energy_context' not in selected\n    assert task['answer']['checked_statements'][0]['facts'][0]['energy_context']['native_year']==2019")
with (ROOT/'tests/test_agent_energy.py').open('a',encoding='utf-8') as f:
 f.write('''

def test_actual_energy_receipt_materializes_context_and_catalog_alone_cannot_deliver(client,native,monkeypatch):
    from backend.agent_selections import materialize
    pid,r,_=create_utility(client,native,monkeypatch);agent=client.app.state.agent
    selected={'kind':'utility','record_id':r['utility_id'],'record_hash':r['hash'],'fact_keys':['mbe_percent'],'finish':True}
    catalog=agent.call(pid,'utility_comparison_read',{'utility_id':r['utility_id']},False)
    with pytest.raises(core.ValidationError,match='catalog'):
        materialize({'events':[{'tool':'utility_comparison_read','status':'succeeded','result':catalog}]},selected)
    scripted(agent,monkeypatch,[tool('utility_comparison_read',{'utility_id':r['utility_id'],'fact_keys':['mbe_percent']}),tool('professional_deliver',{'delivery':selected})])
    task=agent.start(pid,Chat(message='Read bias',mode='provider',infer_outputs=False,read_requests=[{'request_key':'r','kind':'utility','purpose':'results','record_id':r['utility_id']}]),background=False)
    assert task['status']=='succeeded',task.get('error')
    fact=task['answer']['checked_statements'][0]['facts'][0]
    assert fact['energy_context']==facts(r,'utility')[2]['energy_context']
    assert fact['energy_context']['native_year']==2019 and fact['study_years'] is None and fact['area_m2'] is None


def test_energy_receipt_never_revives_source_withdrawn_after_read(client,native,monkeypatch):
    pid,r,snapshot=create_utility(client,native,monkeypatch);agent=client.app.state.agent
    selection={'kind':'utility','record_id':r['utility_id'],'record_hash':r['hash'],'fact_keys':['mbe_percent'],'finish':True}
    scripted(agent,monkeypatch,[tool('utility_comparison_read',{'utility_id':r['utility_id'],'fact_keys':['mbe_percent']}),tool('professional_deliver',{'delivery':selection})])
    original=agent.gateway.complete;count=0
    def withdraw(*args,**kwargs):
        nonlocal count
        count+=1
        if count>1:snapshot['sql_sha256']='withdrawn'
        return original(*args,**kwargs)
    monkeypatch.setattr(agent.gateway,'complete',withdraw)
    task=agent.start(pid,Chat(message='Read bias',mode='provider',infer_outputs=False,read_requests=[{'request_key':'r','kind':'utility','purpose':'results','record_id':r['utility_id']}]),background=False)
    assert not (task.get('answer') or {}).get('checked_statements') and not task['professional_deliveries']
    assert any(e['tool']=='professional_deliver' and e['status']=='failed' for e in task['events'])
''')
print('Restricted defer to unresolved metrics; old energy tests now verify receipt schema and context preservation')
