"""Prepare an immutable public-source runtime; original business data stay in place."""
import hashlib, json, os, tempfile, uuid
from pathlib import Path

out = Path(__file__).parent.resolve()
snapshot = json.loads((out / 'final-source-v6.json').read_text())
assets = json.loads((out / 'git-assets-v5.json').read_text())
assert snapshot['application_commit'] == assets['candidate']
source = Path(snapshot['root'])
root = Path(tempfile.gettempdir()) / ('vra-designload-prototype-' + uuid.uuid4().hex)
root.mkdir()
for row in snapshot['files']:
    raw = (source / row['path']).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == row['sha256'], row['path']
    target = root / row['path']
    assert target.resolve().is_relative_to(root.resolve())
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
for name, digest in assets['assets'].items():
    raw = (Path(assets['root']) / 'frontend/dist' / name).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == digest
    target = root / 'frontend/dist' / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
record = {'application_commit': snapshot['application_commit'], 'source': str(root),
          'source_files': snapshot['files'], 'assets': assets['assets'],
          'business_data': str(out.parents[1] / 'validation/thermal-20261104/ui-runtime'),
          'runtime_started': False, 'original_data_copied': False}
with (out / 'prototype-prepared-v1.json').open('x', encoding='utf-8') as stream:
    json.dump(record, stream, indent=2)
print(json.dumps({'source': str(root), 'files': len(snapshot['files']), 'assets': len(assets['assets'])}))
