from pathlib import Path
import json,math
from decimal import Decimal
import ezdxf
root=Path('C:/Users/18483/AppData/Local/Temp/vra-acadsharp-probe-20261108/screen')
frozen=json.loads(Path('C:/Users/18483/AppData/Local/Temp/vra-libredwg-014-reference-20261108/decode-reference/frozen.json').read_text())
def close(a,b):
    v=Decimal(b);return abs(Decimal(str(a))-v)<=Decimal(5).scaleb(v.as_tuple().exponent-1)+Decimal('1e-9')
results=[]
for c in frozen['cases']:
    d=ezdxf.readfile(root/c['id']/'output.dxf');e=d.entitydb[c['handle']]
    checks={'type':e.dxftype()=={'Line':'LINE','circle':'CIRCLE','Text':'MTEXT'}[c['kind']]}
    for k,v in c['properties'].items():
        if k=='Length (RO)':a=(e.dxf.end-e.dxf.start).magnitude
        elif k=='Area':a=math.pi*e.dxf.radius**2
        else:a=getattr(e.dxf,{'StartPoint':'start','EndPoint':'end','Center':'center','Radius':'radius','InsertionPoint':'insert','TextString':'text'}[k])
        checks[k]=all(close(x,y) for x,y in zip(a,v.strip('()').split(),strict=True)) if v.startswith('(') else a==v.strip('"') if v.startswith('"') else close(a,v)
    results.append({'case':c['id'],'checks':checks,'pass':all(checks.values())})
(root/'reference-check.json').write_text(json.dumps({'criteria':frozen['numeric_tolerance'],'same_frozen_references':True,'results':results},indent=2))
print(json.dumps({'cases':len(results),'pass':sum(r['pass'] for r in results)}))
