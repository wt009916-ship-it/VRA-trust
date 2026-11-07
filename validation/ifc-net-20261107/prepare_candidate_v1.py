"""Freeze worktree source into C temp; never copy original runtime or credentials."""
import hashlib,json,subprocess,tempfile,uuid
from pathlib import Path
repo=Path.cwd();out=Path(__file__).resolve().parent
root=Path(tempfile.gettempdir())/('vra-hourly-candidate-'+uuid.uuid4().hex)
root.mkdir()
names=set(subprocess.check_output(['git','ls-files','-z']).decode().split('\0'))
names.update(subprocess.check_output(['git','ls-files','--others','--exclude-standard','-z']).decode().split('\0'))
allowed=('backend/','tests/','scripts/','fixtures/','cases/','shared/','frontend/src/','frontend/tests/','frontend/legacy/tests/')
rows=[]
for name in sorted(names):
    if not name or not (name.startswith(allowed) or '/' not in name):continue
    p=repo/name
    if not p.is_file():continue
    raw=p.read_bytes();target=root/name
    assert target.resolve().is_relative_to(root.resolve())
    target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
    rows.append({'path':name,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)})
record={'root':str(root),'base_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        'source':'Worktree candidate, not a released commit','files':rows}
with (out/'candidate-source-v1.json').open('x',encoding='utf-8') as f:json.dump(record,f,indent=2)
print(json.dumps({'root':str(root),'files':len(rows)}))
