from pathlib import Path
root=Path('C:/Users/18483/AppData/Local/Temp/vra-timestep-reliability-20261108')
p=root/'backend/agent.py';s=p.read_text(encoding='utf-8').replace("if call['function']['name']=='requested_defer':finish_requested |= result['finish']", "if call['function']['name']=='requested_defer' and result.get('status')=='needs_clarification':finish_requested |= result['finish']");p.write_text(s,encoding='utf-8')
p=root/'tests/test_agent_actions.py';s=p.read_text(encoding='utf-8')+'''

def test_failed_defer_after_delivery_in_same_batch_is_recoverable(client,monkeypatch):
    pid=create_project(client)['project_id'];a=client.app.state.agent;r=create_record(client,pid,'thermal')
    delivery=tool('professional_deliver',{'delivery':{**selected(r),'finish':False}})
    defer=tool('requested_defer',{'request_keys':['wall']})
    mixed={'role':'assistant','tool_calls':delivery['tool_calls']+defer['tool_calls']}
    mixed['tool_calls'][1]['id']='defer_after_delivery'
    scripted(a,monkeypatch,[tool('thermal_read',{'thermal_id':r['thermal_id']}),mixed,tool('professional_deliver',{'delivery':selected(r)})])
    t=a.start(pid,Chat(message='Read R',mode='provider',infer_outputs=False,read_requests=[scope(r)]),background=False)
    assert t['status']=='succeeded',t.get('error')
    failed=next(e for e in t['events'] if e['tool']=='requested_defer')
    assert failed['status']=='failed' and 'pending' in failed['error']
    assert t['answer']['checked_statements'][0]['facts'][0]['value']=='1.97'
    assert not t.get('read_deferrals')
''';p.write_text(s,encoding='utf-8')
p=root/'validation/agent-phase-contract-20261113/live_acceptance.py';s=p.read_text(encoding='utf-8');(p.parent/'live-repair/executed-runner.py').write_text(s,encoding='utf-8')
s=s.replace("out=BASE/'live-repair'","out=BASE/'live-deferral-fix'").replace('vra-agent-phase-actions-live-20261113-c','vra-agent-phase-actions-live-20261113-d')
s=s.replace("   frozen_tasks={'tasks':tasks", "   tasks=[task for task in tasks if task['id']=='A06']\n   frozen_tasks={'repair_scope':'A06 controller state-change regression only; not a fresh semantic acceptance and does not replace the original twelve-task result','tasks':tasks")
s=s.replace("'minimum_complete':11,'total':12", "'minimum_complete':1,'total':1")
(p.parent/'repair_deferral.py').write_text(s,encoding='utf-8')
print('Guarded failed defer result; prepared one bounded regression, original semantic failure remains.')
