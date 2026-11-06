"""Freeze current source and generate new evidence on C:; no old-run rewriting."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

repo = Path(__file__).resolve().parents[2]
out = Path(__file__).resolve().parent
sys.path.insert(0, str(repo))
from backend.private_storage import private_mkdir
base = private_mkdir(Path(tempfile.gettempdir()) / ('vra-weather-v2-' + uuid.uuid4().hex))
root = base / 'source'
root.mkdir()
env = dict(os.environ, VRA_DATA_DIR=str(base / 'bootstrap'), ENERGYPLUS_EXE='F:/EnergyPlusV9-0-1/energyplus.exe',
           PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1')
with (out / 'schema-export-v2.log').open('xb') as log:
    r = subprocess.run([sys.executable, 'scripts/export_contract.py'], cwd=repo, env=env, stdout=log, stderr=subprocess.STDOUT)
assert r.returncode == 0
old = json.loads((repo / 'validation/ifc-topology-20261107/release-final/windows-source.json').read_text())
names = {item['path'] for item in old['files']} | {'backend/weather_quality.py', 'tests/test_weather_quality.py',
    'frontend/src/weather-quality.js', 'frontend/tests/weather-quality.test.js', 'scripts/verify_weather_reference.py','tests/test_live_inventory.py','frontend/src/simulation-gate.js','frontend/tests/simulation-gate.test.js'}
records = []
for name in sorted(names):
    source = repo / name
    if not source.is_file():
        continue
    raw = source.read_bytes()
    target = root / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    records.append({'path': name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
record = {'root': str(root), 'base': str(base), 'files': records, 'reused_yearly_reference_calls': 0}
with (out / 'windows-source-v2.json').open('x', encoding='utf-8') as stream:
    json.dump(record, stream, indent=2)
for name, command in [
    ('weather-native-v2', [sys.executable, 'scripts/verify_weather_reference.py', str(base / 'weather'), 'F:/EnergyPlusV9-0-1/WeatherData']),
    ('yearly-reference-v2', [sys.executable, 'scripts/run_reference.py']),
]:
    with (out / (name + '.log')).open('xb') as log:
        process = subprocess.run(command, cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=1200)
    print(json.dumps({'stage': name, 'exit_code': process.returncode, 'root': str(root)}), flush=True)
    if process.returncode:
        raise SystemExit(process.returncode)
summary = json.loads((base / 'weather/weather-reference.json').read_text())
with (out / 'weather-native-v2.json').open('x', encoding='utf-8') as stream:
    json.dump(summary, stream, indent=2)
with (out / 'windows-full-v2.log').open('xb') as log:
    result = subprocess.run([sys.executable, '-m', 'pytest', '-q', '-rs'], cwd=root, env=env,
                            stdout=log, stderr=subprocess.STDOUT, timeout=2100)
print(json.dumps({'stage': 'full', 'exit_code': result.returncode}), flush=True)
raise SystemExit(result.returncode)
