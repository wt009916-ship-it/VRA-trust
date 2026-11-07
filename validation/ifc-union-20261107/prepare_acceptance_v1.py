from pathlib import Path
out=Path('validation/ifc-union-20261107');old=Path('validation/ifc-net-20261107')
s=(old/'prepare_candidate_v1.py').read_text(encoding='utf-8')
s=s.replace("or '/' not in name","or '/' not in name or (name.startswith('frontend/') and name.count('/')==1)")
(out/'prepare_candidate_v1.py').write_text(s,encoding='utf-8',newline='\n')
s=(old/'linux_candidate_v1.py').read_text(encoding='utf-8').replace("'design-source-'","'union-source-'")
(out/'linux_candidate_v1.py').write_text(s,encoding='utf-8',newline='\n')
s=(old/'ui_launch_v1.py').read_text(encoding='utf-8').replace('candidate-source-v2.json','candidate-source-v1.json')
(out/'ui_launch_v1.py').write_text(s,encoding='utf-8',newline='\n')
