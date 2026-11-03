"""Isolated weather -> native annual EnergyPlus acceptance; no production accounts.

Optional --live-nasa calls the real public service (no test transport or fallback).
The private-runtime folder contains test accounts and must not be distributed.
"""
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
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--live-nasa', action='store_true')
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    os.environ['VRA_DATA_DIR'] = str(out/'private-runtime')
    from fastapi.testclient import TestClient
    from backend.api import create_app
    from backend import core
    app = create_app(out/'private-runtime')
    with TestClient(app) as api:
        login = api.post('/api/auth/register', json={'username': 'isolated_weather', 'display_name': 'Weather software acceptance only', 'password': secrets.token_urlsafe(32)})
        login.raise_for_status()
        api.headers['X-CSRF-Token'] = login.json()['csrf_token']
        def checked(response):
            response.raise_for_status()
            return response.json()
        project = checked(api.post('/api/reference-projects'))
        pid = project['project_id']
        base = '/api/projects/'+pid
        evs = checked(api.get(base+'/evidence'))
        epw = next(e for e in evs if e['type']=='epw')
        analysis = checked(api.post(base+'/weather/epw', json={'file_id': epw['source_file']}))
        assert analysis['quality']['simulation_candidate'] and analysis['quality']['records'] == 8760
        core.write_json(out/'reference-epw-analysis.json', analysis)
        (out/'reference-epw-clean.csv').write_bytes(api.get(base+'/weather/'+analysis['weather_id']+'/data.csv').content)
        summary = {'verified_at': core.now(), 'scope': 'Isolated software acceptance; reference building, not field validation',
                   'epw': {k: analysis[k] for k in ['source_hash','analyzer_version','quality','annual']},
                   'nasa_live_tested': args.live_nasa}
        if args.live_nasa:
            body = {'latitude': 30.59, 'longitude': 114.3, 'start': '2025-01-01', 'end': '2025-12-31', 'label': 'Wuhan public climate acceptance only'}
            nasa = checked(api.post(base+'/weather/nasa', json=body))
            assert nasa['quality']['full_year'] and not nasa['quality']['invalid_fields']
            assert not nasa['quality']['simulation_candidate']
            core.write_json(out/'nasa-wuhan-2025-analysis.json', nasa)
            raw = api.get(base+'/files/'+nasa['file_id'])
            raw.raise_for_status()
            (out/'nasa-wuhan-2025-original.json').write_bytes(raw.content)
            assert core.sha(out/'nasa-wuhan-2025-original.json') == nasa['source_hash']
            (out/'nasa-wuhan-2025-clean.csv').write_bytes(api.get(base+'/weather/'+nasa['weather_id']+'/data.csv').content)
            cached = checked(api.post(base+'/weather/nasa', json=body))
            assert cached['weather_id'] == nasa['weather_id']
            summary['nasa'] = {k: nasa[k] for k in ['source_hash','analyzer_version','quality','annual','provenance']}
            summary['nasa']['cache_reused'] = True
            assert len(checked(api.get(base+'/evidence'))) == len(evs)  # No false EPW/evidence creation.
        for ev in evs:
            checked(api.patch(base+'/evidence/'+ev['evidence_id'], json={'expected_revision':ev['revision'], 'review_state':'confirmed', 'responsible_person':'Software acceptance only', 'review_note':'Official reference fixture reviewed solely for regression testing; not field evidence.'}))
        gate = checked(api.get(base+'/gate'))
        assert gate['can_simulate']
        run = checked(api.post('/api/runs', json={'project_id':pid,'scheme_id':'baseline','factor_profile_id':'none'}))
        start = time.monotonic()
        while time.monotonic()-start < 420:
            run = checked(api.get('/api/runs/'+run['run_id']))
            if run['status'] not in {'queued','running'}:
                break
            time.sleep(.5)
        core.write_json(out/'native-run.json', run)
        assert run['status'] == 'succeeded', json.dumps(run, ensure_ascii=False)
        report = api.get('/api/runs/'+run['run_id']+'/report.pdf')
        report.raise_for_status()
        (out/'reference-native-report.pdf').write_bytes(report.content)
        summary['native_engine'] = {'run_id':run['run_id'],'status':run['status'],'metrics':run['metrics'],'elapsed_seconds':round(time.monotonic()-start,2),'weather_source':'reference EPW, never NASA daily data'}
        core.write_json(out/'acceptance.json', summary)
        print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
