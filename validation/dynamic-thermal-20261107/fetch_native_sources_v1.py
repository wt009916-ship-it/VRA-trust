import hashlib,json,sys,tempfile,urllib.request,uuid
from pathlib import Path
repo=Path.cwd();out=Path(__file__).resolve().parent;sys.path.insert(0,str(repo))
from backend.private_storage import private_mkdir
root=private_mkdir(Path(tempfile.gettempdir())/('vra-dynamic-sources-'+uuid.uuid4().hex))
rows=[]
for name in ['ZoneTempPredictorCorrector.cc','HeatBalanceAirManager.cc','Psychrometrics.hh','SQLiteProcedures.cc']:
    url='https://raw.githubusercontent.com/NREL/EnergyPlus/v9.0.1/src/EnergyPlus/'+name
    with urllib.request.urlopen(url,timeout=30) as response:
        raw=response.read(3_000_001);assert len(raw)<=3_000_000
    (root/name).write_bytes(raw)
    rows.append({'url':url,'path':str(root/name),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
with (out/'native-sources-v1.json').open('x',encoding='utf-8') as f:json.dump({'root':str(root),'files':rows,'purpose':'Read-only fixed-version upstream source audit; not executed as code.'},f,indent=2)
print(json.dumps({'root':str(root),'files':len(rows)}))
