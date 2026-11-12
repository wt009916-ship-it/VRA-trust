import json,hashlib
from pathlib import Path
ROOT=Path('C:/Users/18483/AppData/Local/Temp/vra-timestep-reliability-20261108');BASE=ROOT/'validation/agent-phase-contract-20261113';B=BASE/'live-repair';calls=B/'model-calls'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
rows=[]
for n in [7,8,23]:
 p=calls/('model-call-%03d.json'%n);d=read(p)
 rows.append({'call':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'schemas':{t['function']['name']:t['function']['parameters'] for t in d['tools'] if t['function']['name'] in {'utility_comparison_read','professional_read_many'}}})
t=read(B/'A06-task.json');plan=t['output_plan']['items']
r={'basis':'Original raw request schemas and frozen task, not inference about internal model thoughts','read_schema_evidence':rows,'repeated_catalog_calls_in_A03':sum(e['tool']=='professional_read_many' for e in read(B/'A03-task.json')['events']),'A06_question':read(B/'frozen-tasks.json')['tasks'][5]['message'],'A06_selected_explanations':{i['request_key']:i['explanation_topics'] for i in plan},'confirmed_gaps':['Read fact_keys schema has unconstrained string items despite available domain catalog','professional_read_many accepts record_ids only; it cannot request energy fact keys','Relationship requirement absent from model output plan; current topic coverage cannot detect missing question obligation'],'next_batch':'docs/AGENT_METRIC_READ_PLAN.md'}
(BASE/'next-metric-diagnostic.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('Saved exact request-schema diagnostic; no old model tasks rerun.')
