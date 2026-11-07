"""Archive only public synthetic test text; never include account DB/configuration."""
import gzip, hashlib, json, re, shutil
from pathlib import Path

out = Path(__file__).parent
repo = out.parents[1]
entries = []
cohorts = []
for receipt in sorted(out.glob('live-?b-v?.json')):
    data = json.loads(receipt.read_text(encoding='utf-8'))
    root = Path(data['root']).resolve()
    assert root.name in {'live-4b', 'live-8b'} and 'vra-designload-' in str(root)
    assert data['server_stopped'] and data['original_prototype_used'] is False
    wanted = {Path(x['path']).name: x['sha256'] for x in data['requests']}
    wanted.update({Path(x['task_path']).name: x['task_sha256'] for x in data['cases']})
    wanted['server.log'] = data['server_log_sha256']
    wanted['native-report.json'] = data['native_report_sha256']
    for name, expected in sorted(wanted.items()):
        assert re.fullmatch(r'(model-call-\d+\.json|DL-L\d+-task\.json|server\.log|native-report\.json)', name)
        path = root / name
        raw = path.read_bytes()
        assert len(raw) < 5_000_000 and hashlib.sha256(raw).hexdigest() == expected, str(path)
        text = raw.decode('utf-8')
        assert not re.search(r'(?i)"(?:password|csrf_token|access_token|api_key)"\s*:\s*"[^"\s]+"', text), name
        assert not re.search(r'(?:gh[pousr]_[A-Za-z0-9]{25,}|sk-[A-Za-z0-9]{30,})', text), name
        entries.append({'path': receipt.stem + '/' + name, 'sha256': expected, 'bytes': len(raw), 'text': text})
    cohorts.append({'receipt': receipt.name, 'commit': data['application_commit'], 'tasks': len(data['cases']),
                    'requests': len(data['requests']), 'automated_pass': sum(c['automated_pass'] for c in data['cases'])})
archive = out / 'model-public-text-v1.jsonl.gz'
with archive.open('xb') as stream, gzip.GzipFile(filename='', mode='wb', fileobj=stream, mtime=0) as gz:
    for entry in entries:
        gz.write((json.dumps(entry, ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf-8'))
with gzip.open(archive, 'rt', encoding='utf-8') as stream:
    recovered = [json.loads(line) for line in stream]
assert recovered == entries
browser = []
for folder in ['designload-20261107', 'designload-agent-20261107']:
    source = repo / 'output/playwright' / folder
    target = out / 'browser' / folder
    target.mkdir(parents=True, exist_ok=False)
    for path in sorted(source.iterdir()):
        assert path.is_file() and path.suffix in {'.json', '.png'}, path.name
        raw = path.read_bytes()
        if path.suffix == '.json':
            text = raw.decode('utf-8')
            assert not re.search(r'(?i)"(?:password|csrf_token|access_token|api_key)"\s*:\s*"[^"\s]+"', text), path.name
        shutil.copyfile(path, target / path.name)
        browser.append({'path': (target / path.name).relative_to(repo).as_posix(),
                        'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)})
record = {'archive': archive.relative_to(repo).as_posix(), 'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
          'bytes': archive.stat().st_size, 'files': [{k:v for k,v in x.items() if k != 'text'} for x in entries],
          'cohorts': cohorts, 'tasks': sum(c['tasks'] for c in cohorts), 'requests': sum(c['requests'] for c in cohorts),
          'browser': browser, 'scope': 'Public reference/synthetic data only; no account DB, configuration, credentials, native SQL or large downloads.'}
with (out / 'public-package-v1.json').open('x', encoding='utf-8') as stream:
    json.dump(record, stream, ensure_ascii=False, indent=2)
print(json.dumps({'archive_bytes': record['bytes'], 'text_files': len(entries), 'browser_files': len(browser), 'tasks': record['tasks'], 'requests': record['requests']}))
