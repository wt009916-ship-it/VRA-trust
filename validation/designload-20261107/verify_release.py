"""Verify merge, exact test head, public evidence, current runtime and original business data."""
import hashlib, json, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

out = Path('validation/designload-20261107')
verified = json.loads(subprocess.check_output([sys.executable, str(out / 'verify_evidence.py')], text=True, encoding='utf-8'))
index = json.loads(Path('docs/DESIGN_LOADS_EVIDENCE.json').read_text(encoding='utf-8'))
merge = json.loads((out / 'merge-receipt.json').read_text())
ci = json.loads((out / 'final-remote-receipt.json').read_text())
runtime = json.loads((out / 'runtime-after.json').read_text())
assets = json.loads((out / 'served-assets-verified.json').read_text())

def git(*args):
    return subprocess.check_output(['git', *args], text=True).strip()

head = git('rev-parse', 'HEAD')
assert head == merge['merge_sha'] == git('rev-parse', 'github/main')
assert ci['head'] == merge['tested_head'] == (out / 'release-head.txt').read_text().strip()
assert git('rev-parse', 'HEAD^{tree}') == git('rev-parse', ci['head'] + '^{tree}')
assert len(ci['checks']) == 6 and all(c['conclusion'] == 'success' for c in ci['checks'])
for row in ci['backend_logs']:
    raw = Path(row['path']).read_bytes()
    assert len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256']
# Check transported immutable evidence, not only the local working files.
for row in index['evidence_files'] + index['publications']:
    blob = subprocess.check_output(['git', 'show', head + ':' + row['path']])
    assert hashlib.sha256(blob).hexdigest() == row['sha256'], row['path']
assert not git('status', '--porcelain')
assert runtime['test_ports_released'] and runtime['active_original_tasks'] == 0
assert runtime['original_tables'] == json.loads((out / 'runtime-before.json').read_text())['original_tables']
pointer_hash = hashlib.sha256(Path('validation/reference_comparison.json').read_bytes()).hexdigest()
assert pointer_hash == '6b92a42d0002949fb099c186755984558e422afc18534810412aef9eb1947e4d'
plan = json.loads((out / 'prototype-prepared-v1.json').read_text())
for row in plan['source_files']:
    assert hashlib.sha256((Path(plan['source']) / row['path']).read_bytes()).hexdigest() == row['sha256'], row['path']
record = {'verified_at': datetime.now(timezone.utc).isoformat(), 'pr': merge['pr'], 'main': head,
          'tested_head': ci['head'], 'application_commit': verified['application_commit'],
          'verified_files': verified['verified_files'] + len(ci['backend_logs']), 'clean': True,
          'merged_tree_equals_tested_tree': True, 'evidence_git_bytes_verified': True,
          'score': 76, 'prior_score': 75, 'goal': 'active', 'training': False,
          'original_reference_pointer_sha256': pointer_hash, 'original_data_unchanged': runtime['original_tables'],
          'prototype_health': runtime['health'], 'prototype_restarted': True, 'served_assets': assets,
          'ci_backend_runs': ci['backend_logs'], 'regression': index['regression'],
          'next_work': 'Drawing source preservation, deterministic deskew/noise candidates, scale conflict and independent unseen fixtures; dynamic/design-source applicability remains open.',
          'unresolved': ['4B stale recovery', 'model prose misattribution', 'mixed tasks and general injection',
                         'CPU probe ordering', 'net quantities and DWG/conversion', 'real-building/expert and production acceptance', 'global UI readability']}
with (out / 'release-receipt.json').open('x', encoding='utf-8') as stream:
    json.dump(record, stream, indent=2)
print(json.dumps({k:v for k,v in record.items() if k not in {'served_assets', 'ci_backend_runs', 'original_data_unchanged'}}))
