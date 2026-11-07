"""Replay frozen free-floating inputs against independent nonlinear energy balance.

No HVAC, no solar/ventilation/latent coupling; not a real-building calibration.
The input directory contains predeclared.json and <case>/input.idf. Never write
there. Temperature tolerance remains 0.02 K, including coarse-step failures.
"""
import argparse
import json
import math
import re
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend import core
from backend.execution import Policy, supervise
from backend.hourly_thermal import inspect_hourly_thermal
from backend.private_storage import private_mkdir

# An absolute property-input rounding allowance, NOT a temperature tolerance.
# |d ln C / dw| < 4 for w near 1e-5, so this changes C by < 4e-16.
HUMIDITY_ROUNDING = 1e-16


def independent_hourly(spec, humidity=1e-5):
    ua = spec['area_m2'] / (1 / spec['inside_h'] + spec['wall_R'] + 1 / spec['outside_h'])
    capacity = (spec['volume_m3'] * spec['cap'] * spec['pressure_Pa'] *
                (spec['cp_dry_J_kgK'] + spec['cp_vapour_J_kgK'] * humidity) /
                (spec['gas_constant'] * (1 + 1.6077687 * humidity)))
    dt = 3600 / spec['steps']
    temperature = spec['mean_C']
    for _ in range(200):
        start, values = temperature, []
        for index, external in enumerate(spec['boundary_C']):
            gain = 1000 if spec['gains'] and index >= 12 * spec['steps'] else 0
            equilibrium = external + gain / ua + 273.15
            temperature = equilibrium / (1 + (equilibrium / (temperature + 273.15) - 1) *
                math.exp(-ua / capacity * equilibrium * dt)) - 273.15
            values.append(temperature)
        if abs(start - temperature) < 1e-12:
            return [math.fsum(values[i:i + spec['steps']]) / spec['steps']
                    for i in range(0, len(values), spec['steps'])]
    raise ValueError('Independent periodic solution did not converge')


def run(inputs, output):
    if output.exists():
        raise ValueError('Output must be a NEW directory; retain previous results')
    specs = json.loads((inputs / 'predeclared.json').read_text())['specs']
    private_mkdir(output)
    shutil.copyfile(inputs / 'predeclared.json', output / 'predeclared.json')
    receipt = {'script_sha256': core.sha(Path(__file__)),
               'gold_sha256': core.sha(output / 'predeclared.json'),
               'humidity_rounding_kg_kg': HUMIDITY_ROUNDING, 'cases': []}
    # Validate and freeze every model/answer before executing any native case.
    for spec in specs:
        if not re.fullmatch('[a-z0-9_]+', spec['name']) or spec['tolerance_K'] != .02:
            raise ValueError('Unexpected case identity or temperature tolerance')
        work = private_mkdir(output / spec['name'])
        shutil.copyfile(inputs / spec['name'] / 'input.idf', work / 'input.idf')
        if core.sha(work / 'input.idf') != spec['model_sha256']:
            raise ValueError('Frozen model hash mismatch')
        recalculated = independent_hourly(spec)
        if max(abs(a - b) for a, b in zip(recalculated, spec['gold_hourly_temperature_C'])) > 1e-10:
            raise ValueError('Frozen independent answer mismatch')
    core.write_json(output / 'policy.json', {**receipt, 'cases': [s['name'] for s in specs],
        'scope': 'New native runs, frozen v2 inputs/gold; humidity rounding premise corrected explicitly. No change to 0.02 K temperature criterion.'})
    for spec in specs:
        work = output / spec['name']
        row = {'name': spec['name'], 'model_sha256': core.sha(work / 'input.idf'),
               'status': 'not_run', 'tolerance_K': spec['tolerance_K']}
        try:
            native = private_mkdir(work / 'output')
            row['execution'] = supervise([core.engine_path(), '-d', native, work / 'input.idf'],
                work, private_mkdir(work / 'logs'), Policy(), 120, output=native)
            err = (native / 'eplusout.err').read_text(errors='replace')
            if re.search(r'\*\*\s*(Severe|Fatal)\s*\*\*', err, re.I):
                raise ValueError('Native severe/fatal')
            parsed = inspect_hourly_thermal(native / 'eplusout.sql', work / 'input.idf', environment_index=1)
            core.write_json(work / 'hourly.json', parsed)
            if parsed['status'] != 'calculated_model_scenario':
                raise ValueError(parsed.get('reason'))
            series = parsed['summary']['peak_day_profiles'][0]['zones']['BOX_1']
            with sqlite3.connect((native / 'eplusout.sql').resolve().as_uri() + '?mode=ro', uri=True) as con:
                humidity = [r[0] for r in con.execute('SELECT r.Value FROM ReportData r '
                    'JOIN ReportDataDictionary d USING(ReportDataDictionaryIndex) JOIN Time t USING(TimeIndex) '
                    'WHERE d.Name=? AND d.ReportingFrequency=? AND COALESCE(t.WarmupFlag,0)=0 ORDER BY t.TimeIndex',
                    ('Zone Air Humidity Ratio', 'Hourly'))]
            if len(humidity) != 24 or not all(math.isfinite(w) and w >= 0 for w in humidity):
                raise ValueError('Incomplete or invalid native humidity')
            row['maximum_temperature_error_K'] = max(abs(a - b) for a, b in
                zip(series['temperature_C'], spec['gold_hourly_temperature_C']))
            row['humidity_max'] = max(humidity)
            row['dry_property_floor_verified_with_rounding'] = max(humidity) <= 1e-5 + HUMIDITY_ROUNDING
            row['humidity_rounding_temperature_sensitivity_K'] = max(abs(a - b) for a, b in zip(
                independent_hourly(spec, 1e-5 + HUMIDITY_ROUNDING), spec['gold_hourly_temperature_C']))
            row['HVAC_absolute_max_W'] = max(abs(v) for k in ('heating_W', 'cooling_W') for v in series[k])
            row['status'] = 'passed' if (row['maximum_temperature_error_K'] <= .02 and
                row['dry_property_floor_verified_with_rounding'] and row['HVAC_absolute_max_W'] < 1e-6 and
                row['humidity_rounding_temperature_sensitivity_K'] < 1e-10) else 'numerical_or_premise_mismatch'
            row['sql_sha256'] = core.sha(native / 'eplusout.sql')
            row['native_hourly'] = series
        except Exception as exc:
            row.update(status='failed', error=type(exc).__name__ + ': ' + str(exc))
        receipt['cases'].append(row)
        core.write_json(work / 'receipt.json', row)
        print(json.dumps({k: v for k, v in row.items() if k not in
            ('execution', 'native_hourly', 'model_sha256', 'sql_sha256')}), flush=True)
    receipt['all_cases_passed'] = all(r['status'] == 'passed' for r in receipt['cases'])
    core.write_json(output / 'receipt.json', receipt)
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--inputs', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    run(args.inputs.resolve(), args.output.resolve())
