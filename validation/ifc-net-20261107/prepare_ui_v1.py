import hashlib,json,subprocess,sys
from pathlib import Path
out=Path(__file__).resolve().parent
s=(out/'prepare_candidate_v1.py').read_text().replace('candidate-source-v1.json','candidate-source-v2.json')
(out/'prepare_candidate_v2.py').write_text(s,encoding='utf-8')
subprocess.run([sys.executable,'-B',str(out/'prepare_candidate_v2.py')],check=True)
a=json.loads((out/'candidate-source-v1.json').read_text());b=json.loads((out/'candidate-source-v2.json').read_text())
old={r['path']:r['sha256'] for r in a['files']}
changes=[r['path'] for r in b['files'] if old.get(r['path'])!=r['sha256']]
assert changes==['frontend/src/ifc-ui.js','frontend/tests/ifc-opening-ui.test.js'],changes
source=(out.parent/'design-inputs-20261107/ui_launch_v1.py').read_text()
source=source.replace('candidate-source-v1.json','candidate-source-v2.json')
(out/'ui_launch_v1.py').write_text(source,encoding='utf-8')
subprocess.run([sys.executable,'-B',str(out/'ui_launch_v1.py')],check=True)
print(json.dumps({'backend_identical_to_full_regression':True,'changed':changes}))
