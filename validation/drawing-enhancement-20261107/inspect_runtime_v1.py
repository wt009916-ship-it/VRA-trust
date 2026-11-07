"""Read-only original business checksums, health and known local test ports; no credentials."""
import hashlib, json, sqlite3, subprocess, sys, urllib.request
from pathlib import Path
repo=Path.cwd(); out=Path(__file__).parent; phase=sys.argv[1]
assert phase in {'before','after'}
for path in out.glob('live-?b-v?.json'):
    row=json.loads(path.read_text(encoding='utf-8')); assert row['server_stopped'],path.name
for name in ('browser-runtime-v1.json','browser-runtime-v2.json','browser-runtime-v3.json'):
    assert json.loads((out/name).read_text())['stopped']
command="$ports=@(Get-NetTCPConnection -LocalPort 18773,18774 -State Listen -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort,OwningProcess); $main=@(Get-NetTCPConnection -LocalPort 18772 -State Listen -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort,OwningProcess); @{test_ports=$ports;prototype=$main} | ConvertTo-Json -Compress"
network=json.loads(subprocess.check_output(['powershell.exe','-NoProfile','-NonInteractive','-Command',command],creationflags=subprocess.CREATE_NO_WINDOW))
assert not network['test_ports'],network
db=repo/'validation/thermal-20261104/ui-runtime/vra.sqlite3'; checks={}; active=[]
with sqlite3.connect('file:'+db.as_posix()+'?mode=ro',uri=True) as con:
    for table,columns in [('records','kind,id,revision,project_id,body'),('jobs','id,project_id,state,body,error')]:
        digest=hashlib.sha256(); count=0
        for row in con.execute('SELECT '+columns+' FROM '+table+' ORDER BY '+('kind,id,revision' if table=='records' else 'id')):
            digest.update(json.dumps(row,ensure_ascii=False,separators=(',',':')).encode()+b'\n');count+=1
        checks[table]={'rows':count,'sha256':digest.hexdigest()}
    assert con.execute("SELECT count(*) FROM jobs WHERE state IN ('queued','running')").fetchone()[0]==0
    for kind,body in con.execute("SELECT kind,body FROM records r WHERE kind IN ('agent','search') AND revision=(SELECT MAX(revision) FROM records s WHERE s.kind=r.kind AND s.id=r.id)"):
        if json.loads(body).get('status') in {'queued','running'}:active.append(kind)
assert not active,'Original task active; do not stop service'
expected=json.loads((repo/'validation/designload-20261107/release-receipt.json').read_text())['original_data_unchanged'] if phase=='before' else json.loads((out/'runtime-before.json').read_text())['original_tables']
assert checks==expected,'Business records changed; preserve and inspect, never overwrite'
with urllib.request.urlopen('http://127.0.0.1:18772/api/health',timeout=5) as response:health=json.load(response)
assert health['status']=='ok' and health['worker_alive'] and health['engine_available'] and not health['demo_mode']
record={'phase':phase,'test_ports_released':True,'active_original_tasks':0,'original_tables':checks,'network':network,'health':health}
with (out/('runtime-'+phase+'.json')).open('x',encoding='utf-8') as handle:json.dump(record,handle,indent=2)
print(json.dumps(record))

