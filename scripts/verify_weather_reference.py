"""New real runs for weather policy. Never edits a reference run or source EPW.

Usage: python scripts/verify_weather_reference.py NEW_DIRECTORY WEATHER_DIRECTORY
Requires ENERGYPLUS_EXE and a directory of the five bundled 9.0.1 US EPW files.
"""
import copy
import csv
import json
import math
import os
import secrets
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend import core
from backend.input_validation import validate_epw
from backend.private_storage import private_mkdir


def execute(case, folder):
    run = core.run_simulation(case['case_id'], 'baseline', 'none', folder,
                              case_override=case, file_root=core.ROOT)
    core.write_json(folder.parent / (folder.name + '-outcome.json'), run)
    assert run['status'] == 'succeeded', run.get('error')
    checked, manifest, _ = core.read_validated(folder, check_current=False)
    quality = core.read_json(folder / 'weather-quality.json')
    assert quality == validate_epw(folder / 'input/weather.epw')
    assert manifest['engine_calls_executed'] == 1 and checked['metrics']['annual_days'] == 365
    assert core.sha(folder / 'input/weather.epw') == quality['source_sha256']
    return {'run_dir': str(folder), 'manifest_sha256': core.sha(folder / 'manifest.json'),
            'weather_quality': quality, 'metrics': checked['metrics'], 'warnings': manifest['warnings'],
            'elapsed_seconds': manifest['elapsed_seconds'], 'code_hash': manifest['fingerprints']['code']}


def main():
    out = Path(sys.argv[1]).resolve()
    if out.exists():
        raise RuntimeError('Choose a new evidence directory')
    private_mkdir(out)
    inputs = core.ROOT / 'validation' / ('weather-inputs-' + out.name)
    inputs.mkdir(parents=True, exist_ok=False)
    public = Path(sys.argv[2]).resolve()
    files = sorted(public.glob('USA_*_TMY3.epw'))
    assert len(files) == 5, 'Expected five fixed EnergyPlus bundled public US climates'
    records = []
    for index, source in enumerate(files):
        digest = core.sha(source)
        target = inputs / source.name
        target.write_bytes(source.read_bytes())
        case = copy.deepcopy(core.load_case('reference_5zone'))
        case['weather'] = target.relative_to(core.ROOT).as_posix()
        case['name'] = 'Fixed model weather sensitivity: ' + source.stem
        case['notes'] += ['Weather-only sensitivity: geometry, design days, sizing inputs, schedules and ground assumptions unchanged; not local compliant design.']
        result = execute(case, out / ('public-' + str(index)))
        assert core.sha(source) == digest == core.sha(target)
        result.update(source=str(source), source_sha256=digest, scope='fixed-model weather-only scenario, not local design load')
        records.append(result)
        core.write_json(out / 'public-progress.json', records)
        print(json.dumps({'station': source.stem, 'annual_energy_kwh': result['metrics']['annual_energy_kwh'],
                          'conditions': len(result['weather_quality']['conditions'])}), flush=True)
    sky = []
    for cover in (0, 10):
        with (core.ROOT / 'fixtures/demo/reference_5zone/weather.epw').open(encoding='utf-8-sig', newline='') as stream:
            data = list(csv.reader(stream))
        for row in data[8:]:
            for index, value in {6:20, 7:10, 8:52.5, 9:80600, 12:9999, 13:0, 14:0, 15:0, 20:0, 21:0,
                                 22:cover, 23:cover, 26:9, 27:999999999, 30:0, 32:.2, 33:0, 34:1}.items():
                row[index] = str(value)
        weather = inputs / ('synthetic-constant-sky-' + str(cover) + '.epw')
        with weather.open('x', encoding='utf-8', newline='') as stream:
            csv.writer(stream).writerows(data)
        model = inputs / ('sky-' + str(cover) + '.idf')
        model.write_text((core.ROOT / 'fixtures/demo/reference_5zone/baseline.idf').read_text() +
                         '\nOutput:Variable,Environment,Site Sky Temperature,Hourly;\n', encoding='utf-8')
        case = copy.deepcopy(core.load_case('reference_5zone'))
        case['weather'] = weather.relative_to(core.ROOT).as_posix()
        case['schemes'][0]['model'] = model.relative_to(core.ROOT).as_posix()
        case['notes'] += ['Synthetic constant weather for independent sky-temperature formula check; not an observed climate.']
        result = execute(case, out / ('synthetic-sky-' + str(cover)))
        # Independent closed-form calculation, not a call to the product parser.
        emissivity = (.787 + .764 * math.log((273.15 + 10) / 273.15)) * (1 + .0224 * cover - .0035 * cover**2 + .00028 * cover**3)
        expected = (273.15 + 20) * emissivity**.25 - 273.15
        with sqlite3.connect(Path(result['run_dir']) / 'output/eplusout.sql') as con:
            rows = con.execute('''SELECT r.Value FROM ReportData r JOIN ReportDataDictionary d
                ON d.ReportDataDictionaryIndex=r.ReportDataDictionaryIndex JOIN Time t ON t.TimeIndex=r.TimeIndex
                JOIN EnvironmentPeriods e ON e.EnvironmentPeriodIndex=t.EnvironmentPeriodIndex
                WHERE d.Name='Site Sky Temperature' AND d.ReportingFrequency='Hourly' AND d.Units='C'
                AND e.EnvironmentType=3 AND COALESCE(t.WarmupFlag,0)=0''').fetchall()
        assert len(rows) == 8760, len(rows)
        errors = [abs(row[0] - expected) for row in rows]
        result.update(cloud_cover_tenths=cover, independent_expected_C=expected, hourly_values=len(rows),
                      actual_range_C=[min(r[0] for r in rows), max(r[0] for r in rows)],
                      max_absolute_error_C=max(errors), tolerance_C=1e-6)
        sky.append(result)
        core.write_json(out / 'sky-progress.json', sky)
        assert max(errors) <= 1e-6, result
        print(json.dumps({'synthetic_sky_cover': cover, 'max_absolute_error_C': max(errors)}), flush=True)
    # Authenticated real run: same quality object in gate, archived native run and all report formats.
    os.environ['VRA_DATA_DIR'] = str(out / 'bootstrap')
    from backend.api import create_app
    from fastapi.testclient import TestClient
    with TestClient(create_app(out / 'api', start_worker=False)) as client:
        login = client.post('/api/auth/register', json={'username':'weather_receipt_test', 'display_name':'Isolated weather test',
                                                       'password':secrets.token_urlsafe(32)})
        assert login.status_code == 200
        client.headers['X-CSRF-Token'] = login.json()['csrf_token']
        project = client.post('/api/reference-projects').json()
        pid = project['project_id']; base = '/api/projects/' + pid
        for evidence in client.get(base + '/evidence').json():
            response = client.patch(base + '/evidence/' + evidence['evidence_id'], json={
                'expected_revision':evidence['revision'], 'review_state':'confirmed', 'responsible_person':'Isolated verifier',
                'review_note':'Public reference scope reviewed for regression, not a measured building'})
            assert response.status_code == 200
        gate = client.get(base + '/gate').json()
        run = client.post('/api/runs', json={'project_id':pid, 'scheme_id':'baseline'})
        assert run.status_code == 202, run.text
        rid = run.json()['run_id']; domain = client.app.state.domain
        claimed = domain.store.claim_job()
        assert claimed['run_id'] == rid
        domain.execute(claimed)
        report = client.get('/api/runs/' + rid + '/report.json').json()
        assert report['run']['status'] == 'succeeded', report['run']
        assert report['run']['weather_quality'] == gate['weather_quality']
        for fmt in ('json', 'html', 'pdf'):
            response = client.get('/api/runs/' + rid + '/report.' + fmt)
            assert response.status_code == 200
            (out / ('authenticated-report.' + fmt)).write_bytes(response.content)
        rd = out / 'api/runs' / rid
        assert core.read_json(rd / 'weather-quality.json') == gate['weather_quality']
        # Corruption only in this private test run; keep failure visible and do not repair it.
        clean_manifest_hash = core.sha(rd / 'manifest.json')
        with (rd / 'weather-quality.json').open('ab') as stream:
            stream.write(b'\n ')
        rejected = client.get('/api/runs/' + rid).json()
        assert rejected['status'] == 'failed' and rejected['metrics'] is None and rejected['weather_quality'] is None
        core.write_json(out / 'authenticated-tamper-rejected.json', rejected)
    summary = {'scope':'Real EnergyPlus 9.0.1 public weather scenarios plus synthetic formula checks; no building certification.',
               'public_climates': records, 'synthetic_sky_checks': sky, 'authenticated_run_id':rid,
               'authenticated_clean_manifest_sha256':clean_manifest_hash, 'receipt_tamper_rejected':True,
               'new_energyplus_simulations':8, 'completed_at':core.now()}
    core.write_json(out / 'weather-reference.json', summary)
    print(json.dumps({'complete':True, 'new_simulations':8, 'output':str(out)}))


if __name__ == '__main__':
    main()
