"""Replay identical, already frozen Windows inputs and gold on unprivileged Linux."""
import hashlib,json,os,re,sys,uuid
from pathlib import Path
assert os.getuid()==65534
out=Path(__file__).resolve().parent;source=out/'native-windows-v2'
root=Path(json.loads((out/'linux-source-v1.json').read_text())['root'])
sys.path.insert(0,str(root))
from backend import core
from backend.execution import Policy,supervise
from backend.hourly_thermal import inspect_hourly_thermal
ctx=json.loads((out.parents[1]/'validation/linux-isolation-20261105/linux-runtime-v2.json').read_text())
os.environ['ENERGYPLUS_EXE']=ctx['engine']
workroot=root/('exact-dynamic-'+uuid.uuid4().hex);workroot.mkdir()
inputs=json.loads((source/'inputs.json').read_text());gold=json.loads((source/'predeclared.json').read_text())
assert core.sha(source/'predeclared.json')==inputs['gold_sha256']
(workroot/'predeclared.json').write_bytes((source/'predeclared.json').read_bytes())
for spec in gold['cases']:
    work=workroot/spec['name'];work.mkdir()
    raw=(source/spec['name']/'input.idf').read_bytes()
    assert hashlib.sha256(raw).hexdigest()==inputs['model_hashes'][spec['name']]
    (work/'input.idf').write_bytes(raw)
core.write_json(workroot/'inputs.json',inputs)
record={'root':str(workroot),'uid':os.getuid(),'models_byte_identical':True,'gold_byte_identical':True,'gold_sha256':inputs['gold_sha256'],'cases':[]}
for spec in gold['cases']:
    work=workroot/spec['name'];native=work/'output';native.mkdir();logs=work/'logs';logs.mkdir()
    row={'case':spec['name'],'status':'not_run','model_sha256':core.sha(work/'input.idf')}
    try:
        row['execution']=supervise([core.engine_path(),'-d',native,work/'input.idf'],work,logs,Policy(),90,output=native)
        assert not re.search(r'\*\*\s*(Severe|Fatal)\s*\*\*',(native/'eplusout.err').read_text(),re.I)
        receipt=inspect_hourly_thermal(native/'eplusout.sql',work/'input.idf',environment_index=1)
        assert receipt['status']=='calculated_model_scenario',receipt.get('reason')
        core.write_json(work/'hourly.json',receipt)
        profile=receipt['summary']['peak_day_profiles'][0];scale=spec['multiplier']*spec['list_multiplier']
        row.update(maximum_unmultiplied_error_W=max(abs(v/scale-g) for z,values in profile['zones'].items() for v,g in zip(values['heating_W'],spec['gold_unmultiplied_heating_W'][z])),
                   temperature_max_error_K=max(abs(v-20) for values in profile['zones'].values() for v in values['temperature_C']),
                   tolerance_unmultiplied_W=spec['tolerance_unmultiplied_W'],building_peak_W=receipt['summary']['building']['heating_peak']['value_W'],
                   sum_zone_peaks_W=sum(z['heating_peak']['value_W'] for z in receipt['summary']['zones']),native_sql_sha256=core.sha(native/'eplusout.sql'))
        row['status']='passed' if row['maximum_unmultiplied_error_W']<=spec['tolerance_unmultiplied_W'] and row['temperature_max_error_K']<.01 else 'numerical_mismatch'
    except Exception as exc:row.update(status='failed',error=type(exc).__name__+': '+str(exc))
    record['cases'].append(row);core.write_json(work/'record.json',row)
    print(json.dumps({k:v for k,v in row.items() if k not in ['execution','model_sha256','native_sql_sha256']}),flush=True)
core.write_json(out/'native-linux-exact-v1.json',record)
windows=json.loads((source/'receipt.json').read_text())['cases'];comparisons=[]
for a,b in zip(windows,record['cases']):
    assert a['case']==b['case'] and a['status']==b['status']
    difference={k:abs(a[k]-b[k]) for k in ['maximum_unmultiplied_error_W','temperature_max_error_K','building_peak_W','sum_zone_peaks_W']}
    comparisons.append({'case':a['case'],'status':b['status'],'absolute_differences':difference,'within_1e_6_W':max(difference.values())<1e-6})
core.write_json(out/'cross-platform-exact-v1.json',{'models_byte_identical':True,'gold_byte_identical':True,'comparison_tolerance_W':1e-6,'comparisons':comparisons})
print(json.dumps({'maximum_difference':max(max(c['absolute_differences'].values()) for c in comparisons),'all_within_1e_6_W':all(c['within_1e_6_W'] for c in comparisons)}))
