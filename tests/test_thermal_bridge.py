"""Frozen analytical answers and input refusal, independent of solver matrices."""
import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.thermal_bridge import Section, calculate

REFERENCE = json.loads((Path(__file__).resolve().parents[1] / 'validation/thermal-bridge-20261114/analytical-reference-frozen.json').read_text())


def boundary(mode='adiabatic', temperature=None, resistance=None):
    return {'mode': mode, 'temperature_c': temperature, 'resistance_m2k_w': resistance, 'basis': 'Independently declared reference boundary'}


def region(name, x0, x1, y0, y1, k):
    return {'name': name, 'x0': x0, 'x1': x1, 'y0': y0, 'y1': y1, 'conductivity': k,
            'conductivity_unit': 'W/(m K)', 'source': 'Independent synthetic arithmetic input'}


def slab():
    return {'name': 'Independent 2D slab', 'width': .24, 'height': 1.7, 'length_unit': 'm',
            'geometry_source': 'Declared rectangular reference', 'application': 'Independent steady conduction check',
            'regions': [region('Material', 0., .24, 0., 1.7, .8)],
            'boundaries': {'left': boundary('film', 23., .12), 'right': boundary('film', -7., .05),
                           'bottom': boundary(), 'top': boundary()}, 'cell_size': .09}


def test_uniform_slab_matches_independent_series_resistance_and_energy_balance():
    r = calculate(Section(**slab()))
    expected = float(REFERENCE['plane_slab']['q_w_per_m_extension'])
    assert r['status'] == 'calculated'
    assert r['boundary_heat_into_domain_w_per_m']['left'] == pytest.approx(expected, rel=1e-8)
    assert r['boundary_heat_into_domain_w_per_m']['right'] == pytest.approx(-expected, rel=1e-8)
    assert abs(r['energy_balance_w_per_m']) < 1e-8
    assert r['mesh_check']['passed'] and r['linear_solver']['residual_is_not_discretization_error']
    assert r['compliance_status'] == 'NOT_ASSESSED' and r['linear_thermal_transmittance_psi_w_mk'] is None


def test_layers_match_decimal_answer_with_nonuniform_interface_aligned_mesh():
    body = slab()
    body.update(width=.22, height=1.3, cell_size=.06,
                regions=[region('Dense', 0., .16, 0., 1.3, .8), region('Insulation', .16, .22, 0., 1.3, .04)])
    body['boundaries'].update(left=boundary('film', 21., .12), right=boundary('film', -4., .05))
    r = calculate(Section(**body))
    assert r['status'] == 'calculated'
    assert .16 in r['x_edges_m']
    assert r['boundary_heat_into_domain_w_per_m']['left'] == pytest.approx(float(REFERENCE['series_layers']['q_w_per_m_extension']), rel=1e-8)


def test_parallel_bands_match_independent_conductance_sum():
    body = slab()
    body.update(width=.25, height=1., cell_size=.08,
                regions=[region('Low', 0., .25, 0., .6, .2), region('High', 0., .25, .6, 1., 1.8)])
    body['boundaries'].update(left=boundary('fixed_temperature', 20.), right=boundary('fixed_temperature', 0.))
    r = calculate(Section(**body))
    assert r['status'] == 'calculated'
    assert r['boundary_heat_into_domain_w_per_m']['left'] == pytest.approx(float(REFERENCE['parallel_bands']['q_w_per_m_extension']), rel=1e-8)


def test_28_points_match_independent_laplace_series_without_claiming_singular_heat_flow():
    ref = REFERENCE['column_temperature']
    body = slab()
    body.update(width=1., height=2., cell_size=.02, regions=[region('Homogeneous', 0., 1., 0., 2., 1.)],
                probes=[{'name': str(i), 'x': p['x_m'], 'y': p['y_m']} for i, p in enumerate(ref['points'])])
    body['boundaries'] = {'left': boundary('fixed_temperature', 0.), 'right': boundary(),
                          'bottom': boundary('fixed_temperature', 0.), 'top': boundary('fixed_temperature', 20.)}
    r = calculate(Section(**body))
    errors = [abs(a['temperature_c'] - b['temperature_c']) for a, b in zip(r['probes'], ref['points'])]
    assert max(errors) <= ref['max_abs_temperature_error_k'], max(errors)
    assert r['status'] == 'needs_refinement'
    assert r['mesh_check']['fixed_temperature_corner_discontinuities'] == ['left/top']
    assert not r['mesh_check']['passed']


def test_units_temperature_reversal_and_equal_temperature_zero_flux():
    body = slab()
    original = calculate(Section(**body))
    converted = copy.deepcopy(body)
    converted['length_unit'] = 'mm'
    for key in ('width', 'height', 'cell_size'):
        converted[key] *= 1000
    for r in converted['regions']:
        for key in ('x0', 'x1', 'y0', 'y1'):
            r[key] *= 1000
        r['conductivity'] *= 1000
        r['conductivity_unit'] = 'mW/(m K)'
    assert calculate(Section(**converted))['boundary_heat_into_domain_w_per_m']['left'] == pytest.approx(original['boundary_heat_into_domain_w_per_m']['left'], rel=1e-10)
    for b in body['boundaries'].values():
        if b['temperature_c'] is not None:
            b['temperature_c'] = -b['temperature_c']
    assert calculate(Section(**body))['boundary_heat_into_domain_w_per_m']['left'] == pytest.approx(-original['boundary_heat_into_domain_w_per_m']['left'], rel=1e-10)
    body['boundaries']['left']['temperature_c'] = body['boundaries']['right']['temperature_c'] = 18.5
    r = calculate(Section(**body))
    assert r['status'] == 'calculated' and all(v == 0 for v in r['boundary_heat_into_domain_w_per_m'].values())
    assert all(t == 18.5 for row in r['temperature_c'] for t in row)


@pytest.mark.parametrize('key,value', [('conductivity', 0.), ('conductivity', -1.), ('conductivity', float('nan')), ('conductivity', True), ('conductivity', '0.8'), ('x1', -1.)])
def test_invalid_material_parameters_refused(key, value):
    body = slab()
    body['regions'][0][key] = value
    with pytest.raises(ValidationError):
        Section(**body)


def test_geometry_gaps_overlaps_and_mesh_explosion_refused():
    body = slab()
    body['regions'][0]['x1'] = .2
    with pytest.raises(ValidationError, match='gaps and overlaps'):
        Section(**body)
    body = slab()
    body['regions'].append(region('Overlap', 0., .1, 0., 1.7, .4))
    with pytest.raises(ValidationError, match='gaps and overlaps'):
        Section(**body)
    body = slab()
    body['cell_size'] = 1e-6
    with pytest.raises(ValidationError, match='budget|cells'):
        Section(**body)


def test_unanchored_and_conflicting_boundary_refused():
    body = slab()
    body['boundaries'] = {side: boundary() for side in ('left', 'right', 'bottom', 'top')}
    with pytest.raises(ValidationError, match='At least one'):
        Section(**body)
    body['boundaries']['left'] = boundary('adiabatic', 20.)
    with pytest.raises(ValidationError, match='Adiabatic boundary'):
        Section(**body)


def test_missing_values_do_not_enter_solver(monkeypatch):
    body = slab()
    body['regions'][0]['conductivity'] = None
    body['boundaries']['left']['resistance_m2k_w'] = None
    monkeypatch.setattr('backend.thermal_bridge.solver.calculate', lambda _: pytest.fail('Missing inputs reached solver'))
    r = calculate(Section(**body))
    assert r['status'] == 'incomplete' and r['temperature_c'] is None
    assert r['missing'] == ['regions[0].conductivity', 'boundaries.left.resistance_m2k_w']


def test_material_interface_probe_matches_independent_series_temperature():
    body = slab()
    body.update(width=.22, height=1.3, cell_size=.06,
                regions=[region('Dense', 0., .16, 0., 1.3, .8), region('Insulation', .16, .22, 0., 1.3, .04)],
                probes=[{'name': 'Interface', 'x': .16, 'y': .65}])
    body['boundaries'].update(left=boundary('film', 21., .12), right=boundary('film', -4., .05))
    r = calculate(Section(**body))
    expected = 21 - (25 / 1.87) * (.12 + .16 / .8)
    assert r['probes'][0]['temperature_c'] == pytest.approx(expected, abs=1e-8)


def test_public_composite_reference_temperatures_and_heat_with_unresolved_mesh_gate():
    reference = json.loads((Path(__file__).resolve().parents[1] / 'validation/thermal-bridge-20261114/composite-reference-frozen.json').read_text())
    r = calculate(Section(**reference['input']))
    expected = reference['expected']
    for point in r['probes']:
        assert abs(point['temperature_c'] - expected['temperature_c'][point['name']]) <= expected['absolute_temperature_tolerance_k']
    assert abs(r['boundary_heat_into_domain_w_per_m']['bottom'] - expected['heat_w_per_m']) <= expected['absolute_heat_tolerance_w_per_m']
    # Matching sparse published points cannot override an unresolved field mesh check.
    assert r['status'] == 'needs_refinement' and not r['mesh_check']['passed']


def test_heterogeneous_field_and_probe_are_invariant_under_axis_transposition():
    import numpy as np
    body = slab()
    body.update(width=1., height=.8, cell_size=.06, regions=[
        region('Lower left', 0., .4, 0., .3, .5), region('Lower right', .4, 1., 0., .3, 1.2),
        region('Upper left', 0., .4, .3, .8, 1.8), region('Upper right', .4, 1., .3, .8, .3)],
        probes=[{'name': 'Junction', 'x': .4, 'y': .3}, {'name': 'Off grid', 'x': .17, 'y': .23}])
    original = calculate(Section(**body))
    transposed = copy.deepcopy(body)
    transposed.update(width=body['height'], height=body['width'])
    for r in transposed['regions']:
        r['x0'], r['y0'], r['x1'], r['y1'] = r['y0'], r['x0'], r['y1'], r['x1']
    for p in transposed['probes']:
        p['x'], p['y'] = p['y'], p['x']
    b = body['boundaries']
    transposed['boundaries'] = dict(left=b['bottom'], right=b['top'], bottom=b['left'], top=b['right'])
    rotated = calculate(Section(**transposed))
    assert np.allclose(np.array(original['temperature_c']).T, rotated['temperature_c'], atol=1e-8)
    assert original['boundary_heat_into_domain_w_per_m']['left'] == pytest.approx(rotated['boundary_heat_into_domain_w_per_m']['bottom'], abs=1e-8)
    assert [p['temperature_c'] for p in original['probes']] == pytest.approx([p['temperature_c'] for p in rotated['probes']], abs=1e-8)
    assert original['status'] == rotated['status']
    assert original['mesh_check']['max_temperature_difference_k'] == pytest.approx(rotated['mesh_check']['max_temperature_difference_k'], abs=1e-8)



def test_smooth_two_dimensional_field_converges_with_four_air_films():
    body = slab()
    body.update(width=1., height=1., cell_size=.05, regions=[region('Homogeneous', 0., 1., 0., 1., 1.)],
                probes=[{'name': 'Centre', 'x': .5, 'y': .5}])
    body['boundaries'] = {side: boundary('film', temp, .2) for side, temp in [('left', 20.), ('right', 0.), ('bottom', 10.), ('top', 10.)]}
    r = calculate(Section(**body))
    assert r['status'] == 'calculated'
    assert r['probes'][0]['temperature_c'] == pytest.approx(10., abs=1e-9)
    # Symmetry and linearity imply equal/opposite left-right flow and zero NET
    # top/bottom flow, although each of those surfaces exchanges local heat.
    q = r['boundary_heat_into_domain_w_per_m']
    assert q['left'] == pytest.approx(-q['right'], abs=1e-8)
    assert q['top'] == pytest.approx(0., abs=1e-8)
    assert q['bottom'] == pytest.approx(0., abs=1e-8)
    assert abs(r['temperature_c'][0][0] - r['temperature_c'][20][0]) > 1.
    assert any(q > 0 for q in r['boundary_samples']['top']['heat_into_domain_w_per_m'])
    assert any(q < 0 for q in r['boundary_samples']['top']['heat_into_domain_w_per_m'])
