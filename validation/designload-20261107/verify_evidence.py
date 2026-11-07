"""Verify local evidence bytes and final production source without updating history."""
import hashlib, json, subprocess
from pathlib import Path

repo = Path.cwd()
data = json.loads((repo / 'docs/DESIGN_LOADS_EVIDENCE.json').read_text(encoding='utf-8'))
for row in data['evidence_files'] + data['publications']:
    raw = (repo / row['path']).read_bytes()
    assert len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256'], row['path']
snapshot = json.loads((repo / data['source_snapshot']).read_text())
for row in snapshot['files']:
    if row['path'].startswith(('backend/', 'frontend/', 'tests/', 'scripts/', 'shared/', 'cases/', 'fixtures/')):
        raw = (repo / row['path']).read_bytes()
        # Git may normalize the eight explicitly audited CRLF files at checkout.
        if hashlib.sha256(raw).hexdigest() != row['sha256']:
            audit = json.loads((repo / data['git_source_check']).read_text())
            match = next(x for x in audit['files'] if x['path'] == row['path'])
            assert row['path'] in audit['normalizations'] and hashlib.sha256(raw).hexdigest() == match['git_sha256'], row['path']
changed = subprocess.check_output(['git', 'diff', '--name-only', data['application_commit'], '--', 'backend', 'frontend/src',
                                  'frontend/tests', 'frontend/package.json', 'frontend/package-lock.json', 'tests', 'scripts', 'shared', 'cases', 'fixtures'], text=True).strip()
assert not changed, changed
print(json.dumps({'application_commit': data['application_commit'], 'verified_files': len(data['evidence_files']) + len(data['publications']), 'score': data['score']}))
