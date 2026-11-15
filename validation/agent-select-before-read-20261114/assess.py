"""Independent checks against pre-inference task contract and arithmetic oracle."""
import hashlib
import json
import math
from fractions import Fraction
from pathlib import Path

root = Path.cwd()
base = root / 'validation/agent-select-before-read-20261114'
live = base / 'live-selection-f'
read = lambda name: json.loads((live / name).read_text(encoding='utf-8'))
receipt = read('receipt.json')
assert receipt['completed'] and receipt['processes_stopped']
frozen = read('frozen-tasks.json')
assert hashlib.sha256((live / 'frozen-tasks.json').read_bytes()).hexdigest() == receipt['frozen_tasks_sha256']
records = read('records-before.json')
oracle = read('independent-oracle.json')
ids = {k: next(v for field, v in record.items() if field in ('thermal_id', 'utility_id', 'enduse_id')) for k, record in records.items()}
thermal = {'layer_resistance_m2k_w': Fraction(160, 1000) / Fraction(8, 10) + Fraction(60, 1000) / (Fraction(40, 1000) * Fraction(12, 10))}
thermal['total_resistance_m2k_w'] = thermal['layer_resistance_m2k_w'] + Fraction(9, 100) + Fraction(7, 100)
thermal['u_w_m2k'] = 1 / thermal['total_resistance_m2k_w']
units = {'layer_resistance_m2k_w': 'm2 K/W', 'total_resistance_m2k_w': 'm2 K/W', 'u_w_m2k': 'W/(m2 K)', 'cvrmse_percent': '%', 'rmse_kwh': 'kWh', 'compared_hours': 'hour'}
rows = []
for case in frozen['tasks']:
    task = read(case['id'] + '-task.json')
    statements = (task.get('answer') or {}).get('checked_statements', [])
    actual = {row['record_id']: {f['fact'] for f in row['facts']} for row in statements}
    expected = {ids[k]: set(v) for k, v in case['expected']['record_facts'].items()}
    checks = {'succeeded': task['status'] == 'succeeded', 'exact_requested_fields': actual == expected}
    for row in statements:
        source = next(k for k, ident in ids.items() if ident == row['record_id'])
        for fact in row['facts']:
            key = fact['fact']
            if source == 'wall':
                want = thermal[key]
                checks[source + '.' + key + '.period'] = fact['period'] == 'steady_state' and fact['energy_context'] is None
            else:
                want = 8784 if key == 'compared_hours' else oracle['variants'][source][{'cvrmse_percent': 'cvrmse_pct', 'rmse_kwh': 'rmse_kwh'}[key]]
                context = fact['energy_context']
                checks[source + '.' + key + '.context'] = context['native_year'] == 2020 and context['carrier'] == 'Electricity' and context['data_nature'] == 'synthetic' and context['alignment'] == 'exact_calendar'
            checks[source + '.' + key + '.unit'] = fact['unit'] == units[key]
            if want is None:
                checks[source + '.' + key + '.null_reason'] = fact['value'] is None and fact['source_value'] is None and fact['value_policy'] == 'source_undefined' and bool(fact.get('unavailable_reason'))
            else:
                checks[source + '.' + key + '.value'] = fact['value'] is not None and math.isclose(float(fact['value']), float(want), rel_tol=1e-10, abs_tol=1e-10)
    forbidden = case['expected'].get('forbidden_read_record')
    if forbidden:
        checks['excluded_record_not_read'] = not any(forbidden in json.dumps(e.get('arguments', {})) for e in task['events'] if e['tool'].endswith('_read') or e['tool'] == 'professional_read_many')
    rows.append({'id': case['id'], 'passed': all(checks.values()), 'checks': checks, 'status': task['status'], 'error': task.get('error'), 'events': len(task['events'])})
for name, digest in receipt['product_sha256'].items():
    assert hashlib.sha256((base / 'source-snapshot' / name).read_bytes()).hexdigest() == digest, name
assessment = {'passed': sum(row['passed'] for row in rows), 'total': len(rows), 'cases': rows, 'score_delta': 0, 'source_files_verified': len(receipt['product_sha256']), 'scope': 'Four fresh synthetic-reference questions using the unchanged fixed local model. Not a general intelligence, engineering compliance or real-building acceptance claim. Previous failed screens retained.'}
(base / 'assessment.json').write_text(json.dumps(assessment, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(assessment, ensure_ascii=False))
