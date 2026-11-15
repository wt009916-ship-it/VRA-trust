import math,json
from pathlib import Path
root=Path(__file__).parent
repo=Path('C:/Users/18483/AppData/Local/Temp/vra-timestep-reliability-20261108')
reference={'method':'analytic pi annulus/core, frozen before first curved-partition execution',
 'expected_m3':[math.pi*(.3**2-.27**2)*4,math.pi*.27**2*4],'relative_tolerance':.005,'absolute_tolerance_m3':1e-8}
path=root/'curved-reference-frozen.json';assert not path.exists();path.write_text(json.dumps(reference,indent=2)+'\n')
with (repo/'tests/test_ifc_composite_materials.py').open('a',encoding='utf-8') as f:f.write((root/'additional_tests.py').read_text())
