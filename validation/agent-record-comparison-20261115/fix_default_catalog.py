import hashlib,json,sys
from pathlib import Path
root=Path(__file__).parent;repo=Path('C:/Users/18483/AppData/Local/Temp/vra-timestep-reliability-20261108');sys.path.insert(0,str(repo))
from backend.agent import Agent,TOOLS
before=Agent.tools(None,set(TOOLS))
(root/'explicit-catalog-before.json').write_text(json.dumps(before,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('default_before_chars',len(json.dumps(Agent.tools(None),ensure_ascii=False)))
p=repo/'backend/agent.py';s=p.read_text(encoding='utf-8')
old="{'requested_output_plan', 'requested_availability', 'professional_review', 'requested_defer'}:continue"
new="{'requested_output_plan', 'requested_availability', 'professional_review', 'requested_defer', 'professional_compare'}:continue"
assert s.count(old)==1;s=s.replace(old,new)
s=s.replace('# Unscoped probes/catalogs never advertise compute tools. Task execution', '# Unscoped probes omit compute and comparisons requiring task read receipts. Task execution')
p.write_text(s,encoding='utf-8')
p=repo/'tests/test_local_model.py';s=p.read_text(encoding='utf-8');old='    assert not default & WRITE_TOOLS';assert s.count(old)==1
s=s.replace(old,old+"\n    assert 'professional_compare' not in default  # Requires current-task source reads; explicit catalogs retain it.")
p.write_text(s,encoding='utf-8')
print('Changed only unscoped catalog branch; explicit task selection and constraints unchanged')
