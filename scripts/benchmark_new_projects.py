"""Frozen, previously unseen public IFCs through production APIs; keep all failures.

Inputs and full traces remain outside Git. No input edits, space deletion, geometry
tolerance tuning or repeated floors counted as independent buildings. Annual
outputs describe explicit hypothetical software scenarios, never measured energy.
"""
import argparse
import copy
import json
import os
from pathlib import Path
import runpy
import secrets
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    if out.exists() or out.is_relative_to(ROOT):
        parser.error('Use a new directory outside the checkout')
    out.mkdir(parents=True)
    os.environ['VRA_DATA_DIR'] = str(out/'bootstrap')
    from backend import core, model_export
    from backend.api import create_app
    import ifcopenshell
    from fastapi.testclient import TestClient
    helper = runpy.run_path(str(ROOT/'tests/test_model_workbench.py'))
    manifest = json.loads(args.manifest.read_text(encoding='utf-8-sig'))
    result = {'protocol': manifest['protocol'], 'frozen_at_utc': manifest['frozen_at_utc'],
              'code_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'manifest_sha256': core.sha(args.manifest), 'ifcopenshell': ifcopenshell.version,
              'engine': subprocess.check_output([str(core.engine_path()), '--version'], text=True).strip(),
              'compiler_hash': model_export.compiler_hash(),
              'source_sha256': {name: core.sha(ROOT/name) for name in (
                  'backend/model_import.py', 'backend/modeling.py', 'backend/model_export.py',
                  'backend/thermal_mesh.py', 'backend/honeybee_bridge.py')},
              'cases': [], 'scope': 'Public source geometry and hypothetical reference scenarios, not calibrated source-building energy'}
    traces = []
    def persist():
        core.write_json(out/'results.json', result)
        core.write_json(out/'api-trace.private.json', traces)
    def call(label, response):
        try: body = response.json()
        except ValueError: body = {'non_json': response.text[:1000]}
        traces.append({'step': label, 'http': response.status_code, 'body': body})
        persist()
        return response.status_code, body
    def require(label, response, status=200):
        actual, body = call(label, response)
        if actual != status:
            raise ValueError(f'{label}: HTTP {actual}: {str(body)[:1200]}')
        return body
    app = create_app(out/'runtime', start_worker=True)
    with TestClient(app) as c:
        auth = c.post('/api/auth/register', json={'username': 'new_sample_acceptance',
            'password': 'Sample-'+secrets.token_urlsafe(24), 'display_name': 'Isolated new sample acceptance'})
        assert auth.status_code == 200, auth.text
        c.headers['X-CSRF-Token'] = auth.json()['csrf_token']
        for source in manifest['cases']:
            started = time.monotonic()
            row = {k: source[k] for k in ('id', 'repository', 'commit', 'path', 'kind', 'source_url', 'sha256', 'bytes')}
            row['attempts'] = []
            result['cases'].append(row)
            try:
                path = Path(source['local_path'])
                if core.sha(path) != source['sha256']: raise ValueError('Source hash mismatch')
                document = ifcopenshell.open(str(path))
                row['inventory'] = {'schema': document.schema, 'spaces': len(document.by_type('IfcSpace')),
                    'storeys': len(document.by_type('IfcBuildingStorey')), 'walls': len(document.by_type('IfcWall')),
                    'windows': len(document.by_type('IfcWindow')), 'doors': len(document.by_type('IfcDoor')),
                    'project_ids': [x.GlobalId for x in document.by_type('IfcProject')],
                    'building_ids': [x.GlobalId for x in document.by_type('IfcBuilding')]}
                project = require(source['id']+'_create', c.post('/api/projects', json={'name': source['id']+' public source acceptance',
                    'data_nature': 'engineering_reference', 'building': {'use': 'assumed office software scenario',
                    'location': 'Golden reference weather, not source site', 'region': 'US-CO', 'area_m2': 80.}}), 201)
                base = '/api/projects/'+project['project_id']
                upload = require(source['id']+'_upload', c.post(base+'/files', files={'file': (path.name, path.read_bytes())}), 201)
                fid = upload['file_id']
                inventory = require(source['id']+'_storeys', c.get(base+f'/files/{fid}/ifc-storeys'))
                row['storey_inventory'] = inventory
                options = {'file_id': fid}
                options.update(manifest['protocol'].get('import_options', {}))
                if inventory['suggested_origin_m'] is not None:
                    options['ifc_origin_m'] = [float(v) for v in inventory['suggested_origin_m']]
                attempts = [('whole_file', options)]
                scoped_followup = manifest['protocol'].get('scope_selection') == 'all_multistorey_after_full_failure'
                nonempty = [s for s in inventory['storeys'] if s['spaces']]
                if (inventory['total_spaces'] > 2000 or (scoped_followup and len(nonempty) > 1)) and nonempty:
                    first = nonempty[0]
                    attempts.append(('lowest_nonempty_storey', {**options, 'ifc_storey_ids': [first['id']]}))
                for scope, opts in attempts:
                    if scope != 'whole_file' and row['attempts'][0].get('status') == 'annual_succeeded':
                        continue
                    current = {'scope': scope, 'selected_storeys': opts.get('ifc_storey_ids', []),
                               'source_space_count': inventory['total_spaces'] if scope == 'whole_file' else first['spaces']}
                    row['attempts'].append(current)
                    status, task = call(source['id']+'_'+scope+'_import', c.post(base+'/imports', json=opts))
                    current['import_http'] = status
                    if status != 201:
                        current.update(status='blocked_import', error=task)
                        records = require(source['id']+'_imports', c.get(base+'/imports'))
                        if records:
                            diagnostic = require(source['id']+'_diagnostics', c.get(base+'/imports/'+records[0]['import_id']+'/report.json'))
                            core.write_json(out/(source['id']+'-'+scope+'-diagnostics.json'), diagnostic)
                        persist()
                        continue
                    rooms = copy.deepcopy(task['candidate']['rooms'])
                    current.update(candidate_rooms=len(rooms), warnings=task['candidate'].get('warnings', []))
                    reconstructed = task['candidate'].get('diagnostics', {}).get('method') == 'IFC_ELEMENT_SECTION'
                    current['reconstructed_from_elements'] = reconstructed
                    if not reconstructed and len(rooms) != current['source_space_count']:
                        raise ValueError('Candidate room count differs from explicitly selected source scope')
                    for room in rooms: room.update(conditioned=True, include_floor_area=True)
                    previous = require(source['id']+'_current_model', c.get(base+'/model'))
                    body = {'name': source['id']+' explicit software scenario', 'rooms': rooms, 'reviewed': True,
                        'expected_revision': previous['revision'] if previous else 0, 'review_note': 'Software API acceptance only; all spaces assumed conditioned/countable, shared hypothetical office parameters and Golden weather, not field verification.',
                        'thermal': {**helper['THERMAL'], 'constructions': helper['ASSEMBLIES'],
                                    'geometry_tolerance_m': 0.0, 'adjacency_gap_m': 0.0, 'ifc_unpaired_policy': 'reject'}}
                    body['thermal'].update(manifest['protocol'].get('thermal_options', {}))
                    body['scope_exclusions'] = manifest['protocol'].get('scope_exclusions', {})
                    status, reviewed = call(source['id']+'_review', c.post(base+'/imports/'+task['import_id']+'/review', json=body))
                    current['review_http'] = status
                    if status != 200:
                        current.update(status='blocked_model_review', error=reviewed); persist(); continue
                    model = reviewed['model']
                    current.update(saved_rooms=len(model['rooms']), area_m2=model['area_m2'])
                    require(source['id']+'_area', c.post(base+'/model/sync-area', json={'revision': model['revision']}))
                    strict = require(source['id']+'_strict_validate', c.get(base+'/model/validate'))
                    current['strict_validation'] = strict
                    validation = strict
                    if not strict['can_publish']:
                        body['expected_revision'] = model['revision']
                        body['thermal']['ifc_unpaired_policy'] = 'adiabatic_scenario'
                        status, secondary = call(source['id']+'_explicit_assumption', c.put(base+'/model', json=body))
                        if status != 200:
                            current.update(status='blocked_assumption_save', error=secondary); persist(); continue
                        model = secondary
                        validation = require(source['id']+'_assumed_validate', c.get(base+'/model/validate'))
                        current['hypothetical_validation'] = validation
                    if not validation['can_publish']:
                        current.update(status='blocked_thermal_validation')
                        status, _ = call(source['id']+'_publish_refusal', c.post(base+'/model/publish', json={'revision': model['revision'],
                            'responsible_person': 'Isolated acceptance', 'review_note': 'Refusal-path verification only, not engineer attestation.'}))
                        current['refused_publish_http'] = status
                        persist(); continue
                    weather = core.relative_file(core.ROOT, core.load_case('reference_5zone')['weather'])
                    wid = require(source['id']+'_epw_upload', c.post(base+'/files', files={'file': (weather.name, weather.read_bytes())}), 201)['file_id']
                    ev = require(source['id']+'_epw_evidence', c.post(base+'/evidence', json={'type': 'epw', 'name': 'Golden reference software weather',
                        'source_file': wid, 'source_locator': 'Official shared reference EPW, not source-building actual weather',
                        'authority': 'EnergyPlus reference', 'permission': 'Software acceptance', 'acquisition_method': 'Official fixture',
                        'responsible_person': 'Isolated acceptance', 'status': 'ASSUMED'}), 201)
                    require(source['id']+'_epw_review', c.patch(base+'/evidence/'+ev['evidence_id'], json={'expected_revision': ev['revision'],
                        'review_state': 'confirmed', 'responsible_person': 'Isolated acceptance', 'review_note': 'Hypothetical software climate only, not actual site.'}))
                    require(source['id']+'_publish', c.post(base+'/model/publish', json={'revision': model['revision'],
                        'responsible_person': 'Isolated acceptance', 'review_note': 'Explicit hypothetical software scenario, not customer building performance.'}))
                    run = require(source['id']+'_queue', c.post(base+'/model-runs', json={}), 202)
                    deadline = time.monotonic()+core.engine_timeout_seconds()+120
                    while run['status'] in {'queued', 'running'} and time.monotonic() < deadline:
                        time.sleep(.5)
                        run = c.get('/api/runs/'+run['run_id']).json()
                    core.write_json(out/(source['id']+'-'+scope+'-run.json'), run)
                    current.update(status='annual_'+run['status'], run_id=run['run_id'], metrics=run['metrics'],
                        warnings_count=run['warnings_count'], error=run.get('error'), weather_sha256=core.sha(weather))
                    if run['status'] == 'succeeded':
                        report = c.get('/api/runs/'+run['run_id']+'/report.pdf')
                        current['pdf_http'] = report.status_code
                        if report.status_code == 200: (out/(source['id']+'-'+scope+'-report.pdf')).write_bytes(report.content)
                    persist()
                row['status'] = row['attempts'][-1]['status']
            except Exception as exc:
                row.update(status='harness_or_unhandled_error', error=type(exc).__name__+': '+str(exc)[:2000])
            row['seconds'] = round(time.monotonic()-started, 3)
            persist()
            print(row['id'], row['status'], row.get('inventory', {}).get('spaces'), row['seconds'], flush=True)
    result['finished_at'] = core.now()
    persist()


if __name__ == '__main__':
    main()
