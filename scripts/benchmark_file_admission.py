"""Exercise actual file admission in a fresh isolated runtime; no source conversion."""
import argparse
import json
import os
from pathlib import Path
import secrets
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--file', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    if out.exists() or out.is_relative_to(ROOT):
        parser.error('Use a new directory outside the checkout')
    out.mkdir(parents=True)
    os.environ['VRA_DATA_DIR'] = str(out/'bootstrap')
    from backend import core
    from backend.api import create_app
    from fastapi.testclient import TestClient
    path = args.file.resolve()
    app = create_app(out/'runtime', start_worker=False)
    with TestClient(app) as client:
        auth = client.post('/api/auth/register', json={'username': 'file_acceptance',
            'password': 'Admission-'+secrets.token_urlsafe(24), 'display_name': 'Isolated file acceptance'})
        assert auth.status_code == 200, auth.text
        client.headers['X-CSRF-Token'] = auth.json()['csrf_token']
        project = client.post('/api/projects', json={'name': path.name+' file admission test',
            'data_nature': 'engineering_reference', 'building': {'use': 'unverified source',
            'location': 'unverified source', 'region': 'unknown', 'area_m2': 80}})
        assert project.status_code == 201, project.text
        started = time.monotonic()
        response = client.post('/api/projects/'+project.json()['project_id']+'/files',
                               files={'file': (path.name, path.read_bytes())})
        with app.state.domain.store.connect() as con:
            jobs = con.execute('SELECT COUNT(*) FROM jobs').fetchone()[0]
            files = con.execute("SELECT COUNT(*) FROM records WHERE kind='file'").fetchone()[0]
        result = {'filename': path.name, 'bytes': path.stat().st_size, 'sha256': core.sha(path),
                  'upload_http': response.status_code, 'response': response.json(),
                  'seconds': round(time.monotonic()-started, 3), 'jobs': jobs, 'stored_files': files,
                  'annual_metrics': None, 'scope': 'File admission only; no conversion or thermal validation',
                  'tested_at': core.now()}
        core.write_json(out/'results.json', result)
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
