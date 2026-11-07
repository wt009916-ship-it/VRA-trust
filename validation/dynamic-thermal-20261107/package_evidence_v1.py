import hashlib,json,subprocess
from pathlib import Path
repo=Path.cwd();out=Path(__file__).resolve().parent
def entry(p):
    raw=p.read_bytes();return {'path':p.relative_to(repo).as_posix(),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
publications=[repo/'docs'/name for name in ['HOURLY_THERMAL_DELIVERY.md','HOURLY_THERMAL_CROSSCHECK.md','RESCORE_20261107_HOURLY_THERMAL.md']]
for p in publications:p.write_bytes(p.read_bytes().replace(b'\r\n',b'\n'))
files=[p for p in sorted(out.rglob('*')) if p.is_file() and p.suffix in {'.json','.md','.txt','.py','.js','.log','.idf','.err'} and p.name not in {'ui-server-v1.log'}]
data={'purpose':'Public evidence from actual native and browser tests; not a certification. Live server log excluded until shutdown.',
      'base_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
      'evidence_files':[entry(p) for p in files],'publications':[entry(p) for p in publications]}
(repo/'docs/HOURLY_THERMAL_EVIDENCE.json').write_bytes((json.dumps(data,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
user=repo/'.agents/skills/vra-trust/SKILL.md'
assert hashlib.sha256(user.read_bytes()).hexdigest()==json.loads((repo/'validation/drawing-enhancement-20261107/preserved-worktree-edit-v1.json').read_text())['sha256']
print(json.dumps({'evidence_files':len(files),'bytes':sum(p.stat().st_size for p in files),'unrelated_edit_preserved':True}))
