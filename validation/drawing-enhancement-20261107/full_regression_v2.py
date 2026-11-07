"""Run exact frozen candidate; reuse only validated, unchanged physics references."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

out = Path(__file__).resolve().parent
repo = out.parents[1]
platform = sys.argv[1]
assert platform in {'windows', 'linux'}
plan = json.loads((out / ('candidate-source-v2.json' if platform == 'windows' else 'linux-source-v1.json')).read_text())
root, base = Path(plan['root']), Path(plan['base'])
if platform == 'windows':
    engine = 'F:/EnergyPlusV9-0-1/energyplus.exe'
    prior = Path('C:/Users/18483/AppData/Local/Temp/vra-designload-final-1504e6d0f8314560851c199357a9ebc1/source')
else:
    assert os.getuid() == 65534
    ctx = json.loads((repo / 'validation/linux-isolation-20261105/linux-runtime-v2.json').read_text())
    engine = ctx['engine']
    prior = Path('/var/tmp/vra-linux-acceptance-ybic05cy/designload-final-dcff2b9a9f1f46678dfcf7d211068d1a/source')
for item in plan['files']:
    assert hashlib.sha256((root / item['path']).read_bytes()).hexdigest() == item['sha256'], item['path']
sys.path.insert(0, str(root))
os.environ['ENERGYPLUS_EXE'] = engine
from backend import core
assert core.code_hash() == '811cc91edfdfbed58f78d4b69bb52cbfde20a51b22fdcc68545a2b868d29d6ab'
assert not (root / 'runs').exists()
references = json.loads((prior / 'validation/reference_comparison.json').read_text())
copied = []
for view in references['results']:
    rid = view['run_id']
    assert rid.startswith('run_') and len(rid) == 36
    original, target = prior / 'runs' / rid, root / 'runs' / rid
    shutil.copytree(original, target)
    for p in sorted(original.rglob('*')):
        if p.is_file():
            rel = p.relative_to(original)
            digest = core.sha(p)
            assert core.sha(target / rel) == digest
            copied.append({'path': 'runs/' + rid + '/' + rel.as_posix(), 'sha256': digest})
    core.read_validated(target)
(root / 'validation').mkdir(exist_ok=True)
shutil.copyfile(prior / 'validation/reference_comparison.json', root / 'validation/reference_comparison.json')
receipt = {'platform': platform, 'application_commit': plan['application_commit'], 'root': str(root),
           'physics_hash': core.code_hash(), 'reference_origin': str(prior), 'copied_reference_files': copied,
           'notice': 'Prior design-load release native references reused byte-for-byte after unchanged physics hash and read_validated checks. No new annual reference simulation claimed.'}
with (out / (platform + '-full-source-v2.json')).open('x', encoding='utf-8') as f:
    json.dump(receipt, f, indent=2)
env = dict(os.environ, PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1', ENERGYPLUS_EXE=engine,
           VRA_DATA_DIR=str(base / 'full-bootstrap-v2'))
with (out / (platform + '-full-v2.log')).open('xb') as log:
    result = subprocess.run([sys.executable, '-m', 'pytest', '-q', '-rs', '-p', 'no:cacheprovider'], cwd=root,
                            env=env, stdout=log, stderr=subprocess.STDOUT, timeout=3000)
with (out / (platform + '-full-result-v2.json')).open('x', encoding='utf-8') as f:
    json.dump({'exit_code': result.returncode, 'application_commit': plan['application_commit']}, f)
print(json.dumps({'platform': platform, 'exit_code': result.returncode}), flush=True)
raise SystemExit(result.returncode)

