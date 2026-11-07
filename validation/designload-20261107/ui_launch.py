"""Start the verified source on localhost with the unchanged original data directory."""
import hashlib, json, os, socket, subprocess, sys, time, urllib.request
from pathlib import Path

out = Path(__file__).parent.resolve()
plan = json.loads((out / 'prototype-prepared-v1.json').read_text())
root = Path(plan['source'])
for row in plan['source_files']:
    assert hashlib.sha256((root / row['path']).read_bytes()).hexdigest() == row['sha256'], row['path']
for name, digest in plan['assets'].items():
    assert hashlib.sha256((root / 'frontend/dist' / name).read_bytes()).hexdigest() == digest
with socket.socket() as guard:
    guard.bind(('127.0.0.1', 18772))
env = dict(os.environ, VRA_DATA_DIR=plan['business_data'], ENERGYPLUS_EXE='F:/EnergyPlusV9-0-1/energyplus.exe',
           PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1', VRA_SOURCE_PROJECT_FILES='1000', VRA_SOURCE_TOTAL_FILES='1000')
startup = subprocess.STARTUPINFO(); startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW; startup.wShowWindow = 0
with (out / 'ui-server.log').open('xb') as log, (out / 'ui-server-error.log').open('xb') as error:
    proc = subprocess.Popen([sys.executable, '-X', 'utf8', '-m', 'uvicorn', 'backend.api:app', '--host', '127.0.0.1', '--port', '18772'],
                            cwd=root, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=error,
                            creationflags=subprocess.CREATE_NEW_CONSOLE, startupinfo=startup)
with (out / 'ui-server.pid').open('x') as stream:
    stream.write(str(proc.pid))
for _ in range(30):
    assert proc.poll() is None, 'Prototype startup failed'
    try:
        with urllib.request.urlopen('http://127.0.0.1:18772/api/health', timeout=2) as response:
            health = json.load(response)
        assert health['status'] == 'ok' and health['worker_alive']; break
    except OSError:
        time.sleep(1)
else:
    raise RuntimeError('Prototype health deadline exceeded')
with (out / 'prototype-started-v1.json').open('x', encoding='utf-8') as stream:
    json.dump({'pid': proc.pid, 'source': str(root), 'application_commit': plan['application_commit'], 'health': health}, stream, indent=2)
print(json.dumps({'launcher_pid': proc.pid, 'health': health}))
