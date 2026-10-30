import csv,io,json,os,sys,time,subprocess
from pathlib import Path
import argparse
parser=argparse.ArgumentParser(description='Verify public BDG2/NIST raw CSVs through an isolated application database; never a geometry or field-calibration acceptance.')
parser.add_argument('--source-dir',type=Path,required=True)
parser.add_argument('--output-dir',type=Path,required=True)
args=parser.parse_args()
root=args.source_dir.resolve();repo=Path(__file__).resolve().parents[1];sys.path.insert(0,str(repo))
os.environ['VRA_REGISTRATION_MODE']='open'
from backend import core
from backend.api import create_app
from fastapi.testclient import TestClient
out=args.output_dir.resolve();out.mkdir(parents=True,exist_ok=False)
source_hashes={}
for filename in ['bdg2/metadata-original.csv','bdg2/electricity.csv','nist/HVAC-hour.csv']:
    actual=core.sha(root/filename)
    expected={'bdg2/metadata-original.csv':'992d0b29f24f96ad4332bc4dbb534b7bdd7dd2689aad093f94e93068ecddca02','bdg2/electricity.csv':'039d909d8981e2d69eaeb366144e6ab7e84fa5e7e216aee42bddd95384a66418','nist/HVAC-hour.csv':'7d31e46a69895c195daedee1f154d855c1a7b7b48338fce336df0d60d051379e'}[filename]
    assert actual==expected,filename+' source mismatch'
    source_hashes[filename]=actual
execution={'script_sha256':core.sha(__file__),'measurement_parser_sha256':core.sha(repo/'backend/measurements.py'),'timezone_helper_sha256':core.sha(repo/'scripts/public_meter_timezone.cjs'),'sources':source_hashes,'started_at':core.now(),'api_transport':'FastAPI TestClient, real isolated DB/files, no live TCP in this batch'}
core.write_json(out/'execution.json',execution)
metadata=list(csv.DictReader((root/'bdg2/metadata-original.csv').open(encoding='utf-8-sig')))
with (root/'bdg2/electricity.csv').open(encoding='utf-8') as f:
    reader=csv.DictReader(f);columns=set(reader.fieldnames);rows=[]
    for r in reader:
        if r['timestamp']>='2016-02-01':break
        rows.append(r)
valid=[m for m in metadata if m['building_id'] in columns]
chosen=[];uses=set()
for site in sorted({m['site_id'] for m in valid}):
    candidates=[m for m in valid if m['site_id']==site]
    m=min(candidates,key=lambda m:(m['primaryspaceusage'] in uses,m['building_id']))
    chosen.append(m);uses.add(m['primaryspaceusage'])
for m in sorted(valid,key=lambda m:(m['primaryspaceusage'] in uses,m['building_id'])):
    if len(chosen)>=20:break
    if m not in chosen:chosen.append(m);uses.add(m['primaryspaceusage'])
offset_lookup=json.loads(subprocess.run(['node',str(repo/'scripts/public_meter_timezone.cjs')],input=json.dumps({'zones':list({m['timezone'] for m in chosen}),'dates':[r['timestamp'].replace(' ','T') for r in rows]}),capture_output=True,text=True,check=True).stdout)
records=[];comparisons=[]
app=create_app(out/'runtime',start_worker=False)
with TestClient(app) as client:
    password='Isolated-meter-'+__import__('secrets').token_hex(16)
    access={'username':'public_meter_review','password':password,'projects':{}}
    core.write_json(out/'access.private.json',access)
    login=client.post('/api/auth/register',json={'username':'public_meter_review','display_name':'Isolated public data review','password':password});assert login.status_code==200,login.status_code
    client.headers['X-CSRF-Token']=login.json()['csrf_token']
    for m in chosen:
        t=time.perf_counter();bid=m['building_id']
        create=client.post('/api/projects',json={'name':'BDG2 real measured / '+bid,'data_nature':'engineering_reference','building':{'use':m['primaryspaceusage'] or 'UNKNOWN: source has no use classification','location':m['site_id'],'region':'PUBLIC-ANONYMOUS','area_m2':float(m['sqm'])}})
        assert create.status_code==201,create.text
        pid=create.json()['project_id'];base=f'/api/projects/{pid}'
        access['projects'][bid]=pid;core.write_json(out/'access.private.json',access)
        buffer=io.StringIO();writer=csv.writer(buffer);writer.writerow(['timestamp','energy_kwh'])
        writer.writerows((r['timestamp'],r[bid]) for r in rows)
        content=buffer.getvalue().encode();(out/(bid+'.csv')).write_bytes(content)
        uploaded=client.post(base+'/files',files={'file':(bid+'.csv',content)});assert uploaded.status_code==201,uploaded.text
        fid=uploaded.json()['file_id'];offsets=set(offset_lookup[m['timezone']])
        assert len(offsets)==1,('January timezone transition',bid,offsets)
        body=dict(file_id=fid,building_ref=bid,meter_boundary='BDG2 whole building electricity meter',quantity='electricity',role='observed',timestamp_column='timestamp',value_column='energy_kwh',unit='kWh',interval_seconds=3600,utc_offset_minutes=offsets.pop(),source_note='BDG2 author-published raw hourly kWh_sum. January2016 only, original values unchanged; IANA metadata timezone has one offset throughout selected month. Anonymous measured building, not an identified geometry or calibrated HVAC model.')
        parsed=client.post(base+'/measurements',json=body);assert parsed.status_code==201,parsed.text
        reread=client.get(base+'/measurements');assert reread.status_code==200
        value=parsed.json()
        record={'building_id':bid,'site_id':m['site_id'],'primary_use':m['primaryspaceusage'],'sqm':m['sqm'],'timezone':m['timezone'],'geometry_form':None,'real_building_basis':'Miller et al.2020 DOI10.1038/s41597-020-00712-x, anonymised measured building metadata and raw meter column',
         'scope':'Meter workflow only; not a whole-building BIM/thermal acceptance or independent construction project',
         'original_source_sha256':'039d909d8981e2d69eaeb366144e6ab7e84fa5e7e216aee42bddd95384a66418','subset_sha256':core.sha(out/(bid+'.csv')),'selection':'2016-01-01 inclusive to2016-02-01 exclusive, exact source column values, no imputation','api_status':[create.status_code,uploaded.status_code,parsed.status_code,reread.status_code],'summary':value['summary'],'seconds':time.perf_counter()-t}
        if value['summary']['eligible_for_comparison'] and sum(c['api_status']==201 for c in comparisons)<10:
            # Transparent software baseline, learned only from the first14days.
            training=[r for r in rows if r['timestamp']<'2016-01-15']
            means={h:sum(float(r[bid]) for r in training if int(r['timestamp'][11:13])==h)/sum(int(r['timestamp'][11:13])==h for r in training) for h in range(24)}
            pbuf=io.StringIO();w=csv.writer(pbuf);w.writerow(['timestamp','energy_kwh']);w.writerows((r['timestamp'],means[int(r['timestamp'][11:13])]) for r in rows)
            pred=client.post(base+'/files',files={'file':('hourly-mean-prediction.csv',pbuf.getvalue().encode())});assert pred.status_code==201
            prediction=client.post(base+'/measurements',json={**body,'file_id':pred.json()['file_id'],'role':'prediction','source_note':'Authored hour-of-day mean baseline trained on January1-14 only; predictions never source measurements or native EnergyPlus.'});assert prediction.status_code==201
            offset=body['utc_offset_minutes'];sign='+' if offset>=0 else '-';cutoff=f'2016-01-15T00:00:00{sign}{abs(offset)//60:02d}:{abs(offset)%60:02d}'
            comparison=client.post(base+'/measurements/compare',json={'observed_id':value['measurement_id'],'prediction_id':prediction.json()['measurement_id'],'holdout_start':cutoff,'fitted_parameters':24,'source_note':'First14days train24hour means. Remaining17days withheld. Tests imported prediction scoring, not field calibration.'})
            comparisons.append({'building_id':bid,'api_status':comparison.status_code,**({k:comparison.json()[k] for k in ['training','holdout','calibrated','scope']} if comparison.status_code==201 else {'error':comparison.json()})})
        records.append(record);print(bid,value['summary']['valid_rows'],value['summary']['issues'],flush=True)
        core.write_json(out/'progress.json',{'records':records,'comparisons':comparisons})
    # Actual NIST installed heat pump hourly power, two independent component channels, one building.
    pid=client.post('/api/projects',json={'name':'NIST NZERTF measured heat pump','data_nature':'engineering_reference','building':{'use':'residential laboratory','location':'Gaithersburg','region':'US-MD','area_m2':252.,'notes':'252m2 living area per NIST publication922510; excludes135m2unfinished basement. Area unused in meter-only analysis.'}}).json()['project_id'];base=f'/api/projects/{pid}'
    access['projects']['NIST']=pid;core.write_json(out/'access.private.json',access)
    source=root/'nist/HVAC-hour.csv';uploaded=client.post(base+'/files',files={'file':('NIST-HVAC-hour.csv',source.read_bytes())});assert uploaded.status_code==201,uploaded.text
    nist=[]
    for col in ['HVAC_HeatPumpIndoorUnitPower','HVAC_HeatPumpOutdoorUnitPower']:
        r=client.post(base+'/measurements',json=dict(file_id=uploaded.json()['file_id'],building_ref='NIST_NZERTF',meter_boundary=col,quantity='electricity',role='observed',timestamp_column='Timestamp',value_column=col,unit='W',interval_seconds=3600,source_note='NIST2013-14 NZERTF original hourly file. Metadata channel is average power W, source timestamps carry explicit offset. Actual instrumented test house with emulated occupants, not chiller plant.'));assert r.status_code==201,r.text
        nist.append({'channel':col,'api_status':r.status_code,'source_sha256':core.sha(source),'summary':r.json()['summary']})
core.write_json(out/'results.json',{'bdg2':records,'comparisons':comparisons,'nist':nist,'distinct_bdg2_buildings':len(records),'distinct_bdg2_sites':len({r['site_id'] for r in records}),'independent_geometry_acceptances':0,'central_plant_field_calibrations':0})
print('COMPLETE',len(records),'buildings',len(comparisons),'holdout_comparisons',flush=True)

assert execution['measurement_parser_sha256']==core.sha(repo/'backend/measurements.py')
assert execution['script_sha256']==core.sha(__file__)
core.write_json(out/'completed.json',{'finished_at':core.now(),'executed_code_unchanged':True})
