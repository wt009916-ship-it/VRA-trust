"""Actual EnergyPlus acceptance; isolated reference data, never a field validation."""
import copy
import io
import json
import secrets
import sys
import time
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fastapi.testclient import TestClient
from backend import core
from backend.api import create_app
from backend.agent import Chat

root = ROOT / 'validation/material-decision' / ('session_' + secrets.token_hex(6))
checks = []


def check(condition, description):
    checks.append({'passed': bool(condition), 'check': description})
    print(('PASS ' if condition else 'FAIL ') + description, flush=True)
    if not condition:
        raise AssertionError(description)


def wait(client, url, timeout=600):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(url)
        assert response.status_code == 200, response.text
        value = response.json()
        if value['status'] not in {'running', 'queued'}:
            return value
        time.sleep(.5)
    raise TimeoutError(url)


with TestClient(create_app(root)) as client:
    login = client.post('/api/auth/register', json={'username': 'decision_acceptance', 'display_name': 'Reference acceptance',
                                                   'password': secrets.token_urlsafe(24)}).json()
    client.headers['X-CSRF-Token'] = login['csrf_token']
    project = client.post('/api/reference-projects').json()
    pid, base = project['project_id'], '/api/projects/' + project['project_id']
    check(client.get(base + '/diagnosis').json()['can_simulate'] is False, 'diagnosis identifies unreviewed reference inputs')
    for ev in client.get(base + '/evidence').json():
        response = client.patch(base + '/evidence/' + ev['evidence_id'], json={
            'expected_revision': ev['revision'], 'review_state': 'confirmed', 'responsible_person': 'Automated reference test',
            'review_note': 'Official reference model only; not field evidence'})
        check(response.status_code == 200, 'review reference source ' + ev['name'])
    response = client.post('/api/runs', json={'project_id': pid, 'scheme_id': 'baseline', 'factor_profile_id': 'reference_scenario'})
    check(response.status_code == 202, 'submit actual baseline EnergyPlus run')
    baseline = wait(client, '/api/runs/' + response.json()['run_id'])
    check(baseline['status'] == 'succeeded', 'actual baseline SQL and ERR validated')
    rid = baseline['run_id']
    rd = root / 'runs' / rid
    baseline_hashes = {p.relative_to(rd).as_posix(): core.sha(p) for p in rd.rglob('*') if p.is_file()}
    targets = client.get(base + '/material-targets/' + rid).json()
    target = next(m for m in targets if m['name'] == 'IN46')
    check(target['supported'] and target['surfaces'], 'map existing material to real constructions and surfaces')

    def evidence(name):
        ev = client.post(base + '/evidence', json={'type': 'assumption', 'name': name, 'source_locator': 'Reference acceptance scenario',
            'authority': 'Automated reference test', 'permission': 'Test only', 'acquisition_method': 'Explicit scenario',
            'responsible_person': 'Automated reference test', 'status': 'ASSUMED'}).json()
        return client.patch(base + '/evidence/' + ev['evidence_id'], json={'expected_revision': ev['revision'], 'review_state': 'confirmed',
            'responsible_person': 'Automated reference test', 'review_note': 'Declared assumptions only; not measured properties or market quotes'}).json()
    thermal, cost = evidence('Reference material parameters'), evidence('Synthetic incremental initial costs')
    material_body = {key: target[key] for key in ('conductivity_w_mk', 'density_kg_m3', 'specific_heat_j_kgk')}
    material_body.update(name='IN46 reference parameter scenario', thermal_evidence_id=thermal['evidence_id'],
        source_locator='Official reference IDF Material IN46', test_conditions='Reference scenario, no physical sample test',
        applicability='Existing mapped opaque layer only', review_state='confirmed', responsible_person='Automated reference test',
        review_note='Values read from reference IDF; do not claim material performance validation')
    response = client.post(base + '/materials', json=material_body)
    check(response.status_code == 201, 'register material card with reviewed parameter provenance')
    card = response.json()
    check(card['can_simulate'] and card['source_nature'] == 'ASSUMED' and not card['performance_claim_verified'], 'confirmed scenario preserves assumed data nature')
    options = [{'option_id': name, 'name': name + ' reference thickness', 'material_id': card['material_id'], 'thickness_m': thickness,
                'cost_cny': price, 'cost_evidence_id': cost['evidence_id'], 'cost_scope': 'Explicit synthetic total incremental installation scenario'}
               for name, thickness, price in [('C01', .08, 5000), ('C02', .12, 9000), ('C03', .16, 15000)]]
    plan = {'source_run_id': rid, 'target_material': 'IN46', 'options': options, 'objectives': ['energy_kwh', 'cost_cny', 'cooling_unmet_h'],
            'constraints': {'max_cost_cny': 10000}, 'budget': 2, 'basis': 'Reference-only thickness scenarios; not material performance or economic evidence'}
    task = client.app.state.agent.start(pid, Chat(message='Execute this confirmed material study', allow_compute=True, study_plan=plan), background=False)
    check(task['status'] == 'succeeded', 'local assistant executes explicit user plan through guarded tool')
    study_id = next(e['result']['study_id'] for e in task['events'] if e['tool'] == 'material_study_create')
    study = wait(client, base + '/studies/' + study_id)
    check(study['status'] == 'succeeded', 'material scenarios completed: ' + str(study.get('error')))
    check(study['engine_calls'] == 2 and all(p['status'] == 'succeeded' for p in study['points']), 'exactly two actual candidate engine calls within budget')
    check(study['assessment']['untested_options'] == ['C03'] and study['assessment']['evaluated_options'] == 2, 'unrun option explicitly excluded from candidate claims')
    check(study['assessment']['pareto_option_ids'], 'constraint and Pareto assessment computed from verified outputs')
    check(all(p['metrics']['annual_days'] == 365 for p in study['points']), 'each baseline and candidate uses full-year SQL')
    check(baseline_hashes == {p.relative_to(rd).as_posix(): core.sha(p) for p in rd.rglob('*') if p.is_file()}, 'original baseline artifacts remain byte-for-byte unchanged')
    before = {p.relative_to(root).as_posix(): core.sha(p) for p in (root / 'studies' / study_id).rglob('*') if p.is_file()}
    factors = copy.deepcopy(core.get_profile('reference_scenario')['factors'])
    factors['Electricity']['value'] = .7
    response = client.put(base + '/carbon-factors', json={'expected_revision': 0, 'region': '*', 'scenario': True, 'factors': factors})
    check(response.status_code == 200, 'update project carbon factor separately')
    current = client.get(base + '/studies/' + study_id).json()
    check(current['status'] == 'succeeded' and current['assessment'] is None and current['assessment_stale'], 'factor update invalidates assessment while preserving physical outputs')
    with patch.object(core, 'run_simulation', side_effect=AssertionError('No EnergyPlus call allowed for reevaluation')):
        response = client.post(base + '/studies/' + study_id + '/reevaluate')
    check(response.status_code == 200 and response.json()['assessment']['energyplus_calls_for_assessment'] == 0, 'reassess all candidate carbon with zero physical calls')
    report = client.get(base + '/studies/' + study_id + '/report.json').json()
    check(report['study']['assessment']['rows'][1]['values']['carbon_kg'] != study['assessment']['rows'][1]['values']['carbon_kg'], 'reassessment applies current factor to candidate-specific energy carriers')
    check(before == {p.relative_to(root).as_posix(): core.sha(p) for p in (root / 'studies' / study_id).rglob('*') if p.is_file()}, 'reevaluation never rewrites original candidate artifacts')
    pdf = client.get(base + '/studies/' + study_id + '/report.pdf')
    check(pdf.status_code == 200 and pdf.content.startswith(b'%PDF'), 'same-source material decision PDF generated')
    (root / 'decision-report.pdf').write_bytes(pdf.content)
    html = client.get(base + '/studies/' + study_id + '/report.html')
    check(html.status_code == 200 and 'C01' in html.text and study_id in html.text, 'HTML includes the same candidates and study identity')
    archive = client.get(base + '/studies/' + study_id + '/artifacts')
    with zipfile.ZipFile(io.BytesIO(archive.content)) as zipped:
        check('DECISION_REPORT.json' in zipped.namelist() and any(name.endswith('eplusout.sql') for name in zipped.namelist()), 'download binds decision report to actual SQL and input artifacts')
    followup = client.app.state.agent.start(pid, Chat(message='解释材料方案取舍与下一步补证'), background=False)
    check(followup['answer']['diagnosis']['current_study_id'] == study_id and any(e['tool'] == 'decision_report' for e in followup['events']), 'assistant consumes actual decision report and evidence tasks')
    history_before = client.app.state.domain.store.get('study', study_id)
    revoked = client.patch(base + '/evidence/' + thermal['evidence_id'], json={'expected_revision': thermal['revision'], 'review_state': 'pending',
        'responsible_person': 'Automated reference test', 'review_note': 'Withdraw parameter evidence to validate invalidation'})
    check(revoked.status_code == 200, 'withdraw thermal source as a new version')
    invalid = client.get(base + '/studies/' + study_id).json()
    check(invalid['status'] == 'stale' and invalid['assessment'] is None and all(p['metrics'] is None for p in invalid['points']), 'invalidated material study suppresses current metrics and candidates')
    check(client.get('/api/runs/' + rid).json()['status'] == 'succeeded', 'material source withdrawal leaves original baseline energy valid')
    check(client.app.state.domain.store.get('study', study_id) == history_before, 'historical material study and source snapshots remain unchanged')
    final = {'checks': checks, 'actual_engine_calls': 3, 'project_id': pid, 'study_id': study_id, 'root': str(root),
             'report_before_source_withdrawal': report, 'data_nature': 'Official reference plus explicit synthetic material/cost scenarios, not field validation'}
    core.write_json(root / 'checks.json', final)
    core.write_json(ROOT / 'validation/material-decision/latest.json', final)
    print(json.dumps({'checks_passed': len(checks), 'actual_engine_calls': 3, 'root': str(root)}), flush=True)
