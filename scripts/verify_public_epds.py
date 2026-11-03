"""Real declaration inputs with independently computed reference-quantity oracles.

Twenty declaration datasets are NOT twenty engineering projects. Quantities and
project review records are explicit test scenarios; no field approval is claimed.
"""
import argparse
import csv
import json
import os
import sys
import time
from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--csv', type=Path, required=True)
    p.add_argument('--sha256', required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    out = a.out.resolve()
    if out.exists() or out.is_relative_to(ROOT):
        p.error('Use a new output directory outside the checkout')
    out.mkdir(parents=True)
    os.environ['VRA_DATA_DIR'] = str(out/'bootstrap')
    os.environ['VRA_REGISTRATION_MODE'] = 'open'
    from backend import core
    from backend.api import create_app
    from fastapi.testclient import TestClient
    if core.sha(a.csv) != a.sha256:
        raise ValueError('Official original SHA256 mismatch')
    # This raw CSV reader and Decimal oracle deliberately do not call the product parser.
    with a.csv.open(encoding='cp1252', newline='') as f:
        raw = list(csv.DictReader(f, delimiter=';'))
    candidates = [r for r in raw if r['Typ'] == 'specific dataset' and r['Modul'] == 'A1-A3'
                  and not r['Szenario'].strip() and r['GWPtotal (A2)'].strip() and r['Bezugsgroesse'].strip()
                  and r['Bezugseinheit'] in {'kg', 'qm', 'm3', 'pcs.'}
                  and r['Gueltig bis'].isdigit() and int(r['Gueltig bis']) > date.today().year]
    by_category = defaultdict(list)
    for r in sorted(candidates, key=lambda r: (r['Name (en)'], r['UUID'], r['Version'])):
        by_category[r['Kategorie (en)']].append(r)
    selected, used = [], set()
    for depth in range(20):
        for category in sorted(by_category):
            rows = by_category[category]
            if depth < len(rows):
                r = rows[depth]
                key = (r['UUID'], r['Version'])
                if key not in used:
                    selected.append(r)
                    used.add(key)
                if len(selected) == 20:
                    break
        if len(selected) == 20:
            break
    assert len(selected) == 20
    core.write_json(out/'frozen-selection.json', {'source_sha256': a.sha256, 'selection': selected,
                    'quantity_basis': 'Authored 13.75 declared units; not a source engineering BoQ'})
    app = create_app(out/'runtime', start_worker=False)
    lib = app.state.domain.sustainability.epds
    release = lib.import_csv(a.csv)
    report = {'source': release, 'scope': __doc__, 'cases': [], 'formal_data_changed': False,
              'independently_engineer_approved': 0, 'field_projects_tested': 0, 'training_started': False}
    with TestClient(app) as c:
        auth = c.post('/api/auth/register', json={'username': 'epd_public_acceptance',
            'display_name': 'Isolated declaration checks', 'password': 'Isolated-EPD-review-2026-only'}).json()
        c.headers['X-CSRF-Token'] = auth['csrf_token']
        pid = c.post('/api/projects', json={'name': 'Public declarations / authored quantity scenario',
            'data_nature': 'engineering_reference', 'building': {'use': 'Software reference only',
            'location': 'Not a source building', 'region': 'DE', 'area_m2': 1.}}).json()['project_id']
        base = f'/api/projects/{pid}/sustainability/epds'
        for raw_row in selected:
            ref = {'release_sha256': release['sha256'], 'uuid': raw_row['UUID'], 'version': raw_row['Version']}
            unit = {'qm': 'm2', 'kg': 'kg', 'm3': 'm3', 'pcs.': 'item'}[raw_row['Bezugseinheit']]
            payload = {**ref, 'quantity': 13.75, 'unit': unit, 'boundary': 'A1-A3'}
            row = {'uuid': raw_row['UUID'], 'version': raw_row['Version'], 'name': raw_row['Name (en)'],
                   'category': raw_row['Kategorie (en)'], 'checks': {}, 'passed': False}
            report['cases'].append(row)
            try:
                found = c.get(base, params={'query': raw_row['UUID']}).json()
                row['checks']['search_original_uuid'] = found['total'] == 1
                response = c.post(base+'/calculate', json=payload)
                row['checks']['api_200'] = response.status_code == 200
                result = response.json()
                oracle_factor = Decimal(raw_row['GWPtotal (A2)'])/Decimal(raw_row['Bezugsgroesse'])
                row['oracle_gwp_per_unit'] = str(oracle_factor)
                row['actual_gwp_per_unit'] = result['gwp_per_unit']
                row['checks']['independent_decimal_factor'] = abs(Decimal(str(result['gwp_per_unit']))-oracle_factor) <= max(Decimal('1e-9'), abs(oracle_factor)*Decimal('1e-12'))
                oracle_amount = oracle_factor*Decimal('13.75')
                row['checks']['independent_quantity_total'] = abs(Decimal(str(result['material_kgco2e']))-oracle_amount) <= max(Decimal('1e-8'), abs(oracle_amount)*Decimal('1e-12'))
                line = result['source_rows'][0]['csv_line']
                row['checks']['original_csv_row_identity'] = raw[line-2] == result['source_rows'][0]['values']
                row['checks']['no_module_d_credit'] = all(r['values']['Modul'] == 'A1-A3' for r in result['source_rows']) and result['issued_credits_t'] is None
                row['checks']['applicability_not_auto_approved'] = result['project_applicability'] == 'NOT_REVIEWED'
                bad = c.post(base+'/calculate', json={**payload, 'unit': 'kg' if unit != 'kg' else 'm2'}).json()
                row['checks']['wrong_unit_not_zero'] = bad['material_kgco2e'] is None and bool(bad['gaps'])
                row['checks']['release_hash_bound'] = result['release']['sha256'] == a.sha256
                row['checks']['source_type_and_region_preserved'] = result['dataset']['dataset_type'] == raw_row['Typ'] and result['dataset']['region'] == raw_row['Laenderkennung']
                row['passed'] = all(row['checks'].values())
            except Exception as exc:
                row['error'] = str(exc)[:500]
            core.write_json(out/'results.json', report)
        started = time.perf_counter()
        statuses = []
        for i in range(1000):
            statuses.append(c.get(base, params={'query': selected[i%20]['UUID']}).status_code)
        report['repeated_read_test'] = {'requests': len(statuses), 'non_200': sum(s != 200 for s in statuses),
                                      'seconds': time.perf_counter()-started,
                                      'scope': 'Sequential isolated TestClient reads; not production concurrency or real button clicks'}
    report['passed_cases'] = sum(r['passed'] for r in report['cases'])
    report['checks_passed'] = sum(sum(r['checks'].values()) for r in report['cases'])
    report['checks_total'] = 200
    core.write_json(out/'results.json', report)
    print(json.dumps({k: report[k] for k in ['passed_cases', 'checks_passed', 'checks_total', 'repeated_read_test']}, ensure_ascii=True))
    if report['passed_cases'] != 20 or report['repeated_read_test']['non_200']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
