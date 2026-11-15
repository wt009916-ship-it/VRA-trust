import json,re
from pathlib import Path
BASE=Path(__file__).parent
def idd(path):
    text=path.read_text(errors='replace');matches=list(re.finditer(r'(?m)^([A-Za-z][A-Za-z0-9:_-]+),\s*$',text));result={}
    for index,match in enumerate(matches):
        block=text[match.end():matches[index+1].start() if index+1<len(matches) else len(text)]
        result[match[1].lower()]=re.findall(r'\\field ([^\r\n]+)',block)
    return result
old=idd(Path('F:/EnergyPlusV9-0-1/PreProcess/IDFVersionUpdater/V8-3-0-Energy+.idd'))
new=idd(Path('F:/EnergyPlusV9-0-1/Energy+.idd'))
types={}
for p in (BASE/'public-reference/ASHRAE140-Envelope/Inputs').glob('*.idf'):
    objects=[[v.strip() for v in o.split(',')] for o in re.sub(r'!.*','',p.read_text()).split(';') if o.strip()]
    for o in objects:types.setdefault(o[0].lower(),[]).append({'file':p.name,'fields':len(o)-1,'name':o[1] if len(o)>1 else None})
rows={}
for kind,examples in types.items():
    maximum=max(e['fields'] for e in examples)
    a,b=old.get(kind,[])[:maximum],new.get(kind,[])[:maximum]
    if a!=b:rows[kind]={'old_fields':a,'new_fields':b,'sample':examples[0],'maximum_fields':maximum}
(BASE/'schema-audit.json').write_text(json.dumps(rows,indent=2)+'\n')
for k,v in rows.items():print(k,'\n old:',v['old_fields'][:35],'\n new:',v['new_fields'][:35])
