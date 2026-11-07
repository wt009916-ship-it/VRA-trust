"""Fresh native probes against a predeclared harmonic-conduction solution.

Synthetic prescribed-film boxes, not a real building or an ASHRAE certification.
Run with --output pointing at a NEW directory outside the repository on Windows.
Coarse-step mismatch cases remain failures; they are not silently reclassified.
"""
import argparse
import cmath
import copy
import json
import math
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend import core
from backend.execution import Policy, supervise
from backend.hourly_thermal import inspect_hourly_thermal
from backend.private_storage import private_mkdir


def cases():
    rows = [dict(name='massless', density=None, steps=6),
            dict(name='massive_10min', density=1000, steps=6),
            dict(name='massive_5min', density=1000, steps=12),
            dict(name='massive_2min', density=1000, steps=30),
            dict(name='massive_1min', density=1000, steps=60),
            dict(name='light_mass', density=500, steps=60),
            dict(name='heavy_mass', density=2000, steps=60),
            dict(name='internal_step', density=None, steps=6, gains=True),
            dict(name='coincident', density=None, steps=6, phases=[1, 1]),
            dict(name='staggered', density=None, steps=6, phases=[1, -1]),
            dict(name='multiplied', density=None, steps=6, phases=[1, -1], multiplier=3, list_multiplier=2)]
    for row in rows:
        row.setdefault('phases', [1])
        row.setdefault('multiplier', 1)
        row.setdefault('list_multiplier', 1)
        row.setdefault('gains', False)
        if row['density']:
            gamma = cmath.sqrt(1j * 2 * math.pi * row['density'] * 1000 / (86400 * .5))
            a = cmath.cosh(gamma * .2)
            b = cmath.sinh(gamma * .2) / (.5 * gamma)
            c = .5 * gamma * cmath.sinh(gamma * .2)
            transfer = b + .14 * a + .004 * c
        else:
            transfer = complex(.54)
        amplitude = 5 / transfer
        row['analytical_amplitude_W'] = 110 * abs(amplitude)
        row['analytical_phase_rad'] = cmath.phase(amplitude)
        row['tolerance_unmultiplied_W'] = max(1., row['analytical_amplitude_W'] * .02)
        row['gold_unmultiplied_heating_W'] = {}
        for zone, phase in enumerate(row['phases'], 1):
            row['gold_unmultiplied_heating_W']['BOX_' + str(zone)] = [
                sum(110 * (20 / .54 - (phase * amplitude * cmath.exp(1j * 2 * math.pi *
                    (hour - 1 + (k + 1) / row['steps']) / 24)).imag)
                    for k in range(row['steps'])) / row['steps'] - (1000 if row['gains'] and hour > 12 else 0)
                for hour in range(1, 25)]
    return rows


def model(base, spec):
    global_kinds = {'version', 'timestep', 'building', 'heatbalancealgorithm', 'simulationcontrol',
                    'site:location', 'sizingperiod:designday', 'globalgeometryrules', 'material:nomass',
                    'construction', 'scheduletypelimits', 'schedule:constant', 'sizing:parameters',
                    'designspecification:outdoorair', 'thermostatsetpoint:dualsetpoint',
                    'output:sqlite', 'output:table:summaryreports', 'output:variable'}
    objects = [[v.strip() for v in p.split(',')] for p in re.sub(r'!.*', '', base).split(';') if p.strip()]
    globals_ = [copy.deepcopy(o) for o in objects if o[0].lower() in global_kinds
                and not (o[0] == 'SizingPeriod:DesignDay' and o[1] == 'Synthetic summer')]
    local = [o for o in objects if o[0].lower() not in global_kinds]
    for obj in globals_:
        if obj[0] == 'Timestep':
            obj[1] = str(spec['steps'])
        if obj[0] == 'Material:NoMass':
            if spec['density']:
                obj[:] = ['Material', 'R2', 'Smooth', '.2', '.5', str(spec['density']), '1000', '.9', '.7', '.7']
            else:
                obj[3] = '.4'
    data = globals_
    for zone, phase in enumerate(spec['phases'], 1):
        suffix = '_' + str(zone)
        # Explicit per-zone identities; global schedules and constructions stay shared.
        named = {'Box', 'Ambient', 'South', 'East', 'North', 'West', 'Roof', 'Floor',
                 'Equipment', 'Supply', 'Zone air', 'Return', 'Ideal'}
        for original in local:
            obj = [v + suffix if v in named else v for v in original]
            if obj[0] == 'ZoneControl:Thermostat':
                obj[1] += suffix
            if obj[0] == 'Zone':
                obj[7] = str(spec['multiplier'])
            if obj[0] == 'BuildingSurface:Detailed':
                obj[2] = original[2]  # Surface type is an enum, not a named reference.
                # World coordinates: keep rooms separated even though solar is disabled.
                for i in range(11, len(obj), 3):
                    obj[i] = str(float(obj[i]) + 10 * (zone - 1))
            if obj[0] == 'SurfaceProperty:OtherSideCoefficients':
                obj[:] = [obj[0], obj[1], '25', '0', '1', '0', '0', '0', '0', 'Boundary' + suffix, 'No', '24', '0']
            data.append(obj)
        schedule = ['Schedule:Compact', 'Boundary' + suffix, 'Any', 'Through:12/31', 'For:AllDays', 'Interpolate:No']
        for step in range(1, 24 * spec['steps'] + 1):
            minute = step * 60 // spec['steps']
            schedule.extend([f'Until:{minute // 60:02d}:{minute % 60:02d}',
                             format(phase * 5 * math.sin(2 * math.pi * step / (24 * spec['steps'])), '.15g')])
        data.append(schedule)
        if spec['list_multiplier'] != 1:
            data.extend([['ZoneList', 'List' + suffix, 'Box' + suffix],
                         ['ZoneGroup', 'Group' + suffix, 'List' + suffix, str(spec['list_multiplier'])]])
        if spec['gains']:
            data.extend([['Schedule:Compact', 'Gains' + suffix, 'Any', 'Through:12/31', 'For:AllDays',
                          'Until:12:00', '0', 'Until:24:00', '1'],
                         ['OtherEquipment', 'Convective' + suffix, 'None', 'Box' + suffix, 'Gains' + suffix,
                          'EquipmentLevel', '1000', '', '', '0', '0', '0']])
    for variable in ['Zone Air Temperature', 'Zone Air System Sensible Heating Rate', 'Zone Air System Sensible Cooling Rate',
                     'Zone Air System Sensible Heating Energy', 'Zone Air System Sensible Cooling Energy']:
        data.append(['Output:Variable', '*', variable, 'Hourly'])
    return '\n'.join(','.join(obj) + ';' for obj in data)


def run(output):
    if output.exists():
        raise ValueError('Use a new output directory; old evidence must remain untouched')
    private_mkdir(output)
    fixture = ROOT / 'fixtures/test/native_zone_sizing_projection.json'
    base = json.loads(fixture.read_text())['model_idf']
    specs = cases()
    # Freeze ALL input models, independent answers, and tolerances before any engine call.
    core.write_json(output / 'predeclared.json', {'scope': 'Controlled harmonic 1D wall and prescribed films; clamped indoor 20 C; no solar/ventilation/latent load. Endpoint-sampled continuous analytical answer. Coarse-step disagreement remains a failure.', 'cases': specs})
    for spec in specs:
        private_mkdir(output / spec['name'])
        (output / spec['name'] / 'input.idf').write_text(model(base, spec), encoding='ascii')
    receipt = {'script_sha256': core.sha(Path(__file__)), 'gold_sha256': core.sha(output / 'predeclared.json'),
               'base_fixture_sha256': core.sha(fixture), 'cases': []}
    core.write_json(output / 'inputs.json', {**receipt, 'model_hashes': {s['name']: core.sha(output / s['name'] / 'input.idf') for s in specs}})
    for spec in specs:
        work = output / spec['name']
        row = {'case': spec['name'], 'status': 'not_run', 'model_sha256': core.sha(work / 'input.idf')}
        try:
            native = private_mkdir(work / 'output')
            row['execution'] = supervise([core.engine_path(), '-d', native, work / 'input.idf'], work,
                                         private_mkdir(work / 'logs'), Policy(), 90, output=native)
            err = (native / 'eplusout.err').read_text(errors='replace')
            assert not re.search(r'\*\*\s*(Severe|Fatal)\s*\*\*', err, re.I), 'Native severe/fatal'
            parsed = inspect_hourly_thermal(native / 'eplusout.sql', work / 'input.idf', environment_index=1)
            core.write_json(work / 'hourly.json', parsed)
            assert parsed['status'] == 'calculated_model_scenario', parsed.get('reason')
            profile = parsed['summary']['peak_day_profiles'][0]
            scale = spec['multiplier'] * spec['list_multiplier']
            row['maximum_unmultiplied_error_W'] = max(abs(value / scale - gold) for zone, values in profile['zones'].items()
                for value, gold in zip(values['heating_W'], spec['gold_unmultiplied_heating_W'][zone]))
            row['temperature_max_error_K'] = max(abs(v - 20) for values in profile['zones'].values() for v in values['temperature_C'])
            row['tolerance_unmultiplied_W'] = spec['tolerance_unmultiplied_W']
            row['building_peak_W'] = parsed['summary']['building']['heating_peak']['value_W']
            row['sum_zone_peaks_W'] = sum(z['heating_peak']['value_W'] for z in parsed['summary']['zones'])
            row['native_sql_sha256'] = core.sha(native / 'eplusout.sql')
            row['status'] = 'passed' if row['maximum_unmultiplied_error_W'] <= spec['tolerance_unmultiplied_W'] and row['temperature_max_error_K'] < .01 else 'numerical_mismatch'
        except Exception as exc:
            row.update(status='failed', error=type(exc).__name__ + ': ' + str(exc))
        receipt['cases'].append(row)
        core.write_json(work / 'record.json', row)
        print(json.dumps({k: v for k, v in row.items() if k not in ('execution', 'model_sha256', 'native_sql_sha256')}), flush=True)
    core.write_json(output / 'receipt.json', receipt)
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    run(parser.parse_args().output.resolve())
