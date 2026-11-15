import hashlib
import json
import shutil
from pathlib import Path
root=Path(__file__).parent
repo=Path('C:/Users/18483/AppData/Local/Temp/vra-timestep-reliability-20261108')
before=root/'runtime-source-first'
assert not before.exists()
shutil.copytree(repo/'backend',before/'backend',ignore=shutil.ignore_patterns('__pycache__'))
receipt=json.loads((root/'model-first/receipt.json').read_text(encoding='utf-8'))
for name,expected in receipt['product_sha256'].items():
 assert hashlib.sha256((before/'backend'/name).read_bytes()).hexdigest()==expected,name

p=repo/'backend/agent.py';text=p.read_text(encoding='utf-8')
old="""                            if ds.kind in agent_energy.KINDS:
                                observed = {**observed, 'explanation_facts': [f for f in observed.get('explanation_facts', [])
                                    if f['fact'] in (observed.get('selected_energy_fact_keys') or [])]}"""
new="""                            if ds.kind in agent_energy.KINDS or 'selected_fact_keys' in observed:
                                observed = {**observed, 'explanation_facts': model_projection(observed, ds.kind)['explanation_facts']}"""
assert text.count(old)==1;p.write_text(text.replace(old,new),encoding='utf-8')
p=repo/'backend/agent_metric_reads.py';text=p.read_text(encoding='utf-8')
text=text.replace('from . import core, agent_energy, agent_outputs','from . import core, agent_energy, agent_outputs, agent_intent_catalog')
old="    current=state(record,ident);keys=current['keys']\n    if not keys:return"
new="    current=state(record,ident);keys=current['keys']\n    meanings=agent_intent_catalog.MEANINGS.get(ident.split('_',1)[0], {})\n    if not keys:return"
assert text.count(old)==1;text=text.replace(old,new)
old="Catalog-only repetition makes no progress.'}"
new="Catalog-only repetition makes no progress. Field meanings: ' + '; '.join(k + '=' + meanings.get(k,k) for k in keys)}"
assert text.count(old)==1;p.write_text(text.replace(old,new),encoding='utf-8')
print('Preserved first model runtime hashes; fixed projected tool availability and pre-read metric meanings')
