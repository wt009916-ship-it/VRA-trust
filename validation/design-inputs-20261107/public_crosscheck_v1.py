"""Independent line-oriented field oracle; no claimed physics or source certification."""
import hashlib,json,sys,time
from pathlib import Path
root,out,weather=map(Path,sys.argv[1:])
sys.path.insert(0,str(root))
from backend import design_condition_parser as production
def independent(raw):
    # Independent per-line comment stripping / delimiter state; raw field gold.
    objects=[];fields=[];token=''
    for line in raw.decode('cp1252').splitlines():
        for char in line.split('!',1)[0]+'\n':
            if char in ',;':
                fields.append(token.strip());token=''
                if char==';':objects.append(fields);fields=[]
            else:token+=char
    assert not token.strip() and not fields
    return objects
start=time.perf_counter();rows=[]
for path in sorted(weather.glob('*.ddy')):
    raw=path.read_bytes();gold=independent(raw);actual=production.parse(raw,'cp1252')
    days=[o[1:] for o in gold if o[0].lower()=='sizingperiod:designday']
    sites=[o[1:] for o in gold if o[0].lower()=='site:location']
    assert len(days)==18 and len(sites)==1
    padded=[d+['']*(26-len(d)) for d in days]
    assert [d['fields'] for d in actual['days']]==padded
    assert actual['site']['fields']==sites[0]
    # Explicitly constructed model uses alternate names; mappings are provided.
    model=('Version,9.0;\nSite:Location,'+','.join(sites[0])+';\n'+
        '\n'.join('SizingPeriod:DesignDay,'+','.join(['Model '+str(i)]+d[1:])+';' for i,d in enumerate(padded))).encode()
    pairs=[{'model_day':'Model '+str(i),'source_day':d[0]} for i,d in enumerate(padded)]
    checked=production.compare(production.parse(model,model=True),actual,pairs)
    assert checked['status']=='matching_declared_fields'
    # Independent changed input: +0.1 m/s in first declared day.
    altered=[list(d) for d in padded];altered[0][15]=str(float(altered[0][15])+0.1)
    conflict=('Site:Location,'+','.join(sites[0])+';\n'+'\n'.join('SizingPeriod:DesignDay,'+','.join(d)+';' for d in altered)).encode()
    c=production.compare(production.parse(model,model=True),production.parse(conflict),pairs)
    assert c['status']=='differences_found'
    unequal=[(r['model_day'],f['field']) for r in c['rows'] for f in r['fields'] if not f['equal']]
    assert unequal==[('Model 0','wind_speed')]
    rows.append({'file':path.name,'sha256':hashlib.sha256(raw).hexdigest(),'days':len(days),'raw_fields_matched':len(days)*26+5,
      'explicit_renaming_matches':len(days),'mutated_field_detected':unequal,'source_bytes_preserved':hashlib.sha256(path.read_bytes()).hexdigest()==hashlib.sha256(raw).hexdigest()})
assert len(rows)==5
record={'cases':rows,'elapsed_seconds':time.perf_counter()-start,'assertions_passed':True,
        'limits':'Declared fields only; not EnergyPlus runtime adoption, current standards, design suitability or thermal performance.'}
with out.open('x',encoding='utf-8') as f:json.dump(record,f,ensure_ascii=False,indent=2)
print(json.dumps({'files':len(rows),'design_days':sum(r['days'] for r in rows),'gold_fields':sum(r['raw_fields_matched'] for r in rows),'seconds':record['elapsed_seconds']}))
