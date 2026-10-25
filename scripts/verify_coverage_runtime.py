"""Public scoped IFCs + controlled courtyard -> real annual engine -> isolated restore.

All classifications, constructions and reference Golden weather are explicit test
assumptions. These scenarios do not predict the source buildings' actual energy.
"""
import argparse
import os
from pathlib import Path
import runpy
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources', type=Path, required=True)
    parser.add_argument('--duplex', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    os.environ['VRA_DATA_DIR'] = str(out/'runtime')
    from backend import core, model_geometry
    from backend.api import create_app
    from backend.runtime_backup import restore_snapshot
    from fastapi.testclient import TestClient
    helper = runpy.run_path(str(ROOT/'tests/test_model_workbench.py'))
    sys.path.insert(0, str(ROOT/'tests'))
    tests = runpy.run_path(str(ROOT/'tests/test_coverage_reliability_ops.py'))
    results, trace = [], []
    def checked(step, response, status=200):
        trace.append({'step':step, 'status':response.status_code, 'body':response.json()})
        core.write_json(out/'api-trace.json',trace)
        assert response.status_code == status, str(trace[-1])[:4000]
        return response.json()
    creds = {'username':'coverage_acceptance','password':'Coverage-acceptance-2026!'}
    app = create_app(out/'runtime', start_worker=True)
    with TestClient(app) as client:
        auth = checked('register', client.post('/api/auth/register',json={**creds,'display_name':'Isolated coverage acceptance'}))
        client.headers['X-CSRF-Token'] = auth['csrf_token']
        cases = [('courtyard',None,None), ('duplex',args.duplex,None),
                 ('esplanades_first',args.sources/'1807_EP_AR_v18.ifc','1oZ0wPs_PE8ANCPg3bIs4j'),
                 ('clinic_roof',args.sources/'Clinic_Architectural.ifc','3eM8WbY_59RR5TDWs3wwJL')]
        for name, source, floor in cases:
            started = time.monotonic()
            pid = helper['project'](client)
            base = '/api/projects/'+pid
            task = None
            if source:
                fid = helper['upload'](client,pid,source.name,source.read_bytes())
                options = {'file_id':fid}
                if floor:
                    inventory = checked(name+'_inventory',client.get(base+f'/files/{fid}/ifc-storeys'))
                    options.update(ifc_storey_ids=[floor],ifc_origin_m=inventory['suggested_origin_m'])
                task = checked(name+'_import',client.post(base+'/imports',json=options),201)
                rooms = task['candidate']['rooms']
            else:
                rooms = [tests['courtyard']()]
            for room in rooms:
                room.update(conditioned=True,include_floor_area=True)
            body = {'name':name+' explicit test scenario','rooms':rooms,'reviewed':True,'expected_revision':0,
                'thermal':{**helper['THERMAL'],'constructions':helper['ASSEMBLIES'],
                    'geometry_tolerance_m':.02,'adjacency_gap_m':.6 if source else 0.,
                    'ifc_unpaired_policy':'adiabatic_scenario' if source else 'reject'},
                'review_note':'Software acceptance only. All spaces assumed conditioned and counted, hypothetical constructions and Golden weather; not calibrated performance.'}
            model = checked(name+'_review',client.post(base+'/imports/'+task['import_id']+'/review',json=body))['model'] if task else checked(name+'_save',client.put(base+'/model',json=body))
            checked(name+'_area',client.post(base+'/model/sync-area',json={'revision':model['revision']}))
            epw = core.relative_file(core.ROOT,core.load_case('reference_5zone')['weather'])
            wid = helper['upload'](client,pid,epw.name,epw.read_bytes())
            ev = checked(name+'_weather',client.post(base+'/evidence',json={'type':'epw','name':'Golden test weather',
                'source_file':wid,'source_locator':'Reference weather only; not this building climate','authority':'EnergyPlus',
                'permission':'Reference software acceptance','acquisition_method':'Official fixture',
                'responsible_person':'Isolated acceptance','status':'ASSUMED'}),201)
            checked(name+'_weather_review',client.patch(base+'/evidence/'+ev['evidence_id'],json={
                'expected_revision':ev['revision'],'review_state':'confirmed','responsible_person':'Isolated acceptance',
                'review_note':'Test reference climate, no actual source-building weather-match claim.'}))
            validation = checked(name+'_validate',client.get(base+'/model/validate'))
            core.write_json(out/(name+'-validation.json'),validation)
            if name=='esplanades_first' and not validation['can_publish']:
                results.append({'case':name, 'status':'blocked_thermal_validation', 'rooms':len(rooms),
                    'project_id':pid,'source_sha256':core.sha(source),'blockers':validation['blockers']})
                core.write_json(out/'acceptance.json',results)
                print(name,'BLOCKED thermal validation, original failure retained',flush=True)
                continue
            assert validation['can_publish'], validation['blockers']
            checked(name+'_publish',client.post(base+'/model/publish',json={'revision':model['revision'],
                'responsible_person':'Isolated acceptance','review_note':'Explicit hypothetical operation and envelope, all scope limitations retained.'}))
            queued = checked(name+'_queue',client.post(base+'/model-runs',json={}),202)
            run = queued
            deadline = time.monotonic()+360
            while run['status'] in {'queued','running'} and time.monotonic()<deadline:
                time.sleep(.5)
                run = checked(name+'_poll',client.get('/api/runs/'+run['run_id']))
            core.write_json(out/(name+'-run.json'),run)
            assert run['status']=='succeeded', str(run)[:3000]
            assert run['metrics']['annual_days']==365
            result = {'case':name,'project_id':pid,'rooms':len(rooms),'segments':sum(len(model_geometry.parts(r)) for r in rooms),
                'net_area_m2':model['area_m2'],'source_sha256':core.sha(source) if source else None,
                'run_id':run['run_id'],'metrics':run['metrics'],'warnings':run['warnings_count'],
                'seconds':round(time.monotonic()-started,3),'weather_sha256':core.sha(epw),
                'scope':'Controlled geometry/public IFC scope with hypothetical inputs; not calibrated building performance'}
            results.append(result);core.write_json(out/'acceptance.json',results)
            print(name,'rooms',len(rooms),'warnings',run['warnings_count'],'area',model['area_m2'],flush=True)
        password = {'current_password':creds['password']}
        meta = checked('runtime_snapshot',client.post('/api/admin/runtime/backups',json=password),201)
        archive = out/'runtime'/'runtime-snapshots'/(meta['id']+'.zip')
        recovery = restore_snapshot(archive,out/'restored-runtime')
        with TestClient(create_app(out/'restored-runtime',start_worker=False)) as restored:
            login = checked('restored_login',restored.post('/api/auth/login',json=creds))
            restored.headers['X-CSRF-Token'] = login['csrf_token']
            for result in results:
                if not result.get('run_id'):
                    continue
                run = checked('restored_run',restored.get('/api/runs/'+result['run_id']))
                assert run['status']=='succeeded' and run['metrics']==result['metrics']
                report = restored.get('/api/runs/'+result['run_id']+'/report.html')
                assert report.status_code==200 and len(report.content)>1000
            recovery['restored_annual_reports'] = sum(bool(r.get('run_id')) for r in results)
        core.write_json(out/'restore-drill.json',{'snapshot':meta,'recovery':recovery})
        print('RESTORE',recovery,flush=True)


if __name__=='__main__':
    main()
