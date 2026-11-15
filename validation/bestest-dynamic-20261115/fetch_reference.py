"""Read-only public reference acquisition; no downloaded code is executed."""
import hashlib,json,urllib.parse,urllib.request
from pathlib import Path
BASE=Path(__file__).parent
SHA='5891243a6b0dd2d32e0e9a3274caee3921595ac7'
cases=['600','610','620','630','640','650','900','910','920','930','940','950','960','600FF','650FF','900FF','950FF']
paths=['ASHRAE140-Envelope/Inputs/Case'+c+'.idf' for c in cases]+[
 'WeatherData/DRYCOLDTMY.epw','ASHRAE140-Envelope/BESTEST Comparison with Reference Results.xlsx',
 'ASHRAE140-Envelope/Sec5-2out-Part 1 Results and Bar Charts-Cases 600 thru 900.xlsx',
 'ASHRAE140-Envelope/Sec5-2out-Part 2 Results and Bar Charts-Basic Tests.xlsx',
 'ASHRAE140-Envelope/Report/ASHRAE140-Envelope.md','epsim.py','CMakeLists.txt']
out=BASE/'public-reference';out.mkdir(exist_ok=False)
receipt={'repository':'NatLabRockies/EnergyPlusValidationReports','commit':SHA,'cases_fixed_before_run':cases,'files':[],
 'redistribution':'Originals local only; no repository license established. Public reference analysis, not model training.'}
for path in paths:
    url='https://raw.githubusercontent.com/NatLabRockies/EnergyPlusValidationReports/'+SHA+'/'+urllib.parse.quote(path)
    request=urllib.request.Request(url,headers={'User-Agent':'VRA-Trust-reference-audit'})
    with urllib.request.urlopen(request,timeout=60) as response:data=response.read(8*1024**2+1)
    assert len(data)<=8*1024**2
    target=out/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    receipt['files'].append({'path':path,'url':url,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
    (BASE/'acquisition.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps({'downloaded':len(receipt['files']),'bytes':sum(x['bytes'] for x in receipt['files']),'cases':cases}))
