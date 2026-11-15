import hashlib
import json
from pathlib import Path

BASE = Path(__file__).parent
ROOT = Path('D:/稀土agent-稀土制暖全流程/.codex_work/vra-resource-leveling-20261115')
files = ['backend/drawings.py', 'backend/drawing_worker.py', 'backend/drawing_processing.py',
         'backend/drawing_linework.py', 'backend/drawing_line_reviews.py', 'backend/parser_runtime.py',
         'backend/extensions.py']
out = BASE/'public-v1-source-snapshot'
out.mkdir(exist_ok=False)
hashes = {}
for name in files:
    raw = (ROOT/name).read_bytes()
    target = out/name
    target.parent.mkdir(exist_ok=True)
    target.write_bytes(raw)
    hashes[name] = hashlib.sha256(raw).hexdigest()
frozen = json.loads((BASE/'public-frozen.json').read_text(encoding='utf-8'))
assert hashes['backend/drawing_linework.py'] == frozen['linework_sha256']
(out/'receipt.json').write_text(json.dumps({'captured': 'after completed public-v1, before subsequent edits', 'sha256': hashes}, indent=2)+'\n', encoding='utf-8')
# Canonical source line endings specified by the repository; no semantic edit.
normalized = []
for name in ['backend/agent.py', 'backend/extensions.py', 'backend/parser_runtime.py']:
    path = ROOT/name
    raw = path.read_bytes()
    after = raw.replace(b'\r\n', b'\n')
    if after != raw:
        path.write_bytes(after)
        normalized.append(name)
(BASE/'line-ending-normalization.json').write_text(json.dumps({'only_crlf_to_lf': normalized}, indent=2)+'\n', encoding='utf-8')
print(json.dumps({'snapshotted_files': len(files), 'canonicalized_files': normalized}))
