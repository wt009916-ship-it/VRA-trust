"""Install already accepted assets only after exact tested commit is merged."""
import hashlib,json,subprocess
from pathlib import Path
repo=Path.cwd();base=Path(__file__).resolve().parent
merge=json.loads((base/'merge-receipt.json').read_text());head=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
assert head==merge['merge_sha']
assert subprocess.check_output(['git','rev-parse','HEAD^{tree}'],text=True)==subprocess.check_output(['git','rev-parse',merge['tested_head']+'^{tree}'],text=True)
snapshot=json.loads((base/'windows-source-v2.json').read_text())
for row in snapshot['files']:
 if row['path'].startswith('frontend/'):
  assert hashlib.sha256((repo/row['path']).read_bytes()).hexdigest()==row['sha256']
dist=Path(json.loads((base/'browser-prepared-v2.json').read_text())['source'])/'frontend/dist';records=[]
for p in dist.rglob('*'):
 if p.is_file():
  raw=p.read_bytes();relative=p.relative_to(dist);target=repo/'frontend/dist'/relative
  target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
  records.append({'path':relative.as_posix(),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
(base/'released-assets.json').write_text(json.dumps({'main':head,'source':str(dist),'files':records,'old_assets_deleted':False},indent=2),encoding='utf-8')
print(json.dumps({'assets':len(records),'main':head}))
