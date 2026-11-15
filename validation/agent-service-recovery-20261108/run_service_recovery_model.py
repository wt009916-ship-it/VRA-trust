"""One frozen new task via real local model and loopback fault proxy. No retries of this harness."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
from fractions import Fraction
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

parser = argparse.ArgumentParser()
parser.add_argument('--repo', required=True)
parser.add_argument('--output', required=True)
args = parser.parse_args()
root = Path(args.repo).resolve()
out = Path(args.output).resolve()
assert not out.exists()
out.mkdir()
sys.path.insert(0, str(root))
os.environ['VRA_DATA_DIR'] = str(out / 'private/api')
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'

import httpx
from fastapi.testclient import TestClient
from backend.private_storage import private_mkdir

private_mkdir(out / 'private')
from backend.api import create_app
home = Path(__file__).parent
runtime = json.loads((home.parents[1] / 'vra-trust/validation/local-model-20261106/prepared-runtime.json').read_text())
cache = Path(runtime['root'])
exe = cache / 'runtime/llama-server.exe'
model = cache / 'models/Qwen3-4B-Q4_K_M.gguf'

def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def write(name, value):
    (out / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')

def port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]

assert sha(model) == runtime['verified'][2]['sha256']
model_port = port()
token = secrets.token_urlsafe(32)
os.environ['VRA_LOCAL_MODEL_TOKEN'] = token
body = {'message': '执行本轮明确授权的 wall 计算计划，读取结果，交付总热阻和传热系数及其单位；不要增加其他计算。',
        'mode': 'local_model', 'allow_compute': True,
        'calculation_plans': [{'plan_key': 'wall', 'kind': 'thermal', 'execution_authorized': True,
            'input': {'name': 'Public-formula recovery reference', 'rsi_m2k_w': 0.13, 'rse_m2k_w': 0.04,
                      'surface_basis': 'Synthetic reference film resistances, not a compliance default',
                      'application': 'Uniform opaque reference layer, no thermal bridge',
                      'layers': [{'name': 'Reference layer', 'thickness': 175.0, 'thickness_unit': 'mm',
                                  'conductivity': 0.35, 'conductivity_unit': 'W/(m K)', 'correction_factor': 1.0,
                                  'correction_basis': 'Synthetic declared correction', 'source': 'Independent arithmetic reference'}]}}]}
# Exact input schema must be checked before launching; never repair after inference begins.
from backend.agent import Chat
Chat.model_validate(body)
expected_r = Fraction(13, 100) + Fraction(4, 100) + Fraction(175, 1000) / Fraction(35, 100)
write('frozen.json', {'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip(),
    'source_hashes': {p.relative_to(root).as_posix(): sha(p) for p in (root / 'backend').glob('*.py')},
    'harness_sha256': sha(Path(__file__)), 'request': body, 'fault': '503 on second inference request only',
    'model_sha256': runtime['verified'][2]['sha256'], 'expected_R': str(expected_r), 'expected_U': str(1 / expected_r),
    'criteria': ['one saved thermal record before injected failure', 'same task resumes and delivers R and U',
                 'one calculation execution total', 'failure event preserved', 'at most 5 inference requests and 15 events'],
    'scope': 'One new real-model task with deliberate transport fault; not broad intent accuracy or production recovery.'})
proxy_events = []
client = httpx.Client(timeout=130, trust_env=False)
app = create_app(out / 'private/api', start_worker=False)
project_id = None

class Proxy(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        if self.path != '/v1/chat/completions' or self.headers.get('Authorization') != 'Bearer ' + token:
            self.send_response(401)
            self.end_headers()
            return
        raw = self.rfile.read(int(self.headers['Content-Length']))
        event = {'number': len(proxy_events) + 1, 'request_sha256': hashlib.sha256(raw).hexdigest(),
                 'thermal_records_before_request': len(app.state.agent.store.list('thermal', project_id))}
        proxy_events.append(event)
        if event['number'] == 2:
            status, data = 503, b'{"error":"deliberate isolated availability fault"}'
        else:
            response = client.post(f'http://127.0.0.1:{model_port}/v1/chat/completions', content=raw,
                                   headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
            status, data = response.status_code, response.content
            # Actual generated answer is retained, never a fabricated planner answer.
            (out / f'model-response-{event["number"]}.json').write_bytes(data)
        event['status'] = status
        write('proxy-events.json', proxy_events)
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

proxy = ThreadingHTTPServer(('127.0.0.1', 0), Proxy)
thread = threading.Thread(target=proxy.serve_forever, daemon=True)
llm = None
try:
    model_env = {k: v for k, v in os.environ.items() if k.upper() in {'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'COMSPEC', 'SYSTEMDRIVE'}}
    model_env.update(PATH=str(exe.parent) + os.pathsep + str(Path(os.environ['SystemRoot']) / 'System32'), LLAMA_API_KEY=token)
    with (out / 'model.log').open('xb') as log:
        llm = subprocess.Popen([str(exe), '-m', str(model), '--host', '127.0.0.1', '--port', str(model_port),
            '--alias', 'vra-recovery-reference', '-c', '8192', '-np', '1', '-t', '4', '-ngl', '99',
            '--fit', 'off', '--cache-ram', '0', '--no-context-shift', '--offline', '--no-webui', '--no-agent',
            '--no-webui-mcp-proxy', '--no-slots', '--jinja', '--reasoning', 'off', '--timeout', '120'],
            cwd=exe.parent, env=model_env, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
        for _ in range(120):
            assert llm.poll() is None, 'Model startup failed'
            try:
                if client.get(f'http://127.0.0.1:{model_port}/health', timeout=2).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            time.sleep(1)
        else:
            raise AssertionError('Model not ready')
        thread.start()
        with TestClient(app) as c:
            auth = c.post('/api/auth/register', json={'username': 'recovery_reference', 'display_name': 'Isolated reference', 'password': secrets.token_urlsafe(32)})
            assert auth.status_code == 200, auth.status_code
            c.headers['X-CSRF-Token'] = auth.json()['csrf_token']
            settings = c.put('/api/developer/local-model', json={'enabled': True, 'port': proxy.server_port, 'model': 'vra-recovery-reference'})
            assert settings.status_code == 200
            project = c.post('/api/projects', json={'name': 'Service recovery reference', 'building': {'use': 'office', 'location': 'Synthetic', 'region': 'US-CO', 'area_m2': 510}})
            assert project.status_code == 201
            project_id = project.json()['project_id']
            response = c.post(f'/api/projects/{project_id}/agent/chat', json=body)
            assert response.status_code == 202, response.text
            task = response.json()
            for _ in range(600):
                task = c.get(f'/api/projects/{project_id}/agent/{task["agent_id"]}').json()
                if task['status'] != 'running':
                    break
                time.sleep(.5)
            write('task.json', task)
            records = app.state.agent.store.list('thermal', project_id)
            write('records.json', records)
            facts = {f['fact']: f for d in (task.get('answer') or {}).get('checked_statements', []) for f in d['facts']}
            checks = {'task_succeeded': task['status'] == 'succeeded', 'one_record': len(records) == 1,
                      'fault_after_save': len(proxy_events) >= 2 and proxy_events[1]['thermal_records_before_request'] == 1,
                      'one_calculation': sum(e['tool'] == 'calculation_execute' for e in task['events']) == 1,
                      'both_facts_only': set(facts) == {'total_resistance_m2k_w', 'u_w_m2k'},
                      'within_budget': len(proxy_events) <= 5 and len(task['events']) <= 15,
                      'failure_retained': any(e['tool'] == 'llm.request' and e['status'] == 'failed' for e in task['events'])}
            for key, value in [('total_resistance_m2k_w', expected_r), ('u_w_m2k', 1 / expected_r)]:
                checks[key] = key in facts and abs(float(facts[key]['value']) - float(value)) < 1e-10
            write('summary.json', {'checks': checks, 'passed': all(checks.values()), 'model_requests': len(proxy_events),
                                   'recovery_attempts': task.get('provider_recovery_attempts', 0)})
            print(json.dumps(checks, ensure_ascii=False), flush=True)
finally:
    if thread.is_alive():
        proxy.shutdown()
    proxy.server_close()
    client.close()
    if llm is not None and llm.poll() is None:
        llm.terminate()
        llm.wait(timeout=20)
    write('runtime-final.json', {'model_stopped': llm is None or llm.poll() is not None, 'proxy_closed': True})
