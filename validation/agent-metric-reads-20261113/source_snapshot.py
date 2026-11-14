import hashlib,json,subprocess,shutil
from pathlib import Path
root=Path.cwd();out=root/'validation/agent-metric-reads-20261113';checks=[]
for folder in ('live-first','live-retry-b','live-repair-c'):
 receipt=json.loads((out/folder/'receipt.json').read_text(encoding='utf-8'))
 dest=out/'source-snapshots'/folder
 dest.mkdir(parents=True,exist_ok=True)
 for name,digest in receipt['product_sha256'].items():
  current=(root/name).read_bytes()
  candidates=[current,current.replace(b'\r\n',b'\n')]
  original=subprocess.run(['git','show','HEAD:'+name.replace(chr(92),'/')],capture_output=True).stdout
  candidates += [original,original.replace(b'\n',b'\r\n')]
  match=next((x for x in candidates if hashlib.sha256(x).hexdigest()==digest),None)
  checks.append({'run':folder,'path':name,'matched':match is not None})
  if match is not None:
   p=dest/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(match)
(out/'source-integrity.json').write_text(json.dumps(checks,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'checks':len(checks),'mismatches':[c for c in checks if not c['matched']]}))

