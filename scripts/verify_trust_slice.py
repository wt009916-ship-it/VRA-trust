"""Isolated authenticated, actual EnergyPlus acceptance of selective recomputation/search."""
import copy
import json
import secrets
import sys
import time
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fastapi.testclient import TestClient
from backend.api import create_app
from backend import core

root = ROOT / 'validation' / 'trust-slice' / ('session_' + secrets.token_hex(6))
checks = []


def check(condition, message):
    checks.append({'passed': bool(condition), 'check': message})
    print(('PASS ' if condition else 'FAIL ') + message, flush=True)
    if not condition:
        raise AssertionError(message)


def wait(client, path, timeout=300):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(path)
        assert response.status_code == 200, response.text
        value = response.json()
        if value['status'] not in {'running', 'queued'}:
            return value
        time.sleep(.5)
    raise AssertionError('Timed out: ' + path)


with TestClient(create_app(root)) as client:
    session = client.post('/api/auth/register', json={'username': 'trust_acceptance', 'display_name': 'Reference acceptance', 'password': secrets.token_urlsafe(24)}).json()
    client.headers['X-CSRF-Token'] = session['csrf_token']
    project = client.post('/api/reference-projects').json()
    pid = project['project_id']
    for ev in client.get(f'/api/projects/{pid}/evidence').json():
        response = client.patch(f'/api/projects/{pid}/evidence/{ev["evidence_id"]}', json={'expected_revision': ev['revision'], 'review_state': 'confirmed', 'responsible_person': 'Automated reference test', 'review_note': 'Official reference fixture only, not field validation'})
        check(response.status_code == 200, 'reference evidence confirmed: ' + ev['name'])
    runs = []
    for scheme in ['baseline', 'R1', 'R2']:
        response = client.post('/api/runs', json={'project_id': pid, 'scheme_id': scheme, 'factor_profile_id': 'reference_scenario'})
        check(response.status_code == 202, 'accepted native simulation ' + scheme)
        view = wait(client, '/api/runs/' + response.json()['run_id'])
        check(view['status'] == 'succeeded', 'actual EnergyPlus succeeded ' + scheme + ' ' + str(view.get('error')))
        runs.append(view)
    rid = runs[0]['run_id']
    rd = root / 'runs' / rid
    before = {p.relative_to(rd).as_posix(): core.sha(p) for p in rd.rglob('*') if p.is_file()}
    factors = copy.deepcopy(core.get_profile('reference_scenario')['factors'])
    factors['Electricity']['value'] = .7
    response = client.put(f'/api/projects/{pid}/carbon-factors', json={'expected_revision': 0, 'region': '*', 'scenario': True, 'factors': factors})
    check(response.status_code == 200, 'new project factor version saved')
    view = client.get('/api/runs/' + rid).json()
    check(view['status'] == 'succeeded' and view['metrics'] == runs[0]['metrics'], 'factor change preserves verified energy and EUI')
    check(view['carbon']['node_state'] == 'STALE' and view['carbon']['operating_carbon_kg'] is None, 'carbon invalidated without stale numerical fallback')
    graph = client.get('/api/runs/' + rid + '/claims').json()
    check(rid not in graph['factor_change_affected'] and rid + ':energy' not in graph['factor_change_affected'], 'factor propagation excludes simulation and energy')
    check(graph['recomputation_plan'] == ['carbon.calculate', 'certificate.generate'] and not graph['energyplus_required'], 'selective recomputation plan')
    check(client.get('/api/runs/' + rid + '/report.json').json()['certificate']['status'] == 'PARTIALLY_STALE', 'certificate partially stale')
    pg = client.get(f'/api/projects/{pid}/claims').json()
    check(next(n for n in pg['nodes'] if n['id'].endswith(':energy-ranking'))['state'] == 'VALID', 'energy ranking stays valid')
    check(next(n for n in pg['nodes'] if n['id'].endswith(':carbon-ranking'))['state'] == 'STALE', 'carbon ranking invalidated')
    with patch.object(core, 'run_simulation', side_effect=AssertionError('Carbon recomputation must never invoke EnergyPlus')):
        response = client.post('/api/runs/' + rid + '/recalculate-carbon')
        check(response.status_code == 200, 'carbon recalculated without simulation entry point')
    updated = response.json()
    check(updated['carbon']['node_state'] == 'VALID' and updated['carbon']['provenance']['energyplus_calls'] == 0, 'carbon derivation records zero engine calls')
    check(updated['carbon']['operating_carbon_kg'] != runs[0]['carbon']['operating_carbon_kg'], 'new factor changes only carbon result')
    check(before == {p.relative_to(rd).as_posix(): core.sha(p) for p in rd.rglob('*') if p.is_file()}, 'original run artifacts byte-for-byte unchanged')
    search = client.post(f'/api/projects/{pid}/searches', json={'run_ids': [r['run_id'] for r in runs], 'axes': [{'material': 'IN46', 'values': [.023, .035], 'source': 'Explicit reference-test assumptions, not a measured material range'}], 'budget': 3})
    check(search.status_code == 202, 'bounded real counterexample search accepted')
    study = wait(client, f'/api/projects/{pid}/searches/' + search.json()['search_id'])
    check(study['status'] == 'succeeded', 'search succeeded: ' + str(study.get('error')))
    check(study['engine_calls'] == 3 and study['coverage'] == .5, 'actual budget and incomplete grid coverage recorded')
    check(study['stability_status'] in {'NO_FLIP_WITHIN_BUDGET', 'COUNTEREXAMPLE_FOUND'}, 'limited search never claims proven stability')
    check(all(r['metrics']['annual_days'] == 365 for p in study['points'] for r in p['runs']), 'all counterexample evaluations use full-year SQL')
    response = client.post(f'/api/projects/{pid}/searches/{study["search_id"]}/actions', json={'actions': [{'material': 'IN46', 'confirmed_value': .023, 'cost_cny': 500, 'duration_hours': 1, 'method': 'test-only measurement budget'}]})
    check(response.status_code == 200, 'cost-sensitive conditional evidence planning')
    if not response.json()['observed_counterexamples']:
        check(response.json()['actions'][0]['conditional_reduction_fraction'] is None, 'no invented risk benefit without observed counterexamples')
    report = client.get('/api/runs/' + rid + '/report.json').json()
    check(report['certificate']['stability_status'] == study['stability_status'], 'decision certificate includes same bounded search evidence')
    check(client.get('/api/runs/' + rid + '/report.pdf').status_code == 200, 'PDF generated from updated report snapshot')
    output = {'checks': checks, 'project_id': pid, 'runs': runs, 'carbon_after': updated['carbon'], 'search': study, 'data_nature': 'official reference, not field validation', 'root': str(root)}
    core.write_json(ROOT / 'validation/trust-slice/latest.json', output)
    print(json.dumps({'passed': len(checks), 'root': str(root)}, ensure_ascii=False), flush=True)
