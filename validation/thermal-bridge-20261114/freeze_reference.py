"""Independent analytical expectations, generated before the product solver exists."""
import hashlib
import json
import math
from decimal import Decimal, getcontext
from pathlib import Path

getcontext().prec = 50
out = Path(__file__).resolve().parent


def temperature(x, y, terms):
    # Laplace equation on [0,1] x [0,2], left/bottom zero, top20,
    # right insulated. Odd sine basis satisfies the right Neumann condition.
    values = []
    for n in range(terms):
        wave = (n + .5) * math.pi
        ratio = math.exp(wave * (y - 2)) * (-math.expm1(-2 * wave * y)) / (-math.expm1(-4 * wave))
        values.append(40 / wave * math.sin(wave * x) * ratio)
    return math.fsum(values)


points = []
for row in range(1, 8):
    for col in range(1, 5):
        x, y = col / 4, row / 4
        a, b = temperature(x, y, 1000), temperature(x, y, 2000)
        assert abs(a - b) < 1e-12 and 0 < a < 20
        points.append({'x_m': x, 'y_m': y, 'temperature_c': b})
assert abs(temperature(1, 1, 2000) - 5) < 1e-12
series = Decimal('.12') + Decimal('.16') / Decimal('.8') + Decimal('.06') / Decimal('.04') + Decimal('.05')
cases = {
    'frozen_before_implementation': True,
    'source_scope': 'Independently derived analytical equations. Public WUFI thermal reference used for physical boundary comparison, not standard compliance certification.',
    'source_url': 'https://wufi.de/en/two-dimensional-test-cases-of-iso-10211/',
    'column_temperature': {'width_m': 1, 'height_m': 2, 'conductivity_w_mk': 1,
                           'boundaries': {'left': {'temperature_c': 0}, 'bottom': {'temperature_c': 0},
                                          'top': {'temperature_c': 20}, 'right': {'adiabatic': True}},
                           'oracle': 'sum n>=0: 40/wave*sin(wave*x)*sinh(wave*y)/sinh(2*wave), wave=(n+0.5)*pi',
                           'max_abs_temperature_error_k': .1, 'points': points,
                           'heat_flow_validation': 'NOT_APPLICABLE: discontinuous corner boundary can yield singular total flux; temperature agreement is not a heat-flow convergence claim.'},
    'plane_slab': {'thickness_m': '.24', 'height_m': '1.7', 'conductivity_w_mk': '.8',
                   'inside_c': '23', 'outside_c': '-7', 'rsi_m2k_w': '.12', 'rse_m2k_w': '.05',
                   'q_w_per_m_extension': str(Decimal(30) * Decimal('1.7') / (Decimal('.12') + Decimal('.24') / Decimal('.8') + Decimal('.05'))),
                   'relative_error_limit': 1e-8},
    'series_layers': {'thicknesses_m': ['.16', '.06'], 'conductivities_w_mk': ['.8', '.04'],
                      'height_m': '1.3', 'inside_c': '21', 'outside_c': '-4', 'rsi_m2k_w': '.12', 'rse_m2k_w': '.05',
                      'total_r_m2k_w': str(series), 'q_w_per_m_extension': str(Decimal(25) * Decimal('1.3') / series),
                      'relative_error_limit': 1e-8},
    'parallel_bands': {'thickness_m': '.25', 'heights_m': ['.6', '.4'], 'conductivities_w_mk': ['.2', '1.8'],
                       'left_temperature_c': '20', 'right_temperature_c': '0', 'other_boundaries': 'adiabatic',
                       'q_w_per_m_extension': str(Decimal(20) * (Decimal('.6') * Decimal('.2') + Decimal('.4') * Decimal('1.8')) / Decimal('.25')),
                       'relative_error_limit': 1e-8},
    'mandatory_refusals': ['nonpositive_conductivity', 'nonpositive_dimensions', 'uncovered_material_region',
                          'overlapping_material_assignments', 'all_adiabatic_without_temperature_anchor',
                          'invalid_units', 'nonfinite_input', 'mesh_budget_exceeded'],
    'additional_invariants': ['uniform_temperature_zero_flux', 'maximum_principle', 'energy_balance',
                              'reversed_temperature_difference_reverses_flux', 'grid_refinement_separate_from_iteration_residual'],
    'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
}
target = out / 'analytical-reference-frozen.json'
assert not target.exists(), 'Keep prior frozen oracles'
target.write_text(json.dumps(cases, indent=2) + '\n', encoding='utf-8')
print(json.dumps({'sha256': hashlib.sha256(target.read_bytes()).hexdigest(), 'temperature_points': len(points), 'solver_executed': False, 'score_delta': 0}))
