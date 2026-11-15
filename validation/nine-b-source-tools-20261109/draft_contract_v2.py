"""Post-screen contract hardening prototype; not used by the frozen23 calls.
Complete proposals cannot contain null placeholders. Explicit opposite film labels
cannot bind to one another. Unrecognized prose remains semantically unverified.
"""
import copy,re
from jsonschema import Draft202012Validator
import tool_protocol as original
from source_catalog import catalog,strict_json
from coverage_guard import guard as coverage_guard

TAIL=r'\s*(?:均为|均|为|是|[:：=])?\s*$'
LABEL=r'(?:表面|侧)?(?:膜(?:热阻)?|热阻)'
def film_roles(text,atom):
 prefix=text[max(0,atom.start-120):atom.start]
 if re.search(r'内外'+LABEL+TAIL,prefix,re.I):return {'rsi','rse'}
 if re.search(r'(?:R_?si|内'+LABEL+r')'+TAIL,prefix,re.I):return {'rsi'}
 if re.search(r'(?:R_?se|(?<!内)外'+LABEL+r')'+TAIL,prefix,re.I):return {'rse'}
 return None

def tools(text):
 specs=copy.deepcopy(original.tools(text));c=catalog(text);atoms={a.ref:a for a in c.atoms}
 proposal=specs[0]['function']['parameters'];items=proposal['properties']['tasks']['items']['anyOf'];accepted=[]
 def nonnull(node):
  if isinstance(node,dict):
   if 'enum' in node:node['enum']=[v for v in node['enum'] if v is not None]
   for value in node.values():nonnull(value)
  elif isinstance(node,list):
   for value in node:nonnull(value)
 def has_empty_enum(node):
  if isinstance(node,dict):return ('enum' in node and not node['enum']) or any(has_empty_enum(v) for v in node.values())
  if isinstance(node,list):return any(has_empty_enum(v) for v in node)
  return False
 for branch in items:
  nonnull(branch)
  if branch['properties']['kind']['const']=='thermal':
   for field in ('rsi','rse'):
    ref=branch['properties'][field+'_ref'];ref['enum']=[key for key in ref['enum'] if film_roles(text,atoms[key]) is None or field in film_roles(text,atoms[key])]
  if not has_empty_enum(branch):accepted.append(branch)
 if accepted:proposal['properties']['tasks']['items']['anyOf']=accepted
 else:specs=specs[1:]
 return specs

def guard_roles(text,result):
 checked=copy.deepcopy(result)
 if checked['outcome']!='draft':return checked
 source=catalog(text);atoms={a.ref:a for a in source.atoms};issues=[]
 for ti,task in enumerate(checked['tasks']):
  if task['source_sha256']!=source.source_sha256:raise ValueError('Source revision changed')
  if task['kind']!='thermal':continue
  refs=task['sources']
  for field in ('rsi','rse'):
   a=atoms[refs[field]['ref']];roles=film_roles(text,a)
   if roles is not None and field not in roles:issues.append({'task':ti,'field':field,'ref':a.ref,'explicit_roles':sorted(roles)})
  layers=len([k for k in refs if k.endswith('.thickness')]);triples=[tuple(refs[f'layers.{i}.{key}']['ref'] for key in ('thickness','conductivity','correction')) for i in range(layers)]
  if len(triples)!=len(set(triples)):issues.append({'task':ti,'field':'layers','reason':'Repeated complete source triple requires explicit multiplicity review'})
 checked['role_guard']={'issues':issues,'scope':'Explicit film labels and repeated full layer references only','semantics_verified':False}
 if issues:checked.update(outcome='clarify',issue='source_role_mismatch',proposed_tasks=checked['tasks'],tasks=[],guard='Explicit source roles conflict or a complete layer source is repeated; review before calculation')
 return checked

def decode(text,message):
 calls=message.get('tool_calls')
 if not isinstance(calls,list) or len(calls)!=1:raise ValueError('Exactly one non-writing tool is required')
 fn=calls[0].get('function',{});definition=next((s['function'] for s in tools(text) if s['function']['name']==fn.get('name')),None)
 if definition is None:raise ValueError('Tool is unavailable for these source dimensions')
 args=strict_json(fn['arguments']);Draft202012Validator(definition['parameters']).validate(args)
 return guard_roles(text,coverage_guard(text,original.decode(text,message)))
