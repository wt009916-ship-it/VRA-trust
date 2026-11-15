"""Replay the previously rejected request against the unchanged real local model.

This validates transport/context recovery only, not completion of integrated B06.
Original captures remain read-only. No browser or application database is used.
"""
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time

import httpx

BASE = Path(__file__).parent
ROOT = Path('D:/稀土agent-稀土制暖全流程/.codex_work/vra-resource-leveling-20261115')
MODEL = Path('C:/Users/18483/AppData/Local/Temp/vra-qwen35-9b-20261108/Qwen3.5-9B-Q4_K_M.gguf')
EXE = Path('E:/VRA-local-model-20261106/runtime/llama-server.exe')
sys.path.insert(0, str(ROOT))
from backend import agent_actions


def sha(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    out = BASE / 'context-replay-v2'
    out.mkdir(exist_ok=False)
    source = BASE / 'baseline-v2/model-calls/call-013.json'
    capture = json.loads(source.read_text(encoding='utf-8'))
    receipt = {'scope': 'Original rejected model request only; not complete task acceptance',
               'source_sha256': sha(source), 'harness_sha256': sha(Path(__file__)), 'model_sha256': sha(MODEL), 'runtime_sha256': sha(EXE),
               'product_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
               'working_files': {p: sha(ROOT / p) for p in ['backend/agent_actions.py', 'backend/agent_schema_sharing.py']},
               'completed': False, 'original_test_result_changed': False}
    assert receipt['model_sha256'] == '03b74727a860a56338e042c4420bb3f04b2fec5734175f4cb9fa853daf52b7e8'
    assert receipt['runtime_sha256'] == '00d50686815af38249d0218c91558fbd0e9093ac8c074bac86196907f4305e31'
    payload = {'model': 'vra-nine-b-tools', 'max_tokens': 1400, 'temperature': 0,
               'chat_template_kwargs': {'enable_thinking': False}, 'stream': False,
               **agent_actions.payload(capture['messages'], capture['tools'], strict=True)}
    save(out / 'request.json', payload)
    receipt['request_sha256'] = sha(out / 'request.json')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    token = secrets.token_urlsafe(36)
    env = {k: v for k, v in os.environ.items() if k.upper() in {'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'COMSPEC', 'SYSTEMDRIVE'}}
    env.update(PATH=str(EXE.parent) + os.pathsep + str(Path(os.environ['SystemRoot']) / 'System32'), LLAMA_API_KEY=token)
    args = [str(EXE), '-m', str(MODEL), '--host', '127.0.0.1', '--port', str(port), '--alias', 'vra-nine-b-tools',
            '-c', '16384', '-np', '1', '-t', '4', '-ngl', '99', '--fit', 'off', '--cache-ram', '0',
            '--no-context-shift', '--offline', '--no-webui', '--no-agent', '--no-webui-mcp-proxy',
            '--no-slots', '--jinja', '--reasoning', 'off', '--timeout', '120']
    receipt['model_arguments'] = args
    print('Starting fixed local model; original 16K context and payload contents retained', flush=True)
    process = None
    try:
        with (out / 'model.log').open('xb') as log:
            process = subprocess.Popen(args, cwd=EXE.parent, env=env, stdout=log, stderr=log,
                                       stdin=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
            with httpx.Client(base_url=f'http://127.0.0.1:{port}', timeout=120, trust_env=False) as client:
                for _ in range(120):
                    assert process.poll() is None, 'Model process stopped'
                    try:
                        if client.get('/health', timeout=2).status_code == 200:
                            break
                    except httpx.HTTPError as exc:
                        if '10013' in str(exc) or '访问权限不允许' in str(exc):
                            raise RuntimeError('Loopback denied by execution sandbox') from exc
                    time.sleep(1)
                else:
                    raise TimeoutError('Model startup')
                assert client.post('/v1/chat/completions', json={}).status_code == 401
                print('Model ready; replaying original rejected request through current action schema', flush=True)
                start = time.monotonic()
                result = client.post('/v1/chat/completions', json=payload, headers={'Authorization': 'Bearer ' + token})
                receipt.update(http_status=result.status_code, seconds=round(time.monotonic() - start, 3))
                response = result.json()
                save(out / 'response.json', response)
                result.raise_for_status()
                assert response['model'] == payload['model']
                assert response['choices'][0]['finish_reason'] == 'stop'
                decoded = agent_actions.decode(response['choices'][0]['message'], capture['tools'])
                save(out / 'decoded.json', decoded)
                receipt.update(completed=True, usage=response.get('usage'))
    except Exception as exc:
        receipt['error'] = type(exc).__name__ + ': ' + str(exc)
        raise
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        receipt['process_stopped'] = process is None or process.poll() is not None
        save(out / 'receipt.json', receipt)
        print(json.dumps(receipt, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
