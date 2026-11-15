from pathlib import Path
import shutil
root=Path(__file__).parent;repo=Path('C:/Users/18483/AppData/Local/Temp/vra-timestep-reliability-20261108')
shutil.copy2(root/'agent_delivery_budget.py',repo/'backend/agent_delivery_budget.py')
p=repo/'backend/agent.py';s=p.read_text(encoding='utf-8')
old='from . import agent_read_execution, agent_standards';assert s.count(old)==1;s=s.replace(old,old+', agent_delivery_budget')
old="                    new_deliveries = sum(c['function']['name'] in {'professional_deliver','professional_limit','professional_missing','professional_review'} for c in calls)\n                    new_deliveries += 2*sum(c['function']['name']=='professional_compare' for c in calls)"
assert s.count(old)==1
s=s.replace(old,"                    new_deliveries = agent_delivery_budget.additional_reads(record,calls)\n                    new_deliveries += sum(c['function']['name']=='professional_missing' for c in calls)")
p.write_text(s,encoding='utf-8')
# Preserve the first model failure and the first harness before repairing None handling.
original=root/'live_acceptance.py';shutil.copy2(original,root/'live_acceptance_first.py')
s=original.read_text(encoding='utf-8').replace("out=BASE/'live-first';out.mkdir(exist_ok=False);runtime=BASE/'private-live-runtime'", "out=BASE/'live-after-budget';out.mkdir(exist_ok=False);runtime=BASE/'private-live-runtime-after-budget'")
s=s.replace("task.get('answer',{}).get(","(task.get('answer') or {}).get(").replace("current.get('answer',{}).get(","(current.get('answer') or {}).get(")
s=s.replace("'scope':'Six fresh development-side questions;", "'scope':'C01 regression after first real-model failure; C02-C06 first execution. Six frozen development-side questions;")
original.write_text(s,encoding='utf-8')
print('Corrected unique source recheck reservation; original event/turn limit unchanged')
