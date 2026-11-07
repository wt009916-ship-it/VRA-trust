import hashlib,json,tempfile,urllib.request
from pathlib import Path
root=Path(tempfile.mkdtemp(prefix='vra-sizing-source-'));records=[]
for filename in ('ReportSizingManager.cc','SizingManager.cc'):
 url='https://raw.githubusercontent.com/NatLabRockies/EnergyPlus/v9.0.1/src/EnergyPlus/'+filename
 with urllib.request.urlopen(url,timeout=30) as response:raw=response.read(5000001)
 assert len(raw)<5000001
 path=root/filename;path.write_bytes(raw)
 records.append({'path':str(path),'url':url,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
with (Path(__file__).parent/'sizing-source-v1.json').open('x',encoding='utf-8') as stream:json.dump(records,stream,indent=2)
print(json.dumps(records))
