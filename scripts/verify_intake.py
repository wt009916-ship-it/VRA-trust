"""Repeat source-first intake with supplied public IFCs; no customer data bundled."""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fastapi.testclient import TestClient
from backend.api import create_app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--duplex', type=Path, required=True)
    parser.add_argument('--difficult', type=Path, required=True)
    parser.add_argument('--data-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.data_root.exists():
        raise SystemExit('Use a new isolated directory. Existing accounts must not be changed.')
    app = create_app(args.data_root, start_worker=False)
    results = {'scope': 'Real file parsing and workflow integration; synthetic project declarations, no calibration or energy run.', 'cases': []}
    with TestClient(app) as client:
        session = client.post('/api/auth/register', json={'username':'intake_test','display_name':'隔离验收账号','password':'Synthetic-test-only-2026!'}).json()
        client.headers['X-CSRF-Token'] = session['csrf_token']
        for source in [args.duplex, args.difficult]:
            started = time.monotonic()
            b = client.post('/api/intakes', json={}).json()
            base = '/api/intakes/'+b['id']
            content = source.read_bytes()
            uploaded = client.post(base+'/files', files={'file':(source.name, content)})
            assert uploaded.status_code == 201, uploaded.text
            epw = ROOT/'fixtures/demo/reference_5zone/weather.epw'
            assert client.post(base+'/files', files={'file':('weather.epw', epw.read_bytes())}).status_code == 201
            assert client.post(base+'/analyze').status_code == 202
            analyzed = client.get(base).json()
            project = {'name':'公开 IFC 导入验收 / '+source.stem,
                       'building':{'use':'测试声明，非来源用途','location':'测试声明，非来源地点','region':'TEST','area_m2':1000}}
            commit = client.post(base+'/commit', json={'reviewed':True,'project':project})
            assert commit.status_code == 200, commit.text
            pid = commit.json()['project_id']
            imports = app.state.domain.store.list('import', pid)
            models = app.state.domain.store.list('model', pid)
            record = imports[0]
            result = {'source':source.name,'sha256':hashlib.sha256(content).hexdigest(),'bytes':len(content),
                      'file_inventory':analyzed['files'][0]['analysis']['facts'],
                      'missing_project_fields':analyzed['missing'],
                      'import_status':record['status'],
                      'candidate_rooms':len(record.get('candidate',{}).get('rooms',[])),
                      'diagnostics':record.get('diagnostics'),'error':record.get('error'),
                      'weather':client.get('/api/projects/'+pid+'/weather').json(),
                      'published_model_count':len(models),'can_simulate':client.get('/api/projects/'+pid+'/gate').json()['can_simulate'],
                      'elapsed_seconds':round(time.monotonic()-started,3)}
            assert not result['can_simulate'] and not models
            if source == args.duplex:
                assert record['status'] == 'awaiting_review' and result['candidate_rooms'] == 21
            else:
                assert record['status'] == 'failed' and record['diagnostics']['blocked'] == 94
            results['cases'].append(result)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps([{'source':r['source'],'status':r['import_status'],'rooms':r['candidate_rooms'],
                       'seconds':r['elapsed_seconds']} for r in results['cases']], ensure_ascii=False))


if __name__ == '__main__':
    main()
