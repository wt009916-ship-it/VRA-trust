"""Next-batch evidence only: copies of a public EPW, no simulation or repair."""
import csv,hashlib,json,sys,tempfile,uuid
from pathlib import Path
repo=Path.cwd();out=Path(__file__).resolve().parent;sys.path.insert(0,str(repo))
from backend.input_validation import validate_epw
from backend.private_storage import private_mkdir
root=private_mkdir(Path(tempfile.gettempdir())/('vra-climate-preflight-'+uuid.uuid4().hex))
source=repo/'fixtures/demo/reference_5zone/weather.epw'
original_hash=hashlib.sha256(source.read_bytes()).hexdigest()
with source.open(encoding='utf-8-sig',newline='') as stream:original=list(csv.reader(stream))
cases=[('control',None,None,None),('dry_bulb_missing',8,6,'99.9'),('humidity_missing',8,8,'999'),
       ('pressure_negative',8,9,'-1'),('direct_solar_nan',8,14,'NaN'),('latitude_invalid',0,6,'900')]
results=[]
for name,row,column,value in cases:
 rows=[r[:] for r in original]
 if row is not None:rows[row][column]=value
 path=root/(name+'.epw')
 with path.open('x',encoding='utf-8',newline='') as stream:csv.writer(stream).writerows(rows)
 try:validate_epw(path);status='accepted';error=None
 except ValueError as exc:status='rejected';error=str(exc)
 results.append({'case':name,'row_zero_based':row,'column_zero_based':column,'value':value,
                 'status':status,'error':error,'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
assert hashlib.sha256(source.read_bytes()).hexdigest()==original_hash
record={'application_commit':'7496491f998145fb02de2b32517739955b8bb1f4','source_sha256':original_hash,
        'scope':'Direct EPW preflight only; no EnergyPlus calls, no API claim, no building data, original preserved.',
        'reference':'https://bigladdersoftware.com/epx/docs/9-0/auxiliary-programs/energyplus-weather-file-epw-data-dictionary.html',
        'cases':results}
with (out/'preflight-probe.json').open('x',encoding='utf-8') as stream:json.dump(record,stream,indent=2)
print(json.dumps({'cases':[{'case':r['case'],'status':r['status']} for r in results],'scope':record['scope']}))
