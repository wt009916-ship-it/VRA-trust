"""Authenticated real annual reference run + source-bound zone sizing reports.

Usage: python scripts/verify_design_load_reference.py NEW_OUTPUT_DIRECTORY
This is public-model validation, not an independent answer for the full building.
"""
import json
import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend import core
from backend.private_storage import private_mkdir


def main():
    out = Path(sys.argv[1]).resolve()
    if out.exists():
        raise RuntimeError('Use a new output directory')
    private_mkdir(out)
    os.environ['VRA_DATA_DIR'] = str(out / 'bootstrap')
    from backend.api import create_app
    from fastapi.testclient import TestClient
    with TestClient(create_app(out / 'api', start_worker=False)) as client:
        response = client.post('/api/auth/register', json={'username': 'design_load_acceptance',
            'display_name': 'Isolated sizing reference verifier', 'password': secrets.token_urlsafe(32)})
        assert response.status_code == 200
        client.headers['X-CSRF-Token'] = response.json()['csrf_token']
        project = client.post('/api/reference-projects').json()
        base = '/api/projects/' + project['project_id']
        for ev in client.get(base + '/evidence').json():
            response = client.patch(base + '/evidence/' + ev['evidence_id'], json={
                'expected_revision': ev['revision'], 'review_state': 'confirmed',
                'responsible_person': 'Isolated verifier',
                'review_note': 'Public model scenario for software acceptance; no real-building or local-design certification'})
            assert response.status_code == 200
        submitted = client.post('/api/runs', json={'project_id': project['project_id'], 'scheme_id': 'baseline'})
        assert submitted.status_code == 202, submitted.text
        rid = submitted.json()['run_id']
        domain = client.app.state.domain
        job = domain.store.claim_job()
        assert job['run_id'] == rid
        domain.execute(job)
        report = client.get('/api/runs/' + rid + '/report.json').json()
        core.write_json(out / 'actual-report.json', report)
        assert report['run']['status'] == 'succeeded', report['run']
        sizing = report['run']['metrics']['zone_design_loads']
        assert sizing['status'] == 'calculated_model_scenario', sizing.get('reason')
        assert len(sizing['rows']) == 10 and sizing['building_coincident_peak_W'] is None
        rd = out / 'api/runs' / rid
        raw_result = core.read_json(rd / 'result.json')
        assert raw_result['metrics']['zone_design_loads'] == sizing
        assert sizing['model_sha256'] == core.sha(rd / 'input/model.idf')
        assert sizing['sql_sha256'] == core.sha(rd / 'output/eplusout.sql')
        assert sizing['weather_sha256'] == core.sha(rd / 'input/weather.epw')
        for fmt in ('json', 'html', 'pdf'):
            response = client.get('/api/runs/' + rid + '/report.' + fmt)
            assert response.status_code == 200
            (out / ('report.' + fmt)).write_bytes(response.content)
        # Keep a byte-exact clean copy before this isolated test corruption.
        (out / 'clean-result.json').write_bytes((rd / 'result.json').read_bytes())
        (out / 'clean-manifest.json').write_bytes((rd / 'manifest.json').read_bytes())
        manifest = core.read_json(rd / 'manifest.json')
        raw_result['metrics']['zone_design_loads']['model_sha256'] = '0' * 64
        core.write_json(rd / 'result.json', raw_result)
        manifest['artifact_hashes']['result.json'] = core.sha(rd / 'result.json')
        core.write_json(rd / 'manifest.json', manifest)
        # An internally wrong binding must still fail even when its artifact hash matches.
        rejected = client.get('/api/runs/' + rid).json()
        core.write_json(out / 'binding-rejected.json', rejected)
        assert rejected['status'] == 'failed' and rejected['metrics'] is None
        assert 'Zone design-load receipt binding mismatch' in rejected['error']
    summary = {'run_id': rid, 'new_energyplus_simulations': 1, 'zone_load_rows': 10,
               'annual_energy_kwh': report['run']['metrics']['annual_energy_kwh'],
               'binding_tamper_rejected': True, 'clean_model_sha256': sizing['model_sha256'],
               'clean_sql_sha256': sizing['sql_sha256'], 'sizing': sizing,
               'scope': 'Public reference model native run and report consistency; not independent full-building load validation',
               'code_hash': core.code_hash()}
    core.write_json(out / 'summary.json', summary)
    print(json.dumps({k: v for k, v in summary.items() if k != 'sizing'}))


if __name__ == '__main__':
    main()
