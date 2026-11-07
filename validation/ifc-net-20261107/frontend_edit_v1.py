import json
from pathlib import Path
data=json.loads(Path('validation/ifc-net-20261107/frontend-edit-v1.json').read_text(encoding='utf-8'))
p=Path('frontend/src/ifc-ui.js');s=p.read_text(encoding='utf-8')
s=s.replace("const labels={measured_mesh:","const labels={ambiguous_opening_relationships:'开洞关系有歧义，几何量未知',measured_mesh:")
needle='export function ifcObjectMarkup(product,geometry){'
assert s.count(needle)==1
s=s.replace(needle,data['helper']+needle).replace('${topologyMarkup(geometry?.topology)}','${openingMarkup(geometry)}${topologyMarkup(geometry?.topology)}')
p.write_text(s,encoding='utf-8',newline='\n')
Path('frontend/tests/ifc-opening-ui.test.js').write_text(data['tests'],encoding='utf-8',newline='\n')
