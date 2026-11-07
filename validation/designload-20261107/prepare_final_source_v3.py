import hashlib, json, subprocess, sys, tempfile, uuid
from pathlib import Path
repo = Path(__file__).resolve().parents[2]; out = Path(__file__).parent
assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip() == 'b08548cbe98c06a2cf5a1c583cff58a867aaa937'
sys.path.insert(0, str(repo))
from backend.private_storage import private_mkdir
base = private_mkdir(Path(tempfile.gettempdir()) / ('vra-designload-final-' + uuid.uuid4().hex))
root = base / 'source'; root.mkdir()
prior = json.loads((out / 'integration-source-v1.json').read_text())
names = {r['path'] for r in prior['files']} | {'backend/agent_simulation.py', 'tests/test_agent_simulation.py', 'scripts/verify_design_load_analytic.py'}
records = []
for name in sorted(names):
    raw = (repo / name).read_bytes(); target = root / name
    target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(raw)
    records.append({'path': name, 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)})
record = {'base': str(base), 'root': str(root), 'application_commit': 'b08548cbe98c06a2cf5a1c583cff58a867aaa937', 'files': records}
with (out / 'final-source-v3.json').open('x', encoding='utf-8') as handle: json.dump(record, handle, indent=2)
print(json.dumps({'base': str(base), 'files': len(records)}))
