"""Portable independent steady-state load suite; new native runs only.

Usage: python scripts/verify_design_load_analytic.py NEW_OUTPUT_DIRECTORY
Uses a self-authored box, not a developer-provided building answer or learned output.
"""
import copy
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend import core
from backend.design_loads import inspect_design_loads
from backend.execution import Policy, supervise
from backend.private_storage import private_mkdir


def main():
    out = Path(sys.argv[1]).resolve()
    if out.exists():
        raise RuntimeError('Use a new output directory')
    private_mkdir(out)
    fixture = json.loads((ROOT / 'fixtures/test/native_zone_sizing_projection.json').read_text())
    objects = [[f.strip() for f in o.split(',')] for o in re.sub(r'!.*', '', fixture['model_idf']).split(';') if o.strip()]
    specs = [{'id': 'baseline'}, {'id': 'insulated', 'R': 4}, {'id': 'temperature', 'winter': -20, 'summer': 40},
             {'id': 'thermal_mass', 'mass': True}, {'id': 'zone_multiplier', 'multiplier': 3},
             {'id': 'user_sizing', 'heating_factor': 1.25, 'cooling_factor': 1.15},
             {'id': 'zone_group', 'multiplier': 3, 'list_multiplier': 2}]
    for spec in specs:
        for key, default in dict(R=2, winter=-10, summer=35, multiplier=1, list_multiplier=1,
                                 heating_factor=1, cooling_factor=1).items():
            spec.setdefault(key, default)
        # Independent geometry and thermal circuit: all six faces = 4*5*3+2*5*5 = 110 m2.
        # Interior/exterior prescribed films 10 and 25 W/(m2 K), no solar/gains/air exchange.
        spec['expected_W'] = {mode: 110 * delta / (.1 + spec['R'] + .04) * spec['multiplier'] * spec['list_multiplier']
                             for mode, delta in [('Heating', 20 - spec['winter']), ('Cooling', spec['summer'] - 25)]}
        spec['tolerance'] = 'max(1 W, expected*0.005), declared before execution'
    core.write_json(out / 'predeclared.json', specs)
    records = []
    for spec in specs:
        folder = out / spec['id']
        for p in (folder, folder / 'output', folder / 'logs'):
            private_mkdir(p)
        data = copy.deepcopy(objects)
        for obj in data:
            if obj[0] == 'Material:NoMass':
                if spec.get('mass'):
                    obj[:] = ['Material', 'R2', 'Smooth', '.2', str(.2 / spec['R']), '1000', '1000', '.9', '.7', '.7']
                else:
                    obj[3] = str(spec['R'])
            if obj[0] == 'SizingPeriod:DesignDay':
                winter = obj[1] == 'Synthetic winter'
                obj[5] = str(spec['winter'] if winter else spec['summer'])
                if winter:
                    obj[10] = str(spec['winter'])
            if obj[0] == 'Zone':
                obj[7] = str(spec['multiplier'])
            if obj[0] == 'Sizing:Zone':
                obj[11], obj[12] = str(spec['heating_factor']), str(spec['cooling_factor'])
        if spec['list_multiplier'] != 1:
            data += [['ZoneList', 'Copies', 'Box'], ['ZoneGroup', 'Repeated group', 'Copies', str(spec['list_multiplier'])]]
        model = folder / 'input.idf'
        model.write_text('\n'.join(','.join(obj) + ';' for obj in data), encoding='ascii')
        record = {'spec': spec, 'model_sha256': core.sha(model), 'status': 'not_started'}
        try:
            record['execution'] = supervise([core.engine_path(), '-d', folder / 'output', model],
                                             folder, folder / 'logs', Policy(), 60, output=folder / 'output')
            errors = (folder / 'output/eplusout.err').read_text(errors='replace')
            if re.search(r'\*\*\s*(Severe|Fatal)\s*\*\*', errors, re.I):
                raise AssertionError('Severe/Fatal native diagnostics')
            record['warning_count'] = len(re.findall(r'\*\*\s*Warning\s*\*\*', errors, re.I))
            receipt = inspect_design_loads(folder / 'output/eplusout.sql', model)
            record['receipt'] = receipt
            assert receipt['status'] == 'calculated_model_scenario', receipt.get('reason')
            checks = []
            for row in receipt['rows']:
                expected = spec['expected_W'][row['load_type']]
                factor = spec['heating_factor'] if row['load_type'] == 'Heating' else spec['cooling_factor']
                for column, multiplier in [('calculated_sensible_load_W', 1), ('user_adjusted_sensible_load_W', factor)]:
                    target = expected * multiplier
                    error = abs(row[column] - target)
                    checks.append({'mode': row['load_type'], 'column': column, 'expected_W': target,
                                   'actual_W': row[column], 'absolute_error_W': error, 'pass': error <= max(1, target * .005)})
                assert row['zone_multiplier'] == spec['multiplier'] and row['zone_list_multiplier'] == spec['list_multiplier']
            record['checks'] = checks
            assert len(checks) == 4 and all(c['pass'] for c in checks), 'Independent heat balance mismatch'
            record['status'] = 'passed'
        except Exception as exc:
            record.update(status='failed', error=type(exc).__name__ + ': ' + str(exc))
        core.write_json(folder / 'record.json', record)
        records.append(record)
        print(json.dumps({'case': spec['id'], 'status': record['status'], 'error': record.get('error')}), flush=True)
    core.write_json(out / 'summary.json', {'records': records, 'new_energyplus_simulations': len(records),
        'scope': 'Steady synthetic sensible heat balance; no dynamic climate, solar, humidity or real-building calibration',
        'parser_sha256': core.sha(ROOT / 'backend/design_loads.py')})
    assert all(r['status'] == 'passed' for r in records)


if __name__ == '__main__':
    main()
