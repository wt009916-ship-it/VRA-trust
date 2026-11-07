"""Actual native receipt size, duplicated only for the six-entry transport counterexample."""
import hashlib
import json
import sys
from pathlib import Path

repo = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo))
from backend import core
from backend.agent import Agent
from backend.agent_simulation import model_result, page

source = repo / 'output/playwright/designload-20261107/report.json'
run = json.loads(source.read_text(encoding='utf-8'))['run']
receipt = run['metrics']['zone_design_loads']
size = lambda value: len(json.dumps(value, ensure_ascii=False))
result = {
    'purpose': 'Payload-size counterexample using one actual native run duplicated six times; not six executed runs and not a live model test',
    'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'run_id': run['run_id'],
    'old_list_characters': size([run] * 6), 'new_list_characters': size(model_result('simulation_result', [run] * 6)),
    'context_limit': 64000, 'tool_definitions_characters': size(Agent.tools(None)),
    'single_page_characters': [size(page(run, offset, core.hash_json(receipt))) for offset in (0, 5)],
    'source_versions': {name: core.sha(repo / 'backend' / name) for name in ('agent.py', 'agent_simulation.py', 'agent_capabilities.py')},
}
assert result['old_list_characters'] > 64000
assert result['new_list_characters'] + sum(result['single_page_characters']) < 60000
assert result['tool_definitions_characters'] < 20000
with (Path(__file__).parent / 'agent-context-counterexample-v1.json').open('x', encoding='utf-8') as handle:
    json.dump(result, handle, ensure_ascii=False, indent=2)
print(json.dumps(result, ensure_ascii=False))
