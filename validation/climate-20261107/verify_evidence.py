import hashlib,json,subprocess
from pathlib import Path
repo=Path.cwd();data=json.loads((repo/'docs/WEATHER_QUALITY_EVIDENCE.json').read_text(encoding='utf-8'))
for record in data['evidence_files']+data['publications']:
    path=repo/record['path'];raw=path.read_bytes()
    assert len(raw)==record['bytes'] and hashlib.sha256(raw).hexdigest()==record['sha256'],record['path']
for snapshot in data['source_snapshots']:
    for record in snapshot['files']:
        if record['path'].startswith(('backend/','frontend/','tests/')) or record['path']=='scripts/verify_weather_reference.py':
            assert hashlib.sha256((repo/record['path']).read_bytes()).hexdigest()==record['sha256'],record['path']
changed=subprocess.check_output(['git','diff','--name-only',data['application_commit'],'--','backend','frontend/src','frontend/tests','tests','scripts/verify_weather_reference.py'],text=True).strip()
assert not changed,changed
print(json.dumps({'application_commit':data['application_commit'],'verified_files':len(data['evidence_files'])+len(data['publications']),'score':data['score']}))
