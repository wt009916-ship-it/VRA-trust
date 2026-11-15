"""Explicit source-field compatibility mapping, not a general IDF converter."""
import hashlib,json,re
from pathlib import Path
BASE=Path(__file__).parent
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
frozen=json.loads((BASE/'reference-frozen-v2.json').read_text())
dest=BASE/'frozen-inputs-v3';dest.mkdir(exist_ok=False)
receipt={'reference_sha256':sha(BASE/'reference-frozen-v2.json'),'script_sha256':sha(__file__),
 'schema_sources':{str(p):sha(p) for p in [Path('F:/EnergyPlusV9-0-1/PreProcess/IDFVersionUpdater/V8-3-0-Energy+.idd'),Path('F:/EnergyPlusV9-0-1/Energy+.idd')]},
 'scope':'Four observed legacy object layouts match8.3 IDD fields; original Version is a placeholder, not a verified engine version. Manual named-field mapping for these fixed public files only; no physical parameter tuning.',
 'cases':[]}
for case in frozen['cases']:
    original=BASE/'public-reference/ASHRAE140-Envelope/Inputs'/('Case'+case['case']+'.idf');assert sha(original)==case['source_sha256']
    text=original.read_text(encoding='utf-8-sig');objects=[[v.strip() for v in p.split(',')] for p in re.sub(r'!.*','',text).split(';') if p.strip()]
    changed=[];final=[]
    for obj in objects:
        old=obj.copy();kind=obj[0].lower()
        if kind=='version':
            assert obj[1:]==['.'];obj[1]='9.0'
        elif kind=='runperiod':
            assert len(obj)<=15
            fields=obj[1:]+['']*(14-(len(obj)-1));assert all(v=='' for v in fields[11:]),fields
            # New year slots blank; preserve month/day, start weekday and weather flags.
            obj=[obj[0],*fields[:3],'',*fields[3:5],'',*fields[5:11],'No']
        elif kind=='fenestrationsurface:detailed':
            assert obj[7]=='' and int(obj[10]) in [3,4] and len(obj)==11+3*int(obj[10]),obj
            obj=obj[:7]+obj[8:]  # Only the empty removed Shading Control Name field.
        elif kind=='otherequipment':
            assert len(obj)==11 and obj[4].lower()=='equipmentlevel'
            obj=obj[:2]+['None']+obj[2:]  # Previously unmetered heat gain, not purchased electricity.
        elif kind=='zonehvac:equipmentlist':
            assert len(obj)==6 and obj[2].lower()=='zonehvac:idealloadsairsystem'
            obj=obj[:2]+['SequentialLoad']+obj[2:]  # Exactly one system; same old allocation.
        if obj!=old:changed.append({'object_type':old[0],'name':old[1],'before':old,'after':obj})
        final.append(obj)
    assert sum(o[0].lower()=='version' for o in objects)==1
    assert not any(o[0].lower() in ['output:sqlite','output:table:summaryreports'] for o in objects)
    final.extend([['Output:SQLite','SimpleAndTabular'],['Output:Table:SummaryReports','AllSummary']])
    for variable in ['Zone Air Temperature','Zone Air System Sensible Heating Rate','Zone Air System Sensible Cooling Rate']:
        final.append(['Output:Variable','*',variable,'Hourly'])
    path=dest/('Case'+case['case']+'.idf');path.write_text('\n'.join(','.join(o)+';' for o in final)+'\n',encoding='ascii')
    receipt['cases'].append({'case':case['case'],'source_sha256':sha(original),'path':str(path),'derived_sha256':sha(path),'field_mapping':changed,
      'untouched_object_count':len(objects)-len(changed),'added_objects':final[len(objects):]})
(BASE/'input-preparation-v3.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps({'cases':len(receipt['cases']),'input_directory':str(dest),'physical_parameter_changes':False,'reference_sha256':receipt['reference_sha256']}))
