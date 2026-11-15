"""Transcribed public physical dimensions and reference values; no solver import."""
import hashlib
import json
from pathlib import Path

out = Path(__file__).resolve().parent
regions = []
for name, x0, x1, y0, y1, k in [
    ('Concrete', 0., 500., 41.5, 47.5, 1.15),
    ('Wood', 0., 15., 36.5, 41.5, .12),
    ('Insulation right', 15., 500., 1.5, 41.5, .029),
    ('Insulation left', 1.5, 15., 1.5, 35., .029),
    ('Aluminium vertical', 0., 1.5, 1.5, 36.5, 230.),
    ('Aluminium upper', 1.5, 15., 35., 36.5, 230.),
    ('Aluminium lower', 0., 500., 0., 1.5, 230.),
]:
    regions.append(dict(name=name, x0=x0, x1=x1, y0=y0, y1=y1, conductivity=k,
                        conductivity_unit='W/(m K)', source='Fraunhofer WUFI public thermal benchmark, fixed transcribed geometry'))
assert sum((r['x1'] - r['x0']) * (r['y1'] - r['y0']) for r in regions) == 500 * 47.5
points = [('A', 0., 47.5, 7.1), ('B', 500., 47.5, .8), ('C', 0., 41.5, 7.9),
          ('D', 15., 41.5, 6.3), ('E', 500., 41.5, .8), ('F', 0., 36.5, 16.4),
          ('G', 15., 36.5, 16.3), ('H', 0., 0., 16.8), ('I', 500., 0., 18.3)]
adiabatic = {'mode': 'adiabatic', 'basis': 'Public benchmark insulated cut boundary'}
body = {'name': 'Public heterogeneous reference', 'width': 500., 'height': 47.5, 'length_unit': 'mm',
        'geometry_source': 'WUFI public benchmark case2. Coordinates transcribed with H=(0,0); AB=500, AC=6, CF=5, CD=15, EM=40, aluminium=1.5 mm.',
        'application': 'Independent numerical reference only; not a real building or certification', 'regions': regions,
        'boundaries': {'left': adiabatic, 'right': adiabatic,
                       'bottom': {'mode': 'film', 'temperature_c': 20., 'resistance_m2k_w': .11, 'basis': 'Public reference internal air film'},
                       'top': {'mode': 'film', 'temperature_c': 0., 'resistance_m2k_w': .06, 'basis': 'Public reference external air film'}},
        'cell_size': 2., 'probes': [{'name': n, 'x': x, 'y': y} for n, x, y, _ in points]}
frozen = {'source': 'https://wufi.de/en/two-dimensional-test-cases-of-iso-10211/',
          'reference_figure': 'https://wufi.de/en/wp-content/uploads/sites/11/2015/04/500x173_WUFI-2D-Benchmark2.jpg',
          'expected': {'temperature_c': {n: t for n, _, _, t in points}, 'absolute_temperature_tolerance_k': .1,
                       'heat_w_per_m': 9.5, 'absolute_heat_tolerance_w_per_m': .1}, 'input': body,
          'frozen_before_first_composite_solver_run': True,
          'scope': 'Public benchmark physical data, not a reproduction of a complete standard or an independent certification.',
          'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
p = out / 'composite-reference-frozen.json'
assert not p.exists()
p.write_text(json.dumps(frozen, indent=2) + '\n', encoding='utf-8')
print(hashlib.sha256(p.read_bytes()).hexdigest())
