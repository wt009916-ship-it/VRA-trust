"""Conservative source-accounting prototype; not semantic correctness proof.
Unaccounted original quantities force clarification. No automatic exclusion.
Not imported by either completed model run.
"""
import copy
from source_catalog import catalog

def guard(text,review):
 result=copy.deepcopy(review)
 if result['outcome']!='draft':return result
 source=catalog(text);known={a.ref:a for a in source.atoms};used=set()
 for task in result['tasks']:
  if task['source_sha256']!=source.source_sha256:raise ValueError('Source changed after proposal')
  for value in task['sources'].values():
   atom=known.get(value['ref'])
   if atom is None or any(value[k]!=getattr(atom,k) for k in ('start','end','quote','dimension','value')):raise ValueError('Source binding altered')
   used.add(atom.ref)
 purpose=[a for a in source.atoms if a.dimension=='purpose_mention']
 missing=[a for a in source.atoms if a.ref not in used and a.dimension!='purpose_mention']
 result['coverage']={'all_source_atoms_accounted':not missing,'nonparameter_purpose_mentions':[{'ref':a.ref,'quote':a.quote,'start':a.start,'end':a.end,'classification':'Explicit applicability-check purpose; not an asserted premise'} for a in purpose],'unaccounted':[{'ref':a.ref,'quote':a.quote,'start':a.start,'end':a.end,'dimension':a.dimension,'context':a.context} for a in missing],
 'semantics_verified':False,'notice':'来源覆盖不证明字段归属、否定/条件理解或工程适用性；历史/附件中的数值也不自动忽略。'}
 if missing:
  result.update(outcome='clarify',issue='unaccounted_source',proposed_tasks=result['tasks'],tasks=[],guard='Original input contains unaccounted quantities/assumptions; review their role before calculation')
 return result
