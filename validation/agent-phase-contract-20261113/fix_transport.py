from pathlib import Path
root=Path('C:/Users/18483/AppData/Local/Temp/vra-timestep-reliability-20261108');p=root/'backend/agent_actions.py';s=p.read_text(encoding='utf-8')
s=s.replace("    result={'messages':[{'role':'system','content':instruction},*messages],", "    leading=[];remaining=list(messages)\n    while remaining and remaining[0].get('role')=='system':leading.append(remaining.pop(0).get('content') or '')\n    # The supported local chat template accepts exactly one leading system message.\n    wire_messages=[{'role':'system','content':'\\n\\n'.join([instruction,*leading])},*remaining]\n    result={'messages':wire_messages,")
p.write_text(s,encoding='utf-8')
p=root/'tests/test_agent_actions.py';s=p.read_text(encoding='utf-8')+'''

def test_action_payload_consolidates_existing_system_context_for_local_template():
    messages=[{'role':'system','content':'Scope and permissions'},{'role':'system','content':'Current task state'},{'role':'user','content':'Read R'}]
    before=copy.deepcopy(messages);wire=agent_actions.payload(messages,simple_tools(),strict=True)
    assert messages==before
    assert [m['role'] for m in wire['messages']]==['system','user']
    assert 'Scope and permissions' in wire['messages'][0]['content'] and 'Current task state' in wire['messages'][0]['content']
    assert wire['messages'][1]==messages[-1]
''';p.write_text(s,encoding='utf-8')
p=root/'validation/agent-phase-contract-20261113/live_acceptance.py';s=p.read_text(encoding='utf-8');(p.parent/'live-final/failed-runner.py').write_text(s,encoding='utf-8')
s=s.replace("out=BASE/'live-final'","out=BASE/'live-repair'").replace('vra-agent-phase-actions-live-20261113-b','vra-agent-phase-actions-live-20261113-c')
p.write_text(s,encoding='utf-8')
print('Single leading system-message transport fix; original twelve failed tasks retained, no semantic prompt tuning.')
