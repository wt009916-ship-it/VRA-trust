"""Read-only field inventory of bundled public weather; not a validity verdict."""
import csv,hashlib,json,math
from pathlib import Path
out=Path(__file__).resolve().parent;home=Path('F:/EnergyPlusV9-0-1');rows=[]
for p in sorted((home/'WeatherData').glob('*.epw')):
 with p.open(encoding='utf-8-sig',newline='') as stream:data=list(csv.reader(stream))
 fields=[]
 for index in range(6,35):
  values=[];nonfinite=invalid=0
  for r in data[8:]:
   try:value=float(r[index])
   except (ValueError,IndexError):invalid+=1;continue
   if not math.isfinite(value):nonfinite+=1;continue
   values.append(value)
  fields.append({'zero_based_column':index,'finite_count':len(values),'nonfinite_count':nonfinite,'nonnumeric_or_absent_count':invalid,
                 'min_including_sentinels':min(values) if values else None,'max_including_sentinels':max(values) if values else None})
 ddy=p.with_suffix('.ddy')
 rows.append({'name':p.name,'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size,
              'location_header':data[0],'hourly_rows':len(data)-8,'fields':fields,
              'ddy':{'path':str(ddy),'sha256':hashlib.sha256(ddy.read_bytes()).hexdigest(),'bytes':ddy.stat().st_size}})
record={'scope':'Raw read-only field inventory including missing-value sentinels; not a validation or climate classification result.',
        'source':'WeatherData bundled with installed EnergyPlus 9.0.1; pair each EPW with its own DDY.',
        'license_sha256':hashlib.sha256((home/'LICENSE.txt').read_bytes()).hexdigest(),'weather':rows,'engine_calls':0}
with (out/'public-weather-profile.json').open('x',encoding='utf-8') as stream:json.dump(record,stream,indent=2)
print(json.dumps({'files':len(rows),'rows':[{'name':r['name'],'hours':r['hourly_rows']} for r in rows],'engine_calls':0}))
