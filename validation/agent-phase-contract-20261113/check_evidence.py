import json,hashlib
from pathlib import Path
b=Path('C:/Users/18483/AppData/Local/Temp/vra-timestep-reliability-20261108/validation/agent-phase-contract-20261113')
findings=[];count=0
sensitive={'password','api_key','access_token','csrf_token','authorization','llama_api_key','vra_local_model_token'}
def scan(value,path):
 if isinstance(value,dict):
  for key,item in value.items():
   if key.lower() in sensitive and item not in (None,'',False):findings.append(str(path)+':'+key)
   scan(item,path)
 elif isinstance(value,list):
  for item in value:scan(item,path)
for p in b.rglob('*.json'):
 scan(json.loads(p.read_text(encoding='utf-8')),p.relative_to(b));count+=1
assert not findings,findings
print('Structured credential-field scan passed:',count,'JSON files. No values printed.')
for name in ['live-first','live-final','live-repair','live-deferral-fix','live-status-fix']:
 p=b/name/'receipt.json';r=json.loads(p.read_text(encoding='utf-8'));assert r['processes_stopped']
 print(name,'owned processes stopped; task count',len(r['tasks']))
