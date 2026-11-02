"""Twenty actual NASA POWER grid cells, source-bound QA; never building field data.

Writes new isolated files/database only. One remote request per cell; later checks
reuse the saved original. No provider keys, fake missing-data fills or model training.
"""
import argparse
import csv
from datetime import date
import io
import json
from pathlib import Path
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend import core
from backend.api import create_app
from backend.schema import ProjectCreate
from backend.weather import NASARequest, analyze_nasa

CELLS=[('Nanchang',28.68,115.86),('Harbin',45.80,126.53),('Beijing',39.90,116.40),
       ('Shanghai',31.23,121.47),('Guangzhou',23.13,113.26),('Kunming',25.04,102.72),
       ('Lhasa',29.65,91.12),('Urumqi',43.83,87.62),('Lanzhou',36.06,103.83),
       ('Chongqing',29.56,106.55),('Sanya',18.25,109.51),('Fuzhou',26.07,119.30),
       ('London',51.51,-0.13),('Dubai',25.20,55.27),('Singapore',1.35,103.82),
       ('Oslo',59.91,10.75),('Phoenix',33.45,-112.07),('Sydney',-33.87,151.21),
       ('CapeTown',-33.92,18.42),('SaoPaulo',-23.55,-46.63)]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--resume',action='store_true',help='Reuse cached originals in this isolated output, preserving prior result files')
    args=parser.parse_args();out=args.output.resolve()
    if args.resume:
        if not (out/'runtime/vra.sqlite3').is_file():raise SystemExit('Resume requires an existing isolated QA runtime')
        import shutil
        for name in ['results.json','pending-labels.json']:
            if (out/name).exists():shutil.copy2(out/name,out/(str(time.time_ns())+'-'+name))
    else:out.mkdir(exist_ok=False,parents=True)
    app=create_app(out/'runtime',start_worker=False);d=app.state.domain
    existing=d.store.list('project') if args.resume else []
    pid=existing[0]['project_id'] if existing else d.create_project(ProjectCreate(name='Public NASA grid-cell QA, not engineering buildings',
        building={'use':'research','location':'Public climate points; no building represented',
                  'region':'PUBLIC-GRID','area_m2':1.0,'notes':'Area is synthetic API setup only, not used in weather analysis.'}))['project_id']
    results=[];labels=[]
    for name,lat,lon in CELLS:
        start=time.monotonic();row={'cell':name,'latitude':lat,'longitude':lon,'status':'failed','checks':{}}
        try:
            options=NASARequest(latitude=lat,longitude=lon,start=date(2024,1,1),end=date(2024,12,31),label=name)
            record=d.weather.nasa(pid,options)
            _,path=d.file_record(pid,record['file_id']);raw=json.loads(path.read_bytes());values=raw['properties']['parameter']
            temps=list(values['T2M'].values());valid=all(v!=raw['header']['fill_value'] for v in temps)
            expected={'temperature_c':round(sum(temps)/len(temps),3) if valid else None,
                      'heating_degree_days':round(sum(max(0,18-v) for v in temps),3) if valid else None,
                      'cooling_degree_days':round(sum(max(0,v-26) for v in temps),3) if valid else None}
            # Explicit checks, with independent raw-value arithmetic (no calls to aggregate).
            checks=row['checks'];checks['year_rows']=len(record['rows'])==366
            checks['temperature_mean']=record['annual']['temperature_c']==expected['temperature_c']
            for key in ['heating_degree_days','cooling_degree_days']:
                actual=record['annual'][key];checks[key]=(actual is None and expected[key] is None) or (actual is not None and expected[key] is not None and abs(actual-expected[key])<.02)
            solar=list(values['ALLSKY_SFC_SW_DWN'].values());expected_solar=sum(solar) if all(v!=raw['header']['fill_value'] for v in solar) else None
            actual=record['annual']['solar_kwh_m2'];checks['solar_sum']=(actual is None and expected_solar is None) or (actual is not None and expected_solar is not None and abs(actual-expected_solar)<.02)
            checks['saved_reopen']=d.weather.get(pid,record['weather_id'])['source_hash']==core.sha(path)
            checks['csv_rows']=len(list(csv.DictReader(io.StringIO(d.weather.csv(pid,record['weather_id']).decode('utf-8-sig')))))==366
            checks['cache_reuses_original']=d.weather.nasa(pid,options)['weather_id']==record['weather_id']
            alternate=analyze_nasa(raw,options.model_copy(update={'heating_base_c':20.0,'cooling_base_c':24.0}))
            checks['alternate_hdd']=valid and abs(alternate['annual']['heating_degree_days']-sum(max(0,20-v) for v in temps))<.02
            checks['alternate_cdd']=valid and abs(alternate['annual']['cooling_degree_days']-sum(max(0,v-24) for v in temps))<.02
            row.update(status='passed' if all(checks.values()) else 'failed',source_sha256=core.sha(path),
                       source_url=record['provenance']['url'],annual=record['annual'],quality=record['quality'])
            # Derived answers, never independently approved training examples.
            for key in ['temperature_c','heating_degree_days','cooling_degree_days','solar_kwh_m2']:
                labels.append({'external_id':name+'-'+key,'dataset':'NASA POWER 2024 grid QA 2026-11-02',
                    'project_group':'nasa-grid-'+name.casefold(),'building_ref':'No building: grid cell '+name,
                    'source_nature':'reference','source_url':row['source_url'],'source_sha256':row['source_sha256'],
                    'input_sha256':row['source_sha256'],'license':'NASA POWER public data; attribution required; original metadata retained',
                    'training_permission':'unknown','rights_basis':'Public climate QA only; not a commercial model training permission determination.',
                    'provenance_note':'NASA POWER gridded/reanalysis daily LST, not building/site measured data. Machine-derived answer; independent approval absent.',
                    'function':'weather_analysis','prompt':f'For {name} 2024 daily LST, report {key} using HDD18/CDD26.',
                    'answer':json.dumps(record['annual'][key]),'context':json.dumps({'coordinates':[lon,lat],'period':'2024-01-01/2024-12-31','metric':key,'time_standard':'LST','source_sha256':row['source_sha256']}),
                    'reserved_benchmark':True})
        except Exception as exc:
            row['error']=str(exc)[:400]
        row['duration_s']=round(time.monotonic()-start,3);results.append(row)
        core.write_json(out/'results.json',{'cells':results,'passed':sum(r['status']=='passed' for r in results),
            'scope':'Weather only; grid cells are not independent buildings or field calibration.'})
        core.write_json(out/'pending-labels.json',{'cases':labels})
        print(json.dumps({'cell':name,'status':row['status'],'checks':row['checks'],'error':row.get('error')},ensure_ascii=False),flush=True)
        time.sleep(.5)
    print('COMPLETE: '+str(len(labels))+' pending derived labels; no training.',flush=True)


if __name__=='__main__':main()
