import hashlib, json, urllib.request
from pathlib import Path

out = Path(__file__).parent
plan = json.loads((out / 'prototype-prepared-v1.json').read_text())
merge = json.loads((out / 'merge-receipt.json').read_text())
checks = []
for path, digest in plan['assets'].items():
    url = '/' if path == 'index.html' else '/' + path
    with urllib.request.urlopen('http://127.0.0.1:18772' + url, timeout=10) as response:
        raw = response.read()
    assert hashlib.sha256(raw).hexdigest() == digest, path
    checks.append({'url_path': url, 'sha256': digest})
record = {'main': merge['merge_sha'], 'application_commit': plan['application_commit'], 'verified': checks,
          'source': plan['source'], 'browser_assets_match': True}
with (out / 'served-assets-verified.json').open('x', encoding='utf-8') as stream:
    json.dump(record, stream, indent=2)
print(json.dumps({'served_assets_verified': len(checks), 'main': merge['merge_sha']}))
