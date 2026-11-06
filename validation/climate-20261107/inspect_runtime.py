"""Read-only original-data and owned-process checks; never emit credentials."""
import hashlib,json,sqlite3,subprocess,sys,urllib.request
from pathlib import Path
repo=Path.cwd();out=repo/'validation/climate-20261107';phase=sys.argv[1]
assert phase in {'before','after'}
r=json.loads((out/'browser-runtime-v2.json').read_text(encoding='utf-8'));assert r['stopped'];ids=[r['pid']]
cmd='$owned=@('+','.join(map(str,ids))+'); $p=@(Get-CimInstance Win32_Process | Where-Object {$_.ProcessId -in $owned} | Select-Object ProcessId,Name); $l=@(Get-NetTCPConnection -LocalPort 18773,18774 -State Listen -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort,OwningProcess); @{processes=$p;listeners=$l} | ConvertTo-Json -Compress'
observed=json.loads(subprocess.check_output(['powershell.exe','-NoProfile','-NonInteractive','-Command',cmd],creationflags=subprocess.CREATE_NO_WINDOW))
assert not observed['processes'] and not observed['listeners'],observed
db=repo/'validation/thermal-20261104/ui-runtime/vra.sqlite3';checks={};active=[]
with sqlite3.connect('file:'+db.as_posix()+'?mode=ro',uri=True) as con:
 for table,columns in [('records','kind,id,revision,project_id,body'),('jobs','id,project_id,state,body,error')]:
  h=hashlib.sha256();count=0
  for row in con.execute('SELECT '+columns+' FROM '+table+' ORDER BY '+('kind,id,revision' if table=='records' else 'id')):
   h.update(json.dumps(row,ensure_ascii=False,separators=(',',':')).encode()+b'\n');count+=1
  checks[table]={'rows':count,'sha256':h.hexdigest()}
 active_jobs=con.execute("SELECT count(*) FROM jobs WHERE state IN ('queued','running')").fetchone()[0]
 for kind,body in con.execute("SELECT kind,body FROM records r WHERE kind IN ('agent','search') AND revision=(SELECT MAX(revision) FROM records s WHERE s.kind=r.kind AND s.id=r.id)"):
  if json.loads(body).get('status') in {'queued','running'}:active.append(kind)
assert not active_jobs and not active,'Original active tasks must finish before restart'
if phase=='after':assert checks==json.loads((out/'runtime-before.json').read_text(encoding='utf-8'))['original_tables']
with urllib.request.urlopen('http://127.0.0.1:18772/api/health',timeout=5) as r:health=json.load(r)
assert health['status']=='ok' and health['worker_alive'] and health['engine_available'] and not health['demo_mode']
record={'phase':phase,'owned_test_processes_absent':True,'test_ports_released':True,'original_tables':checks,'active_original_tasks':0,'health':health}
with (out/f'runtime-{phase}.json').open('x',encoding='utf-8',newline='\n') as f:json.dump(record,f,indent=2)
print(json.dumps(record))
