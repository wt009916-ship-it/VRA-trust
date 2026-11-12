import json,hashlib
from pathlib import Path
root=Path('C:/Users/18483/AppData/Local/Temp/vra-timestep-reliability-20261108');base=root/'validation/agent-output-contract-20261113'
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
call=read(base/'live-first/model-calls/model-call-008.json')
tools=[t['function']['name'] for t in call['tools']]
messages=[]
for msg in call['messages']:
 if msg['role']=='tool':
  content=json.loads(msg['content']);messages.append({'keys':list(content),'numeric_fact_count':len(content.get('explanation_facts',[])),'selected_fact_keys':content.get('selected_fact_keys')})
assert 'professional_deliver' not in tools
assert any(m['numeric_fact_count']==0 for m in messages)
row={'observed_failure':'D02, model-call-008','offered_tools':tools,'tool_message_summaries':messages,
     'raw_response_has_false_formal_delivery':'正式交付' in call['response']['content'],
     'code_evidence':{'local_model_tool_choice_auto':"'tool_choice': 'auto'" in (root/'backend/local_model.py').read_text(encoding='utf-8'),
                      'provider_tool_choice_auto':"'tool_choice': 'auto'" in (root/'backend/gateway.py').read_text(encoding='utf-8')},
     'interpretation':'Numeric delivery tool was already withheld until a selected numeric read. The remaining flaw is unconstrained raw model prose while the execution phase still requires a read; merely withholding the delivery tool did not prevent false prose.',
     'next_design':'Verify phase-specific constrained tool responses and current read receipts; preserve raw generations. Do not only add another instruction or enlarge budgets. Direct requested-metric selection and relationship explanation remain independent semantic tests.'}
(base/'next-phase-diagnostic.json').write_text(json.dumps(row,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(row,ensure_ascii=False))
