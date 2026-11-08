"""Bounded real HTTP concurrency probe; no app patching, mocks or private logs.

Runtime accounts are random, isolated and never serialized. The input contract
is written before server startup. A failed run is retained, never overwritten.
"""
import argparse
import concurrent.futures
import ctypes as c
from ctypes import wintypes as w
from decimal import Decimal
import hashlib
import html
import json
import math
import os
from pathlib import Path
import secrets
import socket
import sqlite3
import subprocess
import sys
import sysconfig
import threading
import time
import traceback


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def memory(pid):
    class Counters(c.Structure):
        _fields_ = [('cb', w.DWORD), ('faults', w.DWORD)] + [
            (key, c.c_size_t) for key in ('peak_ws', 'ws', 'peak_pool', 'pool',
                'peak_nonpaged', 'nonpaged', 'pagefile', 'peak_pagefile', 'private')]
    kernel = c.WinDLL('kernel32', use_last_error=True)
    psapi = c.WinDLL('psapi', use_last_error=True)
    kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    kernel.OpenProcess.restype = w.HANDLE
    kernel.CloseHandle.argtypes = [w.HANDLE]
    kernel.GetProcessHandleCount.argtypes = [w.HANDLE, c.POINTER(w.DWORD)]
    psapi.GetProcessMemoryInfo.argtypes = [w.HANDLE, c.c_void_p, w.DWORD]
    handle = kernel.OpenProcess(0x410, False, pid)
    if not handle:
        raise c.WinError(c.get_last_error())
    try:
        counters = Counters(); counters.cb = c.sizeof(counters); count = w.DWORD()
        if not psapi.GetProcessMemoryInfo(handle, c.byref(counters), counters.cb):
            raise c.WinError(c.get_last_error())
        if not kernel.GetProcessHandleCount(handle, c.byref(count)):
            raise c.WinError(c.get_last_error())
        return {'private_bytes': counters.private, 'working_set_bytes': counters.ws,
                'handles': count.value}
    finally:
        kernel.CloseHandle(handle)


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', required=True)
parser.add_argument('--output', required=True)
parser.add_argument('--commit', required=True)
parser.add_argument('--seconds', type=int, default=1800)
parser.add_argument('--interval', type=float, default=4)
parser.add_argument('--serve', action='store_true')
parser.add_argument('--site')
parser.add_argument('--port', type=int)
args = parser.parse_args()
source = Path(args.source).resolve(); out = Path(args.output).resolve()
sys.path.insert(0, str(source))
if args.site:
    sys.path.insert(0, args.site)
os.environ['VRA_DATA_DIR'] = str(out / 'private' / 'runtime')
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'

if args.serve:
    import uvicorn
    from backend.api import app
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=args.port,
                                         log_level='warning', access_log=False))
    def shutdown():
        sys.stdin.buffer.read(1)
        server.should_exit = True
    threading.Thread(target=shutdown, daemon=True).start()
    server.run()
    raise SystemExit(0)

import httpx
from backend.private_storage import private_mkdir

if sys.platform != 'win32' or args.seconds < 60 or args.interval < 4:
    raise ValueError('Windows local probe, minimum 60 seconds, interval >= 4 seconds')
out.mkdir(parents=True, exist_ok=False)
private_mkdir(out / 'private')
rounds = math.ceil(args.seconds / args.interval)
code_hashes = {str(p.relative_to(source)).replace('\\', '/'): sha(p.read_bytes())
               for p in sorted((source / 'backend').glob('*.py'))}
raw_file = b'{"source":"Independent synthetic material reference","field_measurement":false}\n'
frozen = {'application_commit': args.commit, 'source_hashes': code_hashes,
    'harness_sha256': sha(Path(__file__).read_bytes()), 'users': 4,
    'duration_seconds': args.seconds, 'interval_seconds': args.interval, 'rounds': rounds,
    'steady_requests_per_round': 8, 'target_steady_request_rate': 8 / args.interval,
    'restart_before_round': rounds // 2, 'withdraw_before_round': rounds // 4,
    'race_before_rounds': [rounds // 10, rounds * 7 // 10],
    'latency_limits_ms': {'p95': 2000, 'p99': 5000},
    'resource_limits': {'private_peak_bytes': 512 * 1024**2,
                        'private_growth_per_epoch_bytes': 128 * 1024**2, 'handles_peak': 2048},
    'numeric_tolerance_absolute': 1e-12, 'source_file_sha256': sha(raw_file),
    'oracles': [], 'scope': 'Real local HTTP, thermal writes/reads/HTML, file download, '
       'tenant isolation, invalid inputs, evidence CAS and invalidation, graceful restart. '
       'No EnergyPlus/LLM/parser job load, no browser or production/24-hour acceptance.',
    'criteria': ['all expected status codes', 'all saved numeric outputs match Decimal oracle',
        'no foreign project read', 'exactly one revision winner', 'stale result is null',
        'rejected evidence prevents new results', 'all acknowledged records and source bytes survive restart',
        'all reports equal their JSON record', 'SQLite integrity_check ok',
        'latency and resource limits respected', 'source code unchanged', 'service exits cleanly']}
for i in range(4):
    thickness = Decimal(137 + i * 29) / 1000
    conductivity = Decimal(43 + i * 7) / 100
    insulation = Decimal(35 + i * 5) / 1000
    ins_k = Decimal(31 + i * 3) / 1000
    total = Decimal('.13') + Decimal('.04') + thickness / conductivity + insulation / ins_k
    body = {'name': f'Isolated concurrency wall {i}', 'rsi_m2k_w': .13, 'rse_m2k_w': .04,
        'surface_basis': 'Synthetic explicit films', 'application': 'Synthetic uniform dry wall',
        'layers': [
            {'name': 'substrate', 'thickness': int(thickness * 1000), 'thickness_unit': 'mm',
             'conductivity': float(conductivity), 'conductivity_unit': 'W/(m K)',
             'source': 'Frozen synthetic source', 'correction_basis': 'Dry declared reference'},
            {'name': 'insulation', 'thickness': float(insulation * 100), 'thickness_unit': 'cm',
             'conductivity': int(ins_k * 1000), 'conductivity_unit': 'mW/(m K)',
             'source': 'Frozen synthetic source', 'correction_basis': 'Dry declared reference'}]}
    frozen['oracles'].append({'input': body, 'total_resistance_m2k_w': str(total),
                              'u_w_m2k': str(Decimal(1) / total)})
write(out / 'frozen.json', frozen)
lock = threading.Lock(); requests = []; checks = []; samples = []; users = []
process = None; epoch = 0; completed = 0; start = time.monotonic()


def check(name, passed, detail=None):
    entry = {'name': name, 'passed': bool(passed)}
    if detail is not None:
        entry['detail'] = detail
    with lock:
        checks.append(entry)
        with (out / 'checks.jsonl').open('a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    if not passed:
        raise AssertionError(name)


def request(client, method, path, expected=200, **kwargs):
    then = time.perf_counter()
    response = client.request(method, path, **kwargs)
    row = {'method': method, 'path': path, 'status': response.status_code,
           'expected': expected, 'elapsed_ms': (time.perf_counter() - then) * 1000,
           'response_sha256': sha(response.content), 'bytes': len(response.content), 'epoch': epoch}
    # Authentication responses contain ephemeral tokens; never store their hashes/bodies.
    if path.startswith('/api/auth/'):
        row.pop('response_sha256')
    with lock:
        requests.append(row)
        with (out / 'requests.jsonl').open('a', encoding='utf-8') as f:
            f.write(json.dumps(row) + '\n')
    accepted = expected if isinstance(expected, tuple) else (expected,)
    if response.status_code not in accepted:
        raise AssertionError(f'{method} {path}: expected {expected}, got {response.status_code}')
    return response


def start_server():
    global process
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
    env = dict(os.environ); env['PYTHONUTF8'] = '1'
    python = getattr(sys, '_base_executable', sys.executable)
    cmd = [python, '-B', '-X', 'utf8', str(Path(__file__).resolve()),
           '--source', str(source), '--output', str(out), '--commit', args.commit,
           '--serve', '--site', sysconfig.get_paths()['purelib'], '--port', str(port)]
    with (out / f'server-{epoch}.log').open('xb') as log:
        process = subprocess.Popen(cmd, cwd=source, env=env, stdin=subprocess.PIPE,
            stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
    base = f'http://127.0.0.1:{port}'
    with httpx.Client(base_url=base, trust_env=False, timeout=2) as probe:
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise AssertionError('Isolated service failed to start')
            try:
                r = probe.get('/api/health')
                if r.status_code == 200 and r.json()['worker_alive']:
                    return base
            except httpx.TransportError:
                pass
            time.sleep(.1)
    raise AssertionError('Isolated service readiness timed out')


def stop_server():
    if process is not None and process.poll() is None:
        process.stdin.close()
        try:
            process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            process.kill(); process.wait(timeout=5)
            raise AssertionError('Isolated service required forced termination')
        check('service graceful exit', process.returncode == 0)


def snapshot():
    with sqlite3.connect(out / 'private/runtime/vra.sqlite3') as con:
        rows = con.execute('SELECT kind,id,revision,project_id,body FROM records ORDER BY kind,id,revision').fetchall()
        integrity = con.execute('PRAGMA integrity_check').fetchone()[0]
    files = {p.name: sha(p.read_bytes()) for p in (out / 'private/runtime/files').iterdir() if p.is_file()}
    return {'record_rows': len(rows), 'records_sha256': sha(json.dumps(rows, ensure_ascii=False).encode()),
            'files': files, 'integrity_check': integrity}


def sample(round_number):
    row = {'round': round_number, 'epoch': epoch, 'elapsed_seconds': time.monotonic() - start,
           **memory(process.pid)}
    samples.append(row)
    with (out / 'resources.jsonl').open('a', encoding='utf-8') as f:
        f.write(json.dumps(row) + '\n')


def numeric(user, record):
    result = record.get('result')
    okay = record['project_id'] == user['pid'] and record['status'] == 'calculated' and result is not None
    if okay:
        for key in ('total_resistance_m2k_w', 'u_w_m2k'):
            okay = okay and abs(Decimal(str(result[key])) - Decimal(user['oracle'][key])) <= Decimal('1e-12')
        okay = okay and result['compliance_status'] == 'NOT_ASSESSED' and result['energy_saving_rate'] is None
    check('owner and independent thermal result', okay)


def create_thermal(user):
    body = json.loads(json.dumps(user['oracle']['input']))
    for layer in body['layers']:
        layer['evidence_id'] = user['eid']
    record = request(user['client'], 'POST', user['base'] + '/thermal', 201, json=body).json()
    numeric(user, record)
    user['current'] = record
    user['saved'].append({'thermal_id': record['thermal_id'], 'hash': record['hash'],
                          'evidence_id': user['eid']})
    return record


def add_evidence(user):
    value = request(user['client'], 'POST', user['base'] + '/evidence', 201, json={
        'type': 'literature', 'name': 'Synthetic local soak source', 'source_file': user['fid'],
        'source_locator': 'entire synthetic text', 'authority': 'Test author',
        'permission': 'Synthetic reference only', 'acquisition_method': 'Frozen test input',
        'responsible_person': 'Local test', 'status': 'IMPORTED'}).json()
    user['eid'] = value['evidence_id']; user['revision'] = value['revision']


def report_matches(user):
    record = user['current']
    page = request(user['client'], 'GET', user['base'] + '/thermal/' + record['thermal_id'] + '/report.html').text
    embedded = json.loads(html.unescape(page.split('<pre>', 1)[1].split('</pre>', 1)[0]))
    check('HTML contains same current record', embedded == record)


def iteration(user, index):
    client, base = user['client'], user['base']
    if index % 10 == 0:
        create_thermal(user)
        result = request(client, 'GET', base + '/thermal/' + user['current']['thermal_id']).json()
        numeric(user, result)
    elif index % 10 == 1:
        data = request(client, 'GET', base + '/files/' + user['fid']).content
        check('original bytes unchanged', data == raw_file)
        report_matches(user)
    elif index % 10 == 2:
        request(client, 'GET', user['foreign'], 404)
        bad = json.loads(json.dumps(user['oracle']['input'])); bad['layers'][0]['thickness'] = -1
        request(client, 'POST', base + '/thermal', 422, json=bad)
    else:
        data = request(client, 'GET', base + '/thermal/' + user['current']['thermal_id']).json()
        numeric(user, data)
        projects = request(client, 'GET', '/api/projects').json()
        check('project list is tenant scoped', {p['project_id'] for p in projects} == {user['pid']})


def race(pool, user):
    path = user['base'] + '/evidence/' + user['eid']
    before = request(user['client'], 'GET', path + '/history').json()
    barrier = threading.Barrier(4)
    def update(i):
        barrier.wait(timeout=10)
        return request(user['client'], 'PATCH', path, (200, 409), json={'expected_revision': user['revision'],
            'review_state': 'confirmed', 'responsible_person': 'Concurrent test',
            'review_note': f'Explicit synthetic review attempt {i}'})
    responses = list(pool.map(update, range(4)))
    statuses = sorted(r.status_code for r in responses)
    check('exactly one concurrent revision winner', statuses == [200, 409, 409, 409], statuses)
    after = request(user['client'], 'GET', path + '/history').json()
    check('no overwritten evidence revision', len(after) == len(before) + 1 and after[:-1] == before)
    user['revision'] += 1
    stale = request(user['client'], 'GET', user['base'] + '/thermal/' + user['current']['thermal_id']).json()
    check('changed revision invalidates old calculation', stale['status'] == 'stale' and stale['result'] is None)
    create_thermal(user)


def withdraw(user):
    request(user['client'], 'PATCH', user['base'] + '/evidence/' + user['eid'], json={
        'expected_revision': user['revision'], 'review_state': 'rejected',
        'responsible_person': 'Local test', 'review_note': 'Synthetic withdrawal at frozen checkpoint'})
    old = request(user['client'], 'GET', user['base'] + '/thermal/' + user['current']['thermal_id']).json()
    check('withdrawal retracts calculation', old['status'] == 'stale' and old['result'] is None)
    body = json.loads(json.dumps(user['oracle']['input']))
    for layer in body['layers']:
        layer['evidence_id'] = user['eid']
    request(user['client'], 'POST', user['base'] + '/thermal', 409, json=body)
    user['retired'].add(user['eid'])
    add_evidence(user); create_thermal(user)


error = None
try:
    base_url = start_server()
    for i, oracle in enumerate(frozen['oracles']):
        client = httpx.Client(base_url=base_url, trust_env=False, timeout=15)
        auth = request(client, 'POST', '/api/auth/register', json={
            'username': f'soak_{i}_{secrets.token_hex(4)}', 'password': secrets.token_urlsafe(32),
            'display_name': f'Isolated soak {i}'}).json()
        client.headers['X-CSRF-Token'] = auth['csrf_token']; auth = None
        project = request(client, 'POST', '/api/projects', 201, json={
            'name': f'Isolated soak project {i}', 'data_nature': 'engineering_reference',
            'building': {'use': 'office', 'location': 'synthetic', 'region': 'synthetic', 'area_m2': 121 + i}}).json()
        user = {'client': client, 'pid': project['project_id'], 'base': '/api/projects/' + project['project_id'],
                'oracle': oracle, 'saved': [], 'retired': set()}
        users.append(user)
        user['fid'] = request(client, 'POST', user['base'] + '/files', 201,
                              files={'file': ('synthetic.json', raw_file)}).json()['file_id']
        add_evidence(user); create_thermal(user)
    for i, user in enumerate(users):
        user['foreign'] = users[(i + 1) % 4]['base']
    with httpx.Client(base_url=base_url, trust_env=False, timeout=15) as anonymous:
        request(anonymous, 'GET', users[0]['base'], 401)
    request(users[0]['client'], 'POST', users[0]['base'] + '/thermal', 403,
            headers={'X-CSRF-Token': 'invalid'}, json=users[0]['oracle']['input'])
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        workload_start = time.monotonic()
        for index in range(rounds):
            if index in frozen['race_before_rounds']:
                race(pool, users[0])
            if index == frozen['withdraw_before_round']:
                list(pool.map(withdraw, users))
            if index == frozen['restart_before_round']:
                before = snapshot(); write(out / 'before-restart.json', before)
                stop_server(); epoch += 1
                base_url = start_server()
                for user in users:
                    user['client'].base_url = base_url
                after = snapshot(); write(out / 'after-restart.json', after)
                check('all committed records and source files survive restart', before == after)
            list(pool.map(lambda user: iteration(user, index), users))
            completed = index + 1
            if index % 5 == 0:
                sample(index)
                write(out / 'progress.json', {'completed_rounds': completed, 'total_rounds': rounds,
                    'elapsed_seconds': time.monotonic() - workload_start, 'requests': len(requests),
                    'status': 'running', 'epoch': epoch})
            delay = workload_start + (index + 1) * args.interval - time.monotonic()
            if delay > 0:
                time.sleep(delay)
        elapsed = time.monotonic() - workload_start
        check('frozen workload duration completed', elapsed >= args.seconds)
        # Final acknowledged-record audit (read-only, max four simultaneous requests).
        def audit_user(user):
            rows = request(user['client'], 'GET', user['base'] + '/thermal').json()
            saved = {r['thermal_id']: r for r in user['saved']}
            check('no committed record lost or spurious record created', set(saved) == {r['thermal_id'] for r in rows})
            for row in rows:
                old = saved[row['thermal_id']]
                check('immutable saved calculation hash preserved', row['hash'] == old['hash'])
                if old['evidence_id'] in user['retired']:
                    check('withdrawn historical result remains unavailable', row['status'] == 'stale' and row['result'] is None)
            report_matches(user)
        list(pool.map(audit_user, users))
    sample(rounds)
    final = snapshot(); write(out / 'final-database.json', final)
    check('SQLite integrity', final['integrity_check'] == 'ok')
    check('source code unchanged', code_hashes == {p: sha((source / p).read_bytes()) for p in code_hashes})
    timing = sorted(r['elapsed_ms'] for r in requests)
    percentiles = {f'p{p}': timing[math.ceil(len(timing) * p / 100) - 1] for p in (50, 95, 99)}
    check('p95 latency <= 2000 ms', percentiles['p95'] <= 2000, percentiles['p95'])
    check('p99 latency <= 5000 ms', percentiles['p99'] <= 5000, percentiles['p99'])
    check('private memory within 512 MiB', max(r['private_bytes'] for r in samples) <= 512 * 1024**2)
    check('handles within 2048', max(r['handles'] for r in samples) <= 2048)
    for e in (0, 1):
        group = [r for r in samples if r['epoch'] == e]
        growth = max(r['private_bytes'] for r in group) - group[0]['private_bytes']
        check(f'epoch {e} memory growth within 128 MiB', growth <= 128 * 1024**2, growth)
    write(out / 'metrics.json', {'duration_seconds': elapsed, 'requests': len(requests),
        'latency_ms': {**percentiles, 'max': max(timing)},
        'saved_calculations': sum(len(u['saved']) for u in users),
        'private_peak_bytes': max(r['private_bytes'] for r in samples),
        'handles_peak': max(r['handles'] for r in samples)})
except Exception as exc:
    error = {'type': type(exc).__name__, 'message': str(exc), 'traceback': traceback.format_exc()}
    write(out / 'failure.json', error)
finally:
    try:
        stop_server()
    except Exception as exc:
        error = error or {'type': type(exc).__name__, 'message': str(exc)}
    for user in users:
        user['client'].close()
    write(out / 'result.json', {'status': 'passed' if error is None else 'failed',
        'completed_rounds': completed, 'planned_rounds': rounds, 'request_count': len(requests),
        'checks': len(checks), 'failed_checks': [x for x in checks if not x['passed']], 'error': error,
        'server_exit_code': process.returncode if process else None,
        'runtime_private': True, 'runtime_published': False})
    print(json.dumps({'output': str(out), 'status': 'passed' if error is None else 'failed',
                      'completed_rounds': completed, 'requests': len(requests)}), flush=True)
if error:
    raise SystemExit(1)
