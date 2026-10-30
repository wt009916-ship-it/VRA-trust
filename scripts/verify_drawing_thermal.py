"""Public LookHere drawing or Duplex IFC -> real API -> 3 annual native runs.

All construction, schedules, ventilation and weather below are TEST ASSUMPTIONS.
Original input is external and never copied into the repository. Results are not
calibration or predictions of that source building's actual consumption.
"""
import argparse
import os
from pathlib import Path
import runpy
import secrets
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--heat-pump', action='store_true', help='Compare native fixed PTHP at COP 2 and 4')
    parser.add_argument('--capacity-only', action='store_true', help='PTHP COP 4, double capacities and airflow; explicit sensitivity scenario')
    args = parser.parse_args()
    if args.capacity_only and not args.heat_pump:
        parser.error('--capacity-only requires --heat-pump')
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    os.environ['VRA_DATA_DIR'] = str(out/'private-runtime')
    from backend import core, model_geometry
    from backend.api import create_app
    from fastapi.testclient import TestClient
    helper = runpy.run_path(str(ROOT/'tests/test_model_workbench.py'))
    source = args.source.resolve()
    digest = core.sha(source)
    raster = source.suffix.lower() == '.pdf'
    trace = []

    def checked(step, response, expected=200):
        data = response.json()
        trace.append({'step': step, 'status': response.status_code, 'body': data})
        core.write_json(out/'api-trace.json', trace)
        assert response.status_code == expected, str(data)[:3000]
        return data

    with TestClient(create_app(out/'private-runtime', start_worker=True)) as client:
        login = client.post('/api/auth/register', json={'username': 'thermal_acceptance',
            'display_name': 'Isolated test', 'password': secrets.token_urlsafe(32)+'Aa9!'})
        assert login.status_code == 200, login.text
        client.headers['X-CSRF-Token'] = login.json()['csrf_token']
        pid = helper['project'](client)
        base = '/api/projects/'+pid
        fid = helper['upload'](client, pid, source.name, source.read_bytes())
        options = {'file_id': fid}
        if raster:
            options.update(mode='local_raster', page=6, scale_to_m=8.8/510, crop_px=[825, 285, 1360, 775],
                closure_m=.8, scale_basis='Page 6 external 8.80 m dimension; 510 pixels between exterior faces. Test calibration.')
            preview = client.get(base+f'/files/{fid}/plan-preview?page=6')
            assert preview.status_code == 200
            (out/'preview.png').write_bytes(preview.content)
        start = time.perf_counter()
        task = checked('recognize_original', client.post(base+'/imports', json=options), 201)
        seconds = time.perf_counter()-start
        rooms = task['candidate']['rooms']
        assert len(rooms) == (6 if raster else 21)
        labelled = [r['drawing'] for r in rooms if r.get('drawing') and r['drawing']['annotated_area_m2']]
        if raster:
            assert len(labelled) == 5
            assert max(abs(d['area_error_percent']) for d in labelled) < 10
        for r in rooms:
            roof = 'Roof' in r['name']
            r.update(conditioned=not roof, include_floor_area=not roof)
        op = {'weekday': [float(8 <= h < 18) for h in range(24)], 'weekend': [0.]*24,
              'outdoor_air_l_s_person': 5., 'outdoor_air_l_s_m2': .3,
              'sensible_recovery': .6, 'latent_recovery': 0., 'heating_setback_c': 12., 'cooling_setback_c': 32.,
              'source_note': 'Explicit software test assumptions: weekday office use, weekend closed, hypothetical ventilation.'}
        thermal = {**helper['THERMAL'], 'constructions': helper['ASSEMBLIES'], 'operation': op,
                   'geometry_tolerance_m': .02, 'adjacency_gap_m': .35 if raster else .6,
                   'ifc_unpaired_policy': 'reject' if raster else 'adiabatic_scenario'}
        if args.heat_pump:
            thermal['heat_pump'] = dict(cooling_w_m2=120., heating_w_m2=150., airflow_l_s_m2=6.5,
                cooling_cop=2., heating_cop=2., sensible_heat_ratio=.75, fan_pressure_pa=150.,
                fan_total_efficiency=.6, fan_motor_efficiency=.9, supplemental_w_m2=150., minimum_outdoor_c=-15., minimum_cooling_outdoor_c=0.,
                source_note='Explicit software-test equipment assumptions; native default curves; no manufacturer or calibration claim.')
            op['sensible_recovery'] = 0.
            if args.capacity_only:
                thermal['heat_pump'].update(cooling_cop=4., heating_cop=4.)
                for key in ('cooling_w_m2', 'heating_w_m2', 'airflow_l_s_m2', 'supplemental_w_m2'):
                    thermal['heat_pump'][key] *= 2
        body = {'name': source.stem+' / assumed load scenario', 'rooms': rooms, 'reviewed': True,
                'thermal': thermal, 'expected_revision': 0,
                'review_note': 'Automated software acceptance, not engineer attestation. All regions retained. '
                               'Raster height 3 m, occupancy and thermal inputs hypothetical; not calibrated performance.'}
        model = checked('review_geometry', client.post(base+'/imports/'+task['import_id']+'/review', json=body))['model']
        checked('sync_area', client.post(base+'/model/sync-area', json={'revision': model['revision']}))
        weather = core.relative_file(core.ROOT, core.load_case('reference_5zone')['weather'])
        wid = helper['upload'](client, pid, weather.name, weather.read_bytes())
        ev = checked('weather_assumption', client.post(base+'/evidence', json={'type': 'epw', 'name': 'Golden reference weather',
            'source_file': wid, 'source_locator': 'Golden reference, not source building climate', 'authority': 'EnergyPlus',
            'permission': 'Reference software test', 'acquisition_method': 'Official fixture',
            'responsible_person': 'Isolated test', 'status': 'ASSUMED'}), 201)
        checked('review_weather', client.patch(base+'/evidence/'+ev['evidence_id'], json={
            'expected_revision': ev['revision'], 'review_state': 'confirmed', 'responsible_person': 'Isolated test',
            'review_note': 'Test weather only. Not a documented location match for this building.'}))
        results = []
        scenarios = ('pthp_cop2', 'pthp_cop4') if args.heat_pump else ('ventilation_recovery', 'ventilation_no_recovery', 'no_mechanical_ventilation')
        if args.capacity_only:
            scenarios = ('pthp_cop4_capacity2',)
        for index, name in enumerate(scenarios):
            if index:
                body['expected_revision'] = model['revision']
                body['thermal']['operation']['sensible_recovery'] = 0.
                if index == 2:
                    body['thermal']['operation'].update(outdoor_air_l_s_person=0., outdoor_air_l_s_m2=0.)
                if args.heat_pump:
                    body['thermal']['heat_pump'].update(cooling_cop=4., heating_cop=4.)
                model = checked(name+'_save', client.put(base+'/model', json=body))
            check = checked(name+'_validate', client.get(base+'/model/validate'))
            assert check['can_publish'], check['blockers']
            checked(name+'_publish', client.post(base+'/model/publish', json={'revision': model['revision'],
                'responsible_person': 'Isolated test', 'review_note': 'Software test only; all assumptions and unresolved boundaries retained.'}))
            exported = client.get(base+'/model/export.idf')
            assert exported.status_code == 200
            (out/(name+'.idf')).write_bytes(exported.content)
            hb = client.get(base+'/model/geometry.hbjson')
            assert hb.status_code == 200
            (out/(name+'.hbjson')).write_bytes(hb.content)
            core.write_json(out/(name+'-model.json'), model)
            run = checked(name+'_queue', client.post(base+'/model-runs', json={}), 202)
            deadline = time.monotonic()+300
            while run['status'] in {'queued', 'running'} and time.monotonic() < deadline:
                time.sleep(.5)
                run = client.get('/api/runs/'+run['run_id']).json()
            core.write_json(out/(name+'-result.json'), run)
            assert run['status'] == 'succeeded', str(run)[:2500]
            assert run['metrics']['annual_days'] == 365
            results.append({'scenario': name, 'metrics': run['metrics'], 'warnings': run['warnings_count'],
                            'run_id': run['run_id'], 'engine_calls': run['engine_calls_executed'],
                            'geometry_review': check['geometry_review']})
            print(name, run['metrics']['energy_by_carrier_kwh'], 'warnings', run['warnings_count'], flush=True)
        if args.heat_pump:
            electricity = [r['metrics']['energy_by_carrier_kwh']['Electricity'] for r in results]
            if not args.capacity_only:
                assert electricity[1] < electricity[0]*.95, electricity
            assert all(r['metrics']['energy_by_carrier_kwh']['District Heating'] == 0 for r in results)
        else:
            heating = [r['metrics']['energy_by_carrier_kwh']['District Heating'] for r in results]
            assert heating[1] > heating[0] and heating[1] > heating[2], heating
        assert core.sha(source) == digest
        summary = {'verified_at': core.now(), 'source_sha256': digest, 'source_name': source.name,
                   'rooms': len(rooms), 'segments': sum(len(model_geometry.parts(r)) for r in rooms),
                   'import_seconds': seconds, 'area_checks': labelled, 'scenarios': results,
                   'weather_sha256': core.sha(weather), 'scope': 'Public source; explicit assumed load scenarios, not calibrated building energy'}
        core.write_json(out/'acceptance.json', summary)
        print('ACCEPTANCE', out/'acceptance.json')


if __name__ == '__main__':
    main()
