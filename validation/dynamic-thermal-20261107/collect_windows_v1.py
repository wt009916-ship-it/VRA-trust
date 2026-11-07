import hashlib,json,sqlite3
from pathlib import Path
out=Path(__file__).resolve().parent;repo=out.parents[1]
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
root=Path(json.loads((out/'candidate-source-v1.json').read_text())['root'])
native=Path((out/'native-suite-path-v2.txt').read_text().strip())
dest=out/'native-windows-v2';dest.mkdir()
for name in ['predeclared.json','inputs.json','receipt.json']:
    (dest/name).write_bytes((native/name).read_bytes())
inventory=[]
for case in json.loads((native/'receipt.json').read_text())['cases']:
    work=native/case['case'];target=dest/case['case'];target.mkdir()
    for name in ['input.idf','record.json','hourly.json','output/eplusout.err']:
        p=work/name;d=target/name;d.parent.mkdir(parents=True,exist_ok=True);d.write_bytes(p.read_bytes())
    inventory.append({'case':case['case'],'sql_sha256':digest(work/'output/eplusout.sql'),'sql_bytes':(work/'output/eplusout.sql').stat().st_size})
tables={}
db=repo/'validation/thermal-20261104/ui-runtime/vra.sqlite3'
with sqlite3.connect(db.resolve().as_uri()+'?mode=ro',uri=True) as con:
    for table,cols,order in [('records','kind,id,revision,project_id,body','kind,id,revision'),('jobs','id,project_id,state,body,error','id')]:
        h=hashlib.sha256();count=0
        for row in con.execute('SELECT '+cols+' FROM '+table+' ORDER BY '+order):
            h.update(json.dumps(row,ensure_ascii=False,separators=(',',':')).encode()+b'\n');count+=1
        tables[table]={'rows':count,'sha256':h.hexdigest()}
expected=json.loads((repo/'validation/drawing-enhancement-20261107/release-receipt.json').read_text())['original_data_unchanged']
assert tables==expected,'Original business state changed; investigate without overwrite'
source=root/'ui-data/runs/run_67c5ec574f004a509b6df2c07b04a856'
original=json.loads((source/'manifest.json').read_text())
for name in ['input/model.idf','input/weather.epw','output/eplusout.sql','result.json']:
    assert digest(source/name)==original['artifact_hashes'][name]
record={'native_output_inventory':inventory,'original_business_tables':tables,'isolated_stale_run_artifacts_unchanged':True,
        'screenshot_created':(root/'output/playwright/hourly-desktop-v1.png').exists(),
        'browser_limitations':{'register_helper':'Account created; helper then waited for wrong button name and timed out. Actual snapshot verified login; no repeated registration.',
          'mouse_click':'Timeout waiting for reference button visible/enabled/stable; keyboard Enter succeeded.',
          'screenshot':'Timeout 5000ms taking page screenshot after fonts loaded; no screenshot claimed.'}}
with (out/'source-preservation-v1.json').open('x',encoding='utf-8') as f:json.dump(record,f,ensure_ascii=False,indent=2)
print(json.dumps({'native_cases':len(inventory),'original_records':tables['records']['rows'],'original_jobs':tables['jobs']['rows'],'screenshot_created':record['screenshot_created']}))
