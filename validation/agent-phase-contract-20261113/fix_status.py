from pathlib import Path
root=Path('C:/Users/18483/AppData/Local/Temp/vra-timestep-reliability-20261108')
p=root/'backend/agent.py';s=p.read_text(encoding='utf-8').replace("if not any(not ds.artifact(r)['verified'] for ds,r in read_records):available.discard('professional_limit')", "if not any(not ds.artifact(r)['verified'] and r[ds.record_key] not in review_ids for ds,r in read_records):available.discard('professional_limit')")
s=s.replace("[(ds,r) for ds,r in read_records if not ds.artifact(r)['verified']]", "[(ds,r) for ds,r in read_records if not ds.artifact(r)['verified'] and r[ds.record_key] not in review_ids]")
p.write_text(s,encoding='utf-8')
p=root/'tests/test_agent_actions.py';s=p.read_text(encoding='utf-8')+'''

def test_status_only_plan_never_offers_numeric_limitation_substitute(client,monkeypatch):
    from backend import agent_reviews
    from test_agent_professional import thermal_input
    pid=create_project(client)['project_id'];a=client.app.state.agent
    body=thermal_input();body['rsi_m2k_w']=None;r=create_record(client,pid,'thermal',body)
    ref=agent_reviews.reference(r,'thermal')
    scripted(a,monkeypatch,[tool('requested_output_plan',{'output_plan':[plan(excerpt='Explain current source status.',facts=[],topics=['status'])]}),
        tool('thermal_read',{'thermal_id':r['thermal_id']}),tool('professional_review',{'review':{**ref,'finish':True}})])
    original=a.gateway.complete;offered=[]
    def capture(messages,tools,**options):
        offered.append({t['function']['name'] for t in tools});return original(messages,tools,**options)
    monkeypatch.setattr(a.gateway,'complete',capture)
    t=a.start(pid,Chat(message='Explain current source status.',mode='provider',read_execution='model',read_requests=[scope(r)]),background=False)
    assert t['status']=='succeeded',t.get('error')
    assert 'professional_review' in offered[2] and 'professional_limit' not in offered[2]
    assert not t['answer'].get('checked_statements') and t['answer']['output_contract_coverage']=='fulfilled'
''';p.write_text(s,encoding='utf-8')
p=root/'validation/agent-phase-contract-20261113/live_acceptance.py';s=p.read_text(encoding='utf-8')
s=s.replace("out=BASE/'live-repair'","out=BASE/'live-status-fix'").replace('vra-agent-phase-actions-live-20261113-c','vra-agent-phase-actions-live-20261113-e')
s=s.replace("   frozen_tasks={'tasks':tasks", "   tasks=[task for task in tasks if task['id']=='A08']\n   frozen_tasks={'repair_scope':'A08 status-only action-schema regression; original twelve-task assessment retained','tasks':tasks")
s=s.replace("'minimum_complete':11,'total':12", "'minimum_complete':1,'total':1")
(p.parent/'repair_status.py').write_text(s,encoding='utf-8')
print('Status-only output plan offers source review rather than a forbidden numeric-limitation action.')
