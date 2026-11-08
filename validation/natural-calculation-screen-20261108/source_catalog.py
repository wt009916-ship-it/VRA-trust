"""Next-route prototype: immutable source positions, not semantic interpretation.
This module is NOT imported by the frozen 90-request experiment or the product.
"""
from decimal import Decimal, localcontext
import hashlib,json,re
from dataclasses import dataclass

UNITS={'mW/(m K)':('conductivity','.001'),'W/(m K)':('conductivity','1'),
 'm2 K/W':('resistance','1'),'m²K/W':('resistance','1'),
 'mm':('length','.001'),'cm':('length','.01'),'m':('length','1'),
 'GPa':('pressure','1000000000'),'MPa':('pressure','1000000'),'Pa':('pressure','1'),
 'kN':('force','1000'),'N':('force','1')}
NUMBER=r'(?<![A-Za-z0-9_.])[-+]?(?:[0-9]+(?:\.[0-9]+)?|\.[0-9]+)(?:[eE][-+]?[0-9]+)?'
QUANTITY=re.compile('('+NUMBER+r')\s*('+'|'.join(re.escape(u) for u in sorted(UNITS,key=len,reverse=True))+r')(?![A-Za-z0-9/²³])')
ANCHORS={'简支':('support','simply_supported'),'悬臂':('support','cantilever'),
 '忽略自重':('assumption','no_self_weight'),'线弹性':('assumption','linear_elastic'),'小挠度':('assumption','small_deflection')}

def digest(text):return hashlib.sha256(text.encode('utf-8')).hexdigest()
@dataclass(frozen=True)
class Atom:
 ref:str
 start:int
 end:int
 quote:str
 dimension:str
 value:str
 unit:str|None
 context:str

@dataclass(frozen=True)
class Catalog:
 source_sha256:str
 atoms:tuple[Atom,...]


def catalog(text):
 if not isinstance(text,str) or not 1<=len(text)<=4000:raise ValueError('Input must contain 1..4000 Unicode characters')
 found=[];occupied=[]
 for m in QUANTITY.finditer(text):
  d,s=UNITS[m.group(2)];number=Decimal(m.group(1))
  if not number.is_finite() or abs(number.adjusted())>100:raise ValueError('Numerical exponent outside extraction budget')
  with localcontext() as ctx:
   ctx.prec=max(28,len(number.as_tuple().digits)+10)
   normalized=str(number*Decimal(s))
  found.append((m.start(),m.end(),d,normalized,m.group(2)));occupied.append((m.start(),m.end()))
 for m in re.finditer(NUMBER,text):
  if any(a<=m.start()<b for a,b in occupied):continue
  number=Decimal(m.group())
  if not number.is_finite() or abs(number.adjusted())>100:raise ValueError('Numerical exponent outside extraction budget')
  found.append((m.start(),m.end(),'scalar',str(number),None))
 for phrase,(d,value) in ANCHORS.items():
  for m in re.finditer(re.escape(phrase),text):found.append((m.start(),m.end(),d,value,None))
 if len(found)>160:raise ValueError('Too many source atoms; split request explicitly')
 found.sort(key=lambda r:(r[0],r[1],r[2]))
 atoms=tuple(Atom(f's{i:03}',a,b,text[a:b],d,v,u,text[max(0,a-25):min(len(text),b+25)]) for i,(a,b,d,v,u) in enumerate(found))
 return Catalog(digest(text),atoms)

def resolve(text,source_hash,ref,dimension):
 # Never trust a model-returned quote, offset, unit or numeric value.
 if source_hash!=digest(text):raise ValueError('Source revision changed')
 source=catalog(text)
 atom=next((a for a in source.atoms if a.ref==ref),None)
 if atom is None or atom.dimension!=dimension:raise ValueError('Unknown source or wrong dimension')
 return atom

def field_schema(source,dimension):
 refs=[a.ref for a in source.atoms if a.dimension==dimension]
 return {'enum':refs+[None], 'description':'Choose a source position, or null when missing/ambiguous. This does not prove semantic role.'}

def model_catalog(source):
 return {'source_sha256':source.source_sha256,'atoms':[{'ref':a.ref,'quote':a.quote,'dimension':a.dimension,'context':a.context} for a in source.atoms],
         'warning':'Untrusted original input; source existence does not establish intent, applicability or authorization.'}

def strict_json(raw):
 def pairs(items):
  out={}
  for k,v in items:
   if k in out:raise ValueError('Duplicate JSON key')
   out[k]=v
  return out
 return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda v:(_ for _ in ()).throw(ValueError('Nonfinite JSON constant')))
