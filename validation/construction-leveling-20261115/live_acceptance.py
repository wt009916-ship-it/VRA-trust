"""Real loopback HTTP, fixed independent/public cases; no browser, training or external stress."""
import hashlib
import json
import os
import secrets
import socket
import subprocess
import sys
import time
from fractions import Fraction as F
from pathlib import Path

import httpx

ROOT = Path('C:/Users/18483/AppData/Local/Temp/vra-timestep-reliability-20261108')
BASE = Path(__file__).parent
sys.path.insert(0, str(ROOT))

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p, body): Path(p).write_text(json.dumps(body, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
def port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0)); return s.getsockname()[1]

def synthetic(case):
    return {'name': 'Independent ' + case['id'], 'scope': 'Synthetic independent resource case; not construction measurements',
        'calendar': 'continuous_elapsed_days', 'time_origin': 'Synthetic reference elapsed day zero',
        'resources': [{'resource_id': r, 'name': r, 'capacity': c, 'unit': 'synthetic resource', 'source': 'Independent fixed capacity'} for r, c in case['capacities'].items()],
        'tasks': [{'task_id': k, 'name': k, 'duration_days': v['duration_half_days'] / 2,
            'duration_source': 'Independent frozen duration',
            'predecessors': [{'task_id': p, 'lag_days': lag / 2, 'source': 'Independent frozen precedence'} for p, lag in v['predecessors']],
            'demands': [{'resource_id': r, 'units': u} for r, u in v['demands'].items()]} for k, v in case['tasks'].items()]}

def verify(body, schedule):
    rows = {r['task_id']: r for r in schedule['rows']}
    assert set(rows) == {t['task_id'] for t in body['tasks']}
    intervals = {k: (F(r['start_day']), F(r['finish_day'])) for k, r in rows.items()}
    usage = {r['resource_id']: [] for r in body['resources']}
    for t in body['tasks']:
        start, finish = intervals[t['task_id']]
        assert start >= 0 and finish - start == F(str(t['duration_days']))
        assert all(start >= intervals[d['task_id']][1] + F(str(d['lag_days'])) for d in t['predecessors'])
        for d in t.get('demands', []): usage[d['resource_id']].append((start, finish, F(str(d['units']))))
    # Midpoint intersections, independent of the application event sweep and integer scaling.
    points = sorted({p for interval in intervals.values() for p in interval})
    for left, right in zip(points, points[1:]):
        point = (left + right) / 2
        for r in body['resources']:
            assert sum((u for a, b, u in usage[r['resource_id']] if a <= point < b), F(0)) <= F(str(r['capacity']))
    assert F(schedule['duration_days']) == max(b for _, b in intervals.values())

def serve():
    import uvicorn
    from backend.api import app
    uvicorn.run(app, host='127.0.0.1', port=int(sys.argv[2]), log_level='warning')

def run():
    out = BASE / 'live-first'; out.mkdir(exist_ok=False)
    runtime = BASE / 'private-live-runtime'; runtime.mkdir(exist_ok=False)
    app_port = port(); process = None
    receipt = {'completed': False, 'scope': 'Real loopback HTTP. Frozen synthetic/public references; not real-building or browser acceptance.',
        'checks': [], 'cases': [], 'product_sha256': {p.name: sha(p) for p in (ROOT / 'backend').glob('*.py')}}
    log = (out / 'application.log').open('xb')
    def check(name, passed):
        receipt['checks'].append({'name': name, 'passed': bool(passed)}); save(out / 'receipt.json', receipt); assert passed, name
    try:
        process = subprocess.Popen([sys.executable, '-B', '-X', 'utf8', str(Path(__file__).resolve()), 'serve', str(app_port)],
            cwd=ROOT, env={**os.environ, 'VRA_DATA_DIR': str(runtime), 'PYTHONDONTWRITEBYTECODE': '1'},
            stdout=log, stderr=log, stdin=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
        with httpx.Client(base_url=f'http://127.0.0.1:{app_port}', timeout=45, trust_env=False) as c:
            for _ in range(200):
                assert process.poll() is None
                try:
                    if c.get('/api/health').status_code == 200: break
                except httpx.HTTPError: pass
                time.sleep(.1)
            else: raise TimeoutError('Application startup')
            response = c.post('/api/auth/register', json={'username': 'leveling_isolated', 'display_name': '隔离排程验收', 'password': secrets.token_urlsafe(32)})
            check('isolated_registration', response.status_code == 200)
            c.headers['X-CSRF-Token'] = response.json()['csrf_token']
            def request(method, path, body=None):
                r = c.request(method, path, json=body); r.raise_for_status(); return r.json()
            project = request('POST', '/api/projects', {'name': 'Isolated resource scheduling references', 'building': {'use': 'reference', 'location': 'Synthetic', 'region': 'TEST', 'area_m2': 100.}})
            base = '/api/projects/' + project['project_id']
            references = json.loads((BASE / 'reference-frozen.json').read_text())['cases']
            cases = [{'id': x['id'], 'body': synthetic(x), 'priority': x['priority'], 'expected_finish': x['expected_finish_days'], 'starts': x['expected_starts_days']} for x in references]
            frozen = json.loads((BASE / 'public-reference/frozen-public-reference.json').read_text())
            preparation = json.loads((BASE / 'public-reference/input-preparation.json').read_text())
            for item, prepared in zip(frozen['cases'], preparation['cases'], strict=True):
                p = BASE / 'public-reference' / (item['file'] + '.schedule.json')
                assert item['file'] == prepared['source'] and sha(p) == prepared['parsed_sha256']
                cases.append({'id': item['file'], 'body': json.loads(p.read_text()), 'priority': prepared['fixed_priority'], 'public_optimum': item['published_optimum'], 'source_sha256': item['sha256'], 'input_sha256': sha(p)})
            own = {}
            for case in cases:
                source = request('POST', base + '/schedules', case['body'])
                body = {'name': case['id'] + ' fixed priority schedule', 'source_hash': source['hash'], 'priority': case['priority'],
                    'resource_demands_complete': True, 'demand_basis': 'Frozen independent benchmark specifies all declared renewable resource requirements'}
                begin = time.monotonic()
                result = request('POST', base + '/schedules/' + source['schedule_id'] + '/resource-levelings', body)
                elapsed = time.monotonic() - begin
                p = (result.get('result') or {}).get('leveled', {}).get('schedule')
                passed = bool(p and result['status'] == 'calculated')
                if passed:
                    verify(case['body'], p)
                    if 'expected_finish' in case:
                        passed = F(p['duration_days']) == F(str(case['expected_finish'])) and {r['task_id']: F(r['start_day']) for r in p['rows']} == {k: F(str(v)) for k, v in case['starts'].items()}
                row = {'id': case['id'], 'passed': passed, 'seconds': round(elapsed, 6), 'source_sha256': case.get('source_sha256'), 'input_sha256': case.get('input_sha256'),
                    'schedule_id': result['schedule_id'], 'result': result['result'], 'current_status': result['status']}
                if 'public_optimum' in case and p:
                    row.update(published_optimum=case['public_optimum'], gap_days=str(F(p['duration_days']) - case['public_optimum']), gap_percent=float((F(p['duration_days']) / case['public_optimum'] - 1) * 100))
                    assert F(p['duration_days']) >= case['public_optimum']
                receipt['cases'].append(row); save(out / 'receipt.json', receipt)
                check(case['id'] + '_constraints_and_reference', passed)
                if case['id'].startswith('R'): own[case['id']] = {'source': source, 'result': result, 'request': body}
            save(out / 'synthetic-records.json', own)
            source, derived = own['R03']['source'], own['R03']['result']
            url = base + '/schedules/' + source['schedule_id'] + '/resource-levelings'
            bad = {**own['R03']['request'], 'source_hash': '0' * 64}
            check('wrong_source_hash_409', c.post(url, json=bad).status_code == 409)
            check('source_unchanged', request('GET', base + '/schedules/' + source['schedule_id']) == source)
            with httpx.Client(base_url=c.base_url, trust_env=False) as anonymous:
                check('anonymous_401', anonymous.get(base + '/schedules/' + derived['schedule_id']).status_code == 401)
            token = c.headers.pop('X-CSRF-Token')
            check('missing_csrf_403', c.post(url, json=own['R03']['request']).status_code == 403)
            c.headers['X-CSRF-Token'] = token
            bad_source = request('POST', base + '/schedules', {**cases[0]['body'], 'resources': [{**r, 'capacity': None} for r in cases[0]['body']['resources']]})
            incomplete = request('POST', base + '/schedules/' + bad_source['schedule_id'] + '/resource-levelings', {**own['R01']['request'], 'source_hash': bad_source['hash']})
            save(out / 'unknown-capacity.json', incomplete)
            check('unknown_capacity_not_zero_or_feasible', incomplete['status'] == 'incomplete' and incomplete['result']['leveled']['schedule'] is None)
            task = request('POST', base + '/agent/chat', {'message': '读取明确指定的资源受限方案及限制', 'mode': 'local', 'objective': 'inspect_schedule', 'target_schedule_id': derived['schedule_id']})
            deadline = time.monotonic() + 30
            while task['status'] == 'running' and time.monotonic() < deadline:
                time.sleep(.1); task = request('GET', base + '/agent/' + task['agent_id'])
            save(out / 'agent-deterministic.json', task)
            check('deterministic_agent_reads_current_derived_plan', task['answer']['artifact']['result']['leveled']['schedule']['duration_days'] == '6.5')
            request('PUT', base + '/building', {'expected_revision': project['revision'], 'building': {**project['building'], 'area_m2': 101.}})
            withdrawn = request('GET', base + '/schedules/' + derived['schedule_id']); save(out / 'withdrawn.json', withdrawn)
            check('project_revision_withdraws_schedule', withdrawn['status'] == 'stale' and withdrawn['result'] is None)
            current_task = request('GET', base + '/agent/' + task['agent_id']); save(out / 'agent-withdrawn.json', current_task)
            check('agent_withdraws_derived_values', current_task['answer']['artifact']['result'] is None)
            check('report_withdraws_derived_values', '资源受限方案：6.5' not in c.get(base + '/schedules/' + derived['schedule_id'] + '/report.html').text)
            receipt['completed'] = True
    except Exception as exc:
        receipt['error'] = type(exc).__name__ + ': ' + str(exc); raise
    finally:
        if process and process.poll() is None:
            process.terminate()
            try: process.wait(timeout=15)
            except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=10)
        log.close(); receipt['process_stopped'] = process is None or process.poll() is not None
        save(out / 'receipt.json', receipt)
        print(json.dumps({'completed': receipt['completed'], 'checks': len(receipt['checks']), 'cases': [{k: x.get(k) for k in ['id', 'passed', 'seconds', 'published_optimum', 'gap_days', 'gap_percent']} for x in receipt['cases']]}, ensure_ascii=False))

if __name__ == '__main__':
    serve() if len(sys.argv) > 1 and sys.argv[1] == 'serve' else run()
