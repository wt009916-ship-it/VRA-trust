import json
from pathlib import Path
b=Path('C:/Users/18483/AppData/Local/Temp/vra-timestep-reliability-20261108/validation/agent-phase-contract-20261113/live-repair')
for p in sorted(b.glob('*-task.json')):
 t=json.loads(p.read_text(encoding='utf-8'));a=t.get('answer') or {}
 print(json.dumps({'id':p.stem,'status':t['status'],'completion':a.get('task_completion'),'coverage':a.get('output_contract_coverage'),'error':t.get('error'),'events':[{'tool':e['tool'],'status':e['status'],**({'args':e.get('arguments'),'error':e.get('error')} if e['tool']!='llm.request' else {})} for e in t['events']],'checked':[{k:v for k,v in r.items() if k in ['kind','record_id','facts']} for r in a.get('checked_statements',[])],'capability':a.get('capability_assessments'),'deferral':a.get('question_deferral') or t.get('read_deferrals'),'outputs':a.get('requested_outputs')},ensure_ascii=False))
