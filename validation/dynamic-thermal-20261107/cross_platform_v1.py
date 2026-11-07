import json,os,sys,time
from pathlib import Path
assert os.getuid()==65534
out=Path(__file__).resolve().parent
linux=Path(json.loads((out/'linux-source-v1.json').read_text())['root'])
def mounted(value):return Path('/mnt/'+value[0].lower()+value[2:].replace('\\','/'))
windows=mounted(json.loads((out/'candidate-source-v1.json').read_text())['root'])
win_dynamic=mounted((out/'native-suite-path-v2.txt').read_text().strip())
a=json.loads((win_dynamic/'receipt.json').read_text())['cases'];b=json.loads((linux/'dynamic/receipt.json').read_text())['cases']
checks=[]
for left,right in zip(a,b):
    assert left['case']==right['case'] and left['status']==right['status']
    delta={k:abs(left[k]-right[k]) for k in ['maximum_unmultiplied_error_W','temperature_max_error_K','building_peak_W','sum_zone_peaks_W']}
    assert max(delta.values())<1e-6
    checks.append({'case':left['case'],'windows_status':left['status'],'linux_status':right['status'],'absolute_differences':delta})
annual=[]
for scheme in ['baseline','R1','R2']:
    runs=[]
    for root in [windows,linux]:
        comparison=json.loads((root/'validation/reference_comparison.json').read_text())
        rid=next(r['run_id'] for r in comparison['results'] if r['scheme_id']==scheme)
        runs.append(json.loads((root/'runs'/rid/'result.json').read_text()))
    h=[r['metrics']['hourly_thermal'] for r in runs]
    assert all(v['status']=='calculated_model_scenario' and v['summary']['hour_count']==8760 and len(v['summary']['zones'])==6 for v in h)
    delta={k:abs(h[0]['summary']['building'][k]['value_W']-h[1]['summary']['building'][k]['value_W']) for k in ['heating_peak','cooling_peak']}
    assert max(delta.values())<1e-6
    assert runs[0]['metrics']['annual_energy_kwh']==runs[1]['metrics']['annual_energy_kwh']
    annual.append({'scheme':scheme,'run_ids':[r['run_id'] for r in runs],'annual_energy_kwh':runs[0]['metrics']['annual_energy_kwh'],
                   'hourly_peaks_W':h[0]['summary']['building'],'peak_differences_W':delta,'model_sha256':h[0]['model_sha256'],
                   'sql_hashes':[v['sql_sha256'] for v in h],'hours':8760,'zones':6})
sys.path.insert(0,str(linux))
from backend import core
from backend.hourly_thermal import inspect_hourly_thermal
measurements=[]
for r in annual:
    rd=linux/'runs'/r['run_ids'][1]
    start=time.monotonic();receipt=inspect_hourly_thermal(rd/'output/eplusout.sql',rd/'input/model.idf')
    assert receipt['status']=='calculated_model_scenario'
    measurements.append({'scheme':r['scheme'],'elapsed_seconds':time.monotonic()-start,'sql_bytes':(rd/'output/eplusout.sql').stat().st_size})
record={'uid':os.getuid(),'dynamic':checks,'annual':annual,'parser_timings_linux':measurements,'comparison_tolerance_W':1e-6,
        'notice':'Fresh native runs, not re-signed older evidence. Timing observations are not concurrency or production capacity claims.'}
with (out/'cross-platform-v1.json').open('x',encoding='utf-8') as f:json.dump(record,f,ensure_ascii=False,indent=2)
print(json.dumps({'dynamic_cases':len(checks),'matching_statuses':True,'annual_cases':len(annual),'timings':measurements}))
