"""Run isolated targeted checks with explicitly pinned import root; retain first failure."""
from pathlib import Path
import argparse
import json
import os
import subprocess
import sys

parser = argparse.ArgumentParser()
parser.add_argument('--baseline', action='store_true')
args = parser.parse_args()
candidate = Path('C:/Users/18483/AppData/Local/Temp/vra-agent-service-recovery-20261108')
repo = Path('C:/Users/18483/AppData/Local/Temp/vra-drawing-components-20261108') if args.baseline else candidate
out = Path('C:/Users/18483/AppData/Local/Temp/vra-service-recovery-checks-20261108')
out.mkdir(exist_ok=True)
label = 'baseline' if args.baseline else 'candidate-first'
log = out / (label + '.txt')
assert not log.exists(), 'Preserve first run; use a new explicitly named follow-up for changed failures'
env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONPATH': str(repo) + os.pathsep + str(repo / 'tests')}
# Import backend before pytest can add test directories; baseline tests live in the
# independent candidate, while every product module resolves from the baseline.
code = "import backend,pytest; print('PRODUCT_IMPORT_ROOT='+str(backend.__path__),flush=True); raise SystemExit(pytest.main(" 
tests = [str(candidate / 'tests/test_agent_service_recovery.py')]
if args.baseline:
    tests += ['-k', 'inference_outage_continues and local_model']
else:
    tests += [str(candidate / 'tests/test_local_model.py'), str(candidate / 'tests/test_agent_calculations.py'),
              str(candidate / 'tests/test_agent_batch_tools.py')]
tests += ['-q', '-p', 'no:cacheprovider', '--basetemp', str(out / (label + '-tmp'))]
code += repr(tests) + '))'
with log.open('x', encoding='utf-8') as stream:
    result = subprocess.run([sys.executable, '-B', '-X', 'utf8', '-c', code], cwd=repo, env=env,
                            stdout=stream, stderr=subprocess.STDOUT)
print(log.read_text(encoding='utf-8')[-10000:])
print('EXIT_CODE=' + str(result.returncode), flush=True)
(out / (label + '.json')).write_text(json.dumps({'exit_code': result.returncode, 'repo': str(repo), 'log': str(log)}), encoding='utf-8')
raise SystemExit(result.returncode)
