"""Actual loopback HTTP acceptance; isolated account/data, no browser or external model."""
import copy
import hashlib
import json
import os
import secrets
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

repo = Path('C:/Users/18483/AppData/Local/Temp/vra-timestep-reliability-20261108')
out = Path(__file__).parent / 'actual-http'
out.mkdir(exist_ok=False)
runtime = Path('C:/Users/18483/AppData/Local/Temp') / ('vra-thermal-bridge-http-' + secrets.token_hex(8))
runtime.mkdir()
sys.path.insert(0, str(repo / 'tests'))
sys.path.insert(0, str(repo))
from test_thermal_bridge import slab, boundary, region

with socket.socket() as sock:
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
env = {**os.environ, 'VRA_DATA_DIR': str(runtime), 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONPATH': str(repo)}
command = [sys.executable, '-B', '-X', 'utf8', '-c',
    'from backend.api import create_app; import uvicorn; uvicorn.run(create_app(start_worker=False),host="127.0.0.1",port=' + str(port) + ',access_log=False)']
checks = []
def check(name, passed, actual):
    checks.append({'name': name, 'passed': bool(passed), 'actual': actual})
    assert passed, name + ': ' + str(actual)

log = (out / 'server.log').open('wb')
process = subprocess.Popen(command, cwd=repo, env=env, stdout=log, stderr=subprocess.STDOUT,
                           creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
try:
    with httpx.Client(base_url=f'http://127.0.0.1:{port}', timeout=45) as client:
        for attempt in range(80):
            try:
                if client.get('/api/health').status_code == 200:
                    break
            except httpx.TransportError:
                pass
            time.sleep(.25)
        else:
            raise RuntimeError('Isolated API failed to start')
        login = client.post('/api/auth/register', json={'username': 'thermal_bridge_acceptance',
            'display_name': 'Isolated thermal reference test', 'password': secrets.token_urlsafe(32)})
        assert login.status_code == 201, login.status_code
        client.headers['X-CSRF-Token'] = login.json()['csrf_token']
        del login
        project = client.post('/api/projects', json={'name': 'Synthetic/public 2D conduction references',
            'building': {'use': 'reference', 'location': 'Declared test', 'region': 'test', 'area_m2': 1.}}).json()
        base = '/api/projects/' + project['project_id']
        path = base + '/thermal-bridges'
        body = slab()
        body.update(width=1., height=1., cell_size=.05, regions=[region('Homogeneous', 0., 1., 0., 1., 1.)],
                    probes=[{'name': 'Centre', 'x': .5, 'y': .5}])
        body['boundaries'] = {s: boundary('film', t, .2) for s, t in [('left', 20.), ('right', 0.), ('bottom', 10.), ('top', 10.)]}
        ev = client.post(base + '/evidence', json={'type': 'manual_input', 'name': 'Synthetic four-film reference',
            'source_locator': 'Four boundary symmetry test', 'authority': 'Test author', 'permission': 'Synthetic reference',
            'acquisition_method': 'Explicit declaration', 'responsible_person': 'Test author', 'status': 'ASSUMED'}).json()
        body['evidence_ids'] = [ev['evidence_id']]
        response = client.post(path, json=body)
        check('smooth_2d_created', response.status_code == 201, response.status_code)
        smooth = response.json()
        (out / 'smooth-input.json').write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding='utf-8')
        (out / 'smooth-response.json').write_text(json.dumps(smooth, ensure_ascii=False, indent=2), encoding='utf-8')
        check('smooth_field_converged', smooth['status'] == 'calculated', smooth['result']['mesh_check'])
        temp = smooth['result']['probes'][0]['temperature_c']
        check('independent_symmetry_centre_10c', abs(temp - 10) < 1e-8, temp)
        record_path = path + '/' + smooth['thermalbridge_id']
        html = client.get(record_path + '/report.html')
        (out / 'smooth-report.html').write_bytes(html.content)
        check('html_report', html.status_code == 200 and 'W/m' in html.text, html.status_code)
        csv = client.get(record_path + '/temperatures.csv')
        (out / 'smooth-temperatures.csv').write_bytes(csv.content)
        check('csv_cells', csv.status_code == 200 and len(csv.text.splitlines()) - 1 == smooth['result']['mesh_check']['fine_cells'], len(csv.text.splitlines()) - 1)
        reference = json.loads((out.parent / 'composite-reference-frozen.json').read_text())
        start = time.monotonic()
        response = client.post(path, json=reference['input'])
        elapsed = time.monotonic() - start
        check('public_composite_created', response.status_code == 201, {'status_code': response.status_code, 'seconds': elapsed})
        composite = response.json()
        (out / 'composite-response.json').write_text(json.dumps(composite, ensure_ascii=False, indent=2), encoding='utf-8')
        e = reference['expected']
        errors = {p['name']: abs(p['temperature_c'] - e['temperature_c'][p['name']]) for p in composite['result']['probes']}
        check('public_nine_temperature_points', max(errors.values()) <= e['absolute_temperature_tolerance_k'], errors)
        heat = composite['result']['boundary_heat_into_domain_w_per_m']['bottom']
        check('public_heat_flow', abs(heat - e['heat_w_per_m']) <= e['absolute_heat_tolerance_w_per_m'], heat)
        check('unresolved_mesh_not_promoted', composite['status'] == 'needs_refinement', composite['result']['mesh_check'])
        for name, change in [('zero_conductivity', lambda b: b['regions'][0].update(conductivity=0.)),
                             ('wrong_unit', lambda b: b['regions'][0].update(conductivity_unit='kg')),
                             ('negative_width', lambda b: b.update(width=-1.))]:
            changed = copy.deepcopy(body)
            change(changed)
            response = client.post(path, json=changed)
            check(name, response.status_code == 422, response.status_code)
        missing = copy.deepcopy(body)
        missing['regions'][0]['conductivity'] = None
        response = client.post(path, json=missing)
        check('missing_data_null', response.status_code == 201 and response.json()['result']['temperature_c'] is None, response.json()['status'])
        response = client.post(path, json=body, headers={'X-CSRF-Token': ''})
        check('csrf_refusal', response.status_code == 403, response.status_code)
        changed = client.patch(base + '/evidence/' + ev['evidence_id'], json={'expected_revision': 1, 'review_state': 'rejected',
            'responsible_person': 'Test author', 'review_note': 'Withdraw synthetic reference for stale test'})
        check('withdrawal_saved', changed.status_code == 200, changed.status_code)
        current = client.get(record_path).json()
        (out / 'smooth-withdrawn.json').write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding='utf-8')
        check('stale_hides_field', current['status'] == 'stale' and current['result'] is None, current['status'])
        response = client.get(record_path + '/temperatures.csv')
        check('stale_csv_refused', response.status_code == 409, response.status_code)
        response = client.post(path, json=body)
        check('withdrawn_source_recalculation_refused', response.status_code == 409, response.status_code)
        client.cookies.clear()
        response = client.get(record_path + '/report.html')
        check('anonymous_report_refused', response.status_code == 401, response.status_code)
finally:
    process.terminate()
    process.wait(timeout=15)
    log.close()
    sources = {}
    for rel in ['backend/thermal_bridge.py', 'backend/thermal_bridge_solver.py', 'backend/thermal_bridge_routes.py',
                'backend/calculation_provenance.py', 'backend/extensions.py', 'backend/schema.py', 'backend/requirements.txt',
                'frontend/src/thermal-bridge-ui.js', 'frontend/src/thermal-bridge-view.js', 'frontend/src/thermal-bridge.css', 'frontend/src/thermal-ui.js']:
        target = out / 'source-snapshot' / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((repo / rel).read_bytes())
        sources[rel] = hashlib.sha256(target.read_bytes()).hexdigest()
    receipt = {'utc': datetime.now(timezone.utc).isoformat(), 'transport': 'real loopback HTTP / uvicorn; no browser',
               'isolated_data_only': True, 'checks': checks, 'passed': sum(c['passed'] for c in checks),
               'failed': sum(not c['passed'] for c in checks), 'source_sha256': sources,
               'scope': 'Synthetic smooth 2D case plus frozen public composite; not real-building or full ISO validation'}
    (out / 'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'passed': receipt['passed'], 'failed': receipt['failed'], 'checks': len(checks)}))
