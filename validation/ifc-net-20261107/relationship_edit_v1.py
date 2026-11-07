import json
from pathlib import Path
data=json.loads(Path('validation/ifc-net-20261107/relationship-edit-v1.json').read_text(encoding='utf-8'))
p=Path('backend/ifc_geometry.py');s=p.read_text(encoding='utf-8')
assert s.count('def inspect_shapes(doc, products, length_scale):')==1
s=s.replace('def inspect_shapes(doc, products, length_scale):',data['helper']+'def inspect_shapes(doc, products, length_scale):')
s=s.replace('    topology_budget = mesh_topology.Budget()','    topology_budget = mesh_topology.Budget()\n    relationship_checks = opening_relationships(doc, products)')
s=s.replace("        if not bodies:","        row['opening_relationships'] = relationship_checks[element.id()]\n        if row['opening_relationships']['issues']:\n            row['status'] = 'ambiguous_opening_relationships'\n        elif not bodies:")
p.write_text(s,encoding='utf-8',newline='\n')
p=Path('tests/test_ifc_opening_boolean.py')
p.write_text(p.read_text(encoding='utf-8')+data['test'],encoding='utf-8',newline='\n')
