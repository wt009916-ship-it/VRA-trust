import hashlib,json,shutil,sqlite3,subprocess
from pathlib import Path
out=Path(__file__).resolve().parent;repo=out.parents[1]
native=Path((out/'windows-output-v3.txt').read_text().strip())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
windows=json.loads((native/'receipt.json').read_text())
linux=json.loads((out/'linux-v1.json').read_text())
assert windows['gold_sha256']==linux['gold_sha256']
assert windows['script_sha256']==linux['script_sha256']==sha(repo/'scripts/verify_freefloat_thermal.py')
comparisons=[]
for a,b in zip(windows['cases'],linux['cases']):
    assert a['name']==b['name'] and a['model_sha256']==b['model_sha256'] and a['status']==b['status']
    difference=max(abs(v-w) for key in a['native_hourly'] for v,w in zip(a['native_hourly'][key],b['native_hourly'][key]))
    comparisons.append({'name':a['name'],'status':a['status'],'maximum_temperature_error_K':a['maximum_temperature_error_K'],
        'temperature_and_load_cross_platform_max_difference':difference,'same_frozen_model':True})
inputs=out/'native-inputs';inputs.mkdir()
shutil.copyfile(native/'predeclared.json',inputs/'predeclared.json')
shutil.copyfile(native/'receipt.json',out/'windows-v3.json')
for case in windows['cases']:
    dest=inputs/case['name'];dest.mkdir()
    shutil.copyfile(native/case['name']/'input.idf',dest/'input.idf')
    shutil.copyfile(native/case['name']/'output/eplusout.err',dest/'windows.err')
    shutil.copyfile(native/case['name']/'hourly.json',dest/'windows-hourly.json')
(out/'cross-platform-v1.json').write_text(json.dumps({'same_gold':True,'cases':comparisons},indent=2))
old=json.loads((repo/'validation/dynamic-thermal-20261107/release-receipt.json').read_text())
tables={}
with sqlite3.connect((repo/'validation/thermal-20261104/ui-runtime/vra.sqlite3').resolve().as_uri()+'?mode=ro',uri=True) as con:
    for table,cols,order in [('records','kind,id,revision,project_id,body','kind,id,revision'),('jobs','id,project_id,state,body,error','id')]:
        h=hashlib.sha256();count=0
        for row in con.execute('SELECT '+cols+' FROM '+table+' ORDER BY '+order):
            h.update(json.dumps(row,ensure_ascii=False,separators=(',',':')).encode()+b'\n');count+=1
        tables[table]={'rows':count,'sha256':h.hexdigest()}
assert tables==old['original_data_unchanged']
backend=[]
for p in sorted((repo/'backend').rglob('*.py')):
    rel=p.relative_to(repo).as_posix()
    if '__pycache__' in rel:continue
    raw=subprocess.check_output(['git','show','HEAD:'+rel])
    assert p.read_bytes()==raw,rel
    backend.append({'path':rel,'sha256':sha(p)})
(out/'source-preservation-v1.json').write_text(json.dumps({'backend_byte_unchanged_from_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
    'backend_files':backend,'original_business_tables':tables,'reference_pointer_sha256':sha(repo/'validation/reference_comparison.json'),
    'unrelated_edit_sha256':sha(repo/'.agents/skills/vra-trust/SKILL.md')},indent=2))
print(json.dumps({'cases':len(comparisons),'passed_per_platform':sum(c['status']=='passed' for c in comparisons),
    'cross_platform_max_difference':max(c['temperature_and_load_cross_platform_max_difference'] for c in comparisons),
    'backend_files_unchanged':len(backend),'business_data_unchanged':True,'published_input_bytes':sum(p.stat().st_size for p in inputs.rglob('*') if p.is_file())}))
