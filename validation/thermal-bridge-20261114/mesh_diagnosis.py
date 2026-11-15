import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, 'C:/Users/18483/AppData/Local/Temp/vra-timestep-reliability-20261108')
from backend import thermal_bridge_solver as solver
from backend.thermal_bridge import Section, calculate, normalize

out = Path(__file__).parent
reference = json.loads((out / 'composite-reference-frozen.json').read_text())
body = reference['input']
data = normalize(Section(**body))
coarse = solver.solve(data, .002, time.monotonic() + 25)
fine = solver.solve(data, .001, time.monotonic() + 25)
intermediate = np.array([np.interp(coarse['x'], fine['x'], row) for row in fine['temperature']])
sample = np.array([np.interp(coarse['y'], fine['y'], column) for column in intermediate.T]).T
iy, ix = np.unravel_index(np.abs(sample - coarse['temperature']).argmax(), sample.shape)
print(json.dumps({'original_max_difference': {'x_m': coarse['x'][ix], 'y_m': coarse['y'][iy],
    'coarse_c': coarse['temperature'][iy, ix], 'fine_c': sample[iy, ix], 'k': coarse['conductivity'][iy, ix]}}))
# Isolated capacity experiment, not a product configuration or acceptance override.
solver.MAX_CELLS = 160000
body['cell_size'] = 1.
start = time.monotonic()
try:
    result = calculate(Section(**body))
    evidence = {'experimental_cell_cap': 160000, 'input': body, 'seconds': time.monotonic() - start, 'result': result}
except Exception as exc:
    evidence = {'experimental_cell_cap': 160000, 'input': body, 'seconds': time.monotonic() - start, 'error': str(exc)}
target = out / 'composite-refinement-experiment.json'
assert not target.exists()
target.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({k: v for k, v in evidence.items() if k not in ('input', 'result')}))
if 'result' in evidence:
    print(json.dumps({k: result[k] for k in ('status', 'mesh_check', 'linear_solver', 'probes', 'boundary_heat_into_domain_w_per_m')}))
