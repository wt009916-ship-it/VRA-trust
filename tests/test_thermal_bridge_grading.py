"""New mesh method checked against previously frozen independent references."""
import copy
import json
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from backend import thermal_bridge_solver as solver
from backend.thermal_bridge import Section, calculate, normalize
from test_thermal_bridge import REFERENCE, boundary, region, slab

GRADED = 'graded_interface_aligned'
COMPOSITE = json.loads((Path(__file__).resolve().parents[1] / 'validation/thermal-bridge-20261114/composite-reference-frozen.json').read_text())


@pytest.mark.parametrize('case', ['plane_slab', 'series_layers', 'parallel_bands'])
def test_graded_flux_matches_frozen_independent_resistance(case):
    body = slab()
    body['mesh_strategy'] = GRADED
    if case == 'series_layers':
        body.update(width=.22, height=1.3, cell_size=.06,
                    regions=[region('Dense', 0., .16, 0., 1.3, .8), region('Insulation', .16, .22, 0., 1.3, .04)],
                    probes=[{'name': 'Interface', 'x': .16, 'y': .65}])
        body['boundaries'].update(left=boundary('film', 21., .12), right=boundary('film', -4., .05))
    if case == 'parallel_bands':
        body.update(width=.25, height=1., cell_size=.08,
                    regions=[region('Low', 0., .25, 0., .6, .2), region('High', 0., .25, .6, 1., 1.8)])
        body['boundaries'].update(left=boundary('fixed_temperature', 20.), right=boundary('fixed_temperature', 0.))
    result = calculate(Section(**body))
    assert result['status'] == 'calculated'
    assert result['boundary_heat_into_domain_w_per_m']['left'] == pytest.approx(float(REFERENCE[case]['q_w_per_m_extension']), rel=1e-8)
    assert abs(result['energy_balance_w_per_m']) < 1e-8
    if case == 'series_layers':
        assert .16 in result['x_edges_m']
        assert result['probes'][0]['temperature_c'] == pytest.approx(21 - (25 / 1.87) * (.12 + .16 / .8), abs=1e-8)


@pytest.mark.parametrize('step', [4., 2.])
def test_public_composite_meets_original_points_heat_and_two_grid_gates(step):
    result = calculate(Section(**{**COMPOSITE['input'], 'mesh_strategy': GRADED, 'cell_size': step}))
    expected = COMPOSITE['expected']
    assert result['status'] == 'calculated' and result['mesh_check']['passed']
    assert result['mesh_check']['strategy'] == GRADED
    assert result['mesh_check']['max_temperature_difference_k'] <= .1
    assert result['mesh_check']['max_edge_heat_difference_relative'] <= .01
    assert result['mesh_check']['fine_cells'] <= 160000
    for point in result['probes']:
        assert abs(point['temperature_c'] - expected['temperature_c'][point['name']]) <= expected['absolute_temperature_tolerance_k']
    assert abs(result['boundary_heat_into_domain_w_per_m']['bottom'] - expected['heat_w_per_m']) <= expected['absolute_heat_tolerance_w_per_m']
    assert result['compliance_status'] == 'NOT_ASSESSED'
    assert result['linear_thermal_transmittance_psi_w_mk'] is None


def test_graded_28_points_match_analytic_series_but_corner_singularity_still_refused():
    ref = REFERENCE['column_temperature']
    body = slab()
    body.update(width=1., height=2., cell_size=.02, mesh_strategy=GRADED,
                regions=[region('Homogeneous', 0., 1., 0., 2., 1.)],
                probes=[{'name': str(i), 'x': p['x_m'], 'y': p['y_m']} for i, p in enumerate(ref['points'])])
    body['boundaries'] = {'left': boundary('fixed_temperature', 0.), 'right': boundary(),
                          'bottom': boundary('fixed_temperature', 0.), 'top': boundary('fixed_temperature', 20.)}
    result = calculate(Section(**body))
    assert max(abs(a['temperature_c'] - b['temperature_c']) for a, b in zip(result['probes'], ref['points'])) <= ref['max_abs_temperature_error_k']
    assert result['status'] == 'needs_refinement' and not result['mesh_check']['passed']
    assert result['mesh_check']['fixed_temperature_corner_discontinuities'] == ['left/top']


def test_graded_high_contrast_axis_transposition_preserves_field_heat_and_probes():
    body = {**copy.deepcopy(COMPOSITE['input']), 'cell_size': 4., 'mesh_strategy': GRADED}
    result = calculate(Section(**body))
    rotated = copy.deepcopy(body)
    rotated.update(width=body['height'], height=body['width'])
    for r in rotated['regions']:
        r['x0'], r['y0'], r['x1'], r['y1'] = r['y0'], r['x0'], r['y1'], r['x1']
    for p in rotated['probes']:
        p['x'], p['y'] = p['y'], p['x']
    b = body['boundaries']
    rotated['boundaries'] = dict(left=b['bottom'], right=b['top'], bottom=b['left'], top=b['right'])
    other = calculate(Section(**rotated))
    assert np.allclose(np.array(result['temperature_c']).T, other['temperature_c'], atol=1e-7, rtol=0)
    assert result['boundary_heat_into_domain_w_per_m']['bottom'] == pytest.approx(other['boundary_heat_into_domain_w_per_m']['left'], abs=1e-7)
    assert [p['temperature_c'] for p in result['probes']] == pytest.approx([p['temperature_c'] for p in other['probes']], abs=1e-7)
    assert result['status'] == other['status'] == 'calculated'


def test_graded_units_and_equal_temperature():
    body = {**slab(), 'mesh_strategy': GRADED}
    original = calculate(Section(**body))
    body['length_unit'] = 'mm'
    for key in ('width', 'height', 'cell_size'):
        body[key] *= 1000
    for r in body['regions']:
        for key in ('x0', 'x1', 'y0', 'y1'):
            r[key] *= 1000
        r['conductivity'] *= 1000
        r['conductivity_unit'] = 'mW/(m K)'
    other = calculate(Section(**body))
    assert other['boundary_heat_into_domain_w_per_m'] == pytest.approx(original['boundary_heat_into_domain_w_per_m'], abs=1e-8)
    body['boundaries']['left']['temperature_c'] = body['boundaries']['right']['temperature_c'] = 18.5
    equal = calculate(Section(**body))
    assert equal['status'] == 'calculated'
    assert all(v == 0 for v in equal['boundary_heat_into_domain_w_per_m'].values())


def test_graded_axis_capacity_is_aggregate_and_checked_before_large_allocation(monkeypatch):
    # Each of these three strips fits alone; their combined graded cells do not.
    regions = [{'x0': 0., 'x1': 1.}, {'x0': 1., 'x1': 2.}, {'x0': 2., 'x1': 3.}]
    with monkeypatch.context() as m:
        m.setattr(solver, 'MAX_CELLS', 30)
        assert len(solver.edges(1., regions[:1], 'x', .2, GRADED)) - 1 <= 30
        with pytest.raises(ValueError, match='axis exceeds'):
            solver.edges(3., regions, 'x', .2, GRADED)
    def fail(*args):
        pytest.fail('Explosive geometry reached grid allocation')
    monkeypatch.setattr(solver, 'graded_segment', fail)
    with pytest.raises(ValueError, match='budget'):
        solver.edges(100., [{'x0': 0., 'x1': 100.}], 'x', 1e-6, GRADED)


def test_graded_missing_input_and_fine_mesh_budget_are_not_bypassed(monkeypatch):
    body = {**slab(), 'mesh_strategy': GRADED}
    body['cell_size'] = 1e-6
    with pytest.raises(ValidationError, match='budget|cells'):
        Section(**body)
    body['cell_size'] = .09
    body['regions'][0]['conductivity'] = None
    monkeypatch.setattr(solver, 'calculate', lambda _: pytest.fail('Missing material entered numerical solver'))
    assert calculate(Section(**body))['temperature_c'] is None
    with pytest.raises(ValidationError):
        Section(**{**body, 'mesh_strategy': 'auto_invent'})
    assert normalize(Section(**slab()))['mesh_strategy'] == 'uniform_interface_aligned'


def test_graded_mesh_covers_domain_with_positive_cells_and_exact_material_cuts():
    body = {**COMPOSITE['input'], 'mesh_strategy': GRADED, 'cell_size': 4.}
    data = normalize(Section(**body))
    xe, ye, _, _, _ = solver.mesh(data, data['cell_size'])
    for axis, array, length in [('x', xe, data['width']), ('y', ye, data['height'])]:
        assert array[0] == 0 and array[-1] == length
        assert np.all(np.diff(array) > 0) and max(np.diff(array)) <= data['cell_size'] * (1 + 1e-12)
        for r in data['regions']:
            assert r[axis + '0'] in array and r[axis + '1'] in array
