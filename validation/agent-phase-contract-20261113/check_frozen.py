import json,re
from pathlib import Path
b=Path('C:/Users/18483/AppData/Local/Temp/vra-timestep-reliability-20261108/validation/agent-phase-contract-20261113')
def read(name):return json.loads((b/name/'frozen-tasks.json').read_text(encoding='utf-8'))['tasks']
def canonical(task):
 s=json.dumps(task,sort_keys=True,ensure_ascii=False)
 return re.sub(r'(?<![A-Za-z0-9_])(project|thermal|lifecycle|enduse|utility|run|evidence|agent|user)_[a-f0-9]{32}(?![A-Za-z0-9_])',r'\1_<runtime_id>',s)
a=read('live-final');c=read('live-repair');assert len(a)==len(c)==12
assert all(canonical(x)==canonical(y) for x,y in zip(a,c))
for stage,ident in [('live-deferral-fix','A06'),('live-status-fix','A08')]:
 selected=read(stage);assert len(selected)==1
 assert canonical(selected[0])==canonical(next(t for t in c if t['id']==ident))
print('Frozen task/expectation equality verified: transport repair12/12; bounded A06/A08 unchanged apart from ephemeral source IDs. No semantic question tuning.')
