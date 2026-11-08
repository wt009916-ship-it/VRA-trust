"""New annotated source-location oracle; annotations never enter model requests."""
import re,json,hashlib
from fractions import Fraction as F
from pathlib import Path
from source_catalog import catalog
import position_protocol as protocol
ROOT=Path(__file__).resolve().parent

def wall(rsi,rse,layers):
 vals={'rsi':str(rsi),'rse':str(rse)}
 for i,(d,k,c) in enumerate(layers):vals.update({f'layers.{i}.thickness':str(d),f'layers.{i}.conductivity':str(k),f'layers.{i}.correction':str(c)})
 r=F(str(rsi))+F(str(rse))+sum(F(str(d))/(F(str(k))*F(str(c))) for d,k,c in layers)
 return {'kind':'thermal','values':vals,'status':'calculated','oracle':{'total_resistance_m2k_w':str(r),'u_w_m2k':str(1/r)}}
def beam(s,L,b,h,E,P,a,limited=False):
 vals={k:str(v) for k,v in dict(span=L,width=b,depth=h,modulus=E,force=P,position=a).items()};vals.update(support=s,no_self_weight='no_self_weight',linear_elastic='linear_elastic',small_deflection='small_deflection')
 L,b,h,E,P,a=[F(str(x)) for x in [L,b,h,E,P,a]];I=b*h**3/12
 if s=='cantilever':m=P*a;delta=P*a*a*(3*L-a)/(6*E*I)
 else:assert a==L/2;m=P*L/4;delta=P*L**3/(48*E*I)
 return {'kind':'beam','values':vals,'status':'outside_model_screen' if limited else 'calculated','oracle':{'max_abs_moment_nm':str(m),'max_deflection_m':str(delta)}}
CASES=[]
def add(i,annotated,tasks=None,outcome='draft',issues=None):
 parts=[];last=0;spans={}
 for m in re.finditer(r'\[([^|]+)\|([^]]+)\]',annotated):
  parts.append(annotated[last:m.start()]);start=sum(map(len,parts));parts.append(m.group(2))
  for key in m.group(1).split('&'):spans[key]=(start,start+len(m.group(2)))
  last=m.end()
 parts.append(annotated[last:]);text=''.join(parts);c=catalog(text);tasks=tasks or []
 for ti,t in enumerate(tasks):
  refs={}
  for key,value in t['values'].items():
   a,b=spans[f'{ti}:{key}'];matches=[atom for atom in c.atoms if atom.start==a and atom.end==b]
   assert len(matches)==1,(i,key,a,b)
   atom=matches[0]
   if key in {'support','no_self_weight','linear_elastic','small_deflection'}:assert value==atom.value
   else:assert F(value)==F(atom.value),(i,key,value,atom)
   refs[key]=atom.ref
  t['refs']=refs
 data={'outcome':outcome,'issue':None,'tasks':[]}
 for t in tasks:
  r=t['refs']
  if t['kind']=='thermal':
   n=len([k for k in r if k.endswith('.thickness')]);data['tasks'].append({'kind':'thermal','layers':[{k+'_ref':r[f'layers.{j}.{k}'] for k in ['thickness','conductivity','correction']} for j in range(n)],'rsi_ref':r['rsi'],'rse_ref':r['rse']})
  else:data['tasks'].append({'kind':'beam',**{k+'_ref':v for k,v in r.items()}})
 if tasks:
  _,verified=protocol.verify(text,data);calcs=protocol.calculate(verified)
  for t,r in zip(tasks,calcs):
   assert r['status']==t['status'],(i,'preflight applicability mismatch',r)
   assert all(abs(float(r['metrics'][k])-float(F(v)))<=max(1e-9,abs(float(F(v)))*1e-8) for k,v in t['oracle'].items()),(i,'preflight formula mismatch')
   if t['status']=='outside_model_screen':assert r['limitations']
 CASES.append({'id':f'S{i:02}','message':text,'expected':{'outcome':outcome,'allowed_issues':issues or [None],'tasks':tasks},'gold_draft':data if tasks else None,'preflight': 'independent values, exact positions, arithmetic and applicability checked' if tasks else 'abstention/no calculation required'})
