import hashlib
import json
from pathlib import Path
import shutil
import statistics

BASE = Path(__file__).parent
ROOT = Path('D:/稀土agent-稀土制暖全流程/.codex_work/vra-resource-leveling-20261115')
rows = []
frozen = []
for name in ('probe-v1', 'probe-thinking-v1'):
    folder = BASE / name
    receipt = json.loads((folder / 'receipt.json').read_text(encoding='utf-8'))
    assessment = json.loads((folder / 'assessment.json').read_text(encoding='utf-8'))
    assert receipt['completed'] and receipt['process_stopped']
    frozen.append((folder / 'frozen.json').read_bytes())
    durations = [row['seconds'] for row in receipt['results']]
    rows.append({'name': name, 'planner_only_passed': assessment['passed'], 'total': assessment['total'],
                 'structure_valid': sum(row['completed'] for row in receipt['results']),
                 'sequential_request_seconds': round(sum(durations), 3),
                 'median_request_seconds': statistics.median(durations),
                 'model_sha256': receipt['model_sha256'], 'runtime_sha256': receipt['runtime_sha256'],
                 'planner_sha256': receipt['planner_sha256'], 'frozen_sha256': receipt['frozen_sha256'],
                 'reasoning': name == 'probe-thinking-v1',
                 'output_token_cap': 2200 if name == 'probe-thinking-v1' else 1400,
                 'reasoning_budget': 768 if name == 'probe-thinking-v1' else 0})
assert frozen[0] == frozen[1]
for key in ('model_sha256', 'runtime_sha256', 'planner_sha256', 'frozen_sha256'):
    assert rows[0][key] == rows[1][key]
snapshot = BASE / 'planner-v1-source-snapshot'
snapshot.mkdir(exist_ok=True)
hashes = {}
for name in ('backend/agent_task_plan.py', 'tests/test_agent_task_plan.py'):
    source = ROOT / name
    target = snapshot / name
    target.parent.mkdir(exist_ok=True, parents=True)
    if target.exists():
        assert target.read_bytes() == source.read_bytes()
    else:
        shutil.copyfile(source, target)
    hashes[name] = hashlib.sha256(target.read_bytes()).hexdigest()
assert hashes['backend/agent_task_plan.py'] == rows[0]['planner_sha256']
result = {'scope': 'Paired exploratory planning-only comparison; no tool execution or application acceptance',
          'same_frozen_cases': True, 'cases': 'Six known H regressions and two new planner-only probes',
          'runs': rows, 'source_snapshot': hashes, 'score_delta': 0,
          'decision': 'Do not enable this planner or change application reasoning defaults. Stop budget-only tuning on these cases. A subsequent implementation must bind requested outputs and source references to question evidence, then pass whole-task unseen acceptance.',
          'limitations': ['One run per configuration; not a statistical estimate.',
                         'Reasoning mode and output cap changed together; no isolated causal claim.',
                         'Equal pass count does not imply identical behavior.',
                         'No production code integration, deployment, training or browser validation.']}
(BASE / 'comparison.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'runs': [{'name': row['name'], 'passed': row['planner_only_passed'], 'total': row['total'], 'seconds': row['sequential_request_seconds']} for row in rows], 'source_snapshot_verified': True, 'score_delta': 0}))
