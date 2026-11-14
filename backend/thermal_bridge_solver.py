"""Conservative cell-centred 2D conduction on interface-aligned rectangle grids."""
import math
import time

import numpy as np

MAX_CELLS = 160000
MAX_ITERATIONS = 6000


def edges(length, regions, axis, step):
    cuts = sorted({0., length, *(r[axis + '0'] for r in regions), *(r[axis + '1'] for r in regions)})
    counts = [math.ceil((b - a) / step) for a, b in zip(cuts, cuts[1:])]
    if any(b - a < 1e-8 for a, b in zip(cuts, cuts[1:])) or sum(counts) > MAX_CELLS:
        raise ValueError('Geometry spacing or mesh exceeds supported budget')
    return np.concatenate([np.linspace(a, b, n + 1)[:-1] for a, b, n in zip(cuts, cuts[1:], counts)] + [np.array([length])])


def mesh(data, step):
    xe = edges(data['width'], data['regions'], 'x', step)
    ye = edges(data['height'], data['regions'], 'y', step)
    nx, ny = len(xe) - 1, len(ye) - 1
    if nx * ny > MAX_CELLS:
        raise ValueError('Mesh exceeds 160000 cells; select a coarser grid or smaller domain')
    x, y = (xe[:-1] + xe[1:]) / 2, (ye[:-1] + ye[1:]) / 2
    count = np.zeros((ny, nx), dtype=np.int16)
    k = np.zeros((ny, nx))
    for region in data['regions']:
        mask = ((x >= region['x0']) & (x < region['x1']))[None, :] & ((y >= region['y0']) & (y < region['y1']))[:, None]
        count += mask
        k[mask] = region['conductivity']
    if np.any(count != 1):
        raise ValueError('Material regions must cover the rectangle exactly once; gaps and overlaps refused')
    return xe, ye, x, y, k


def interpolate(x, y, field, px, py):
    """Bilinear interpolation on a rectilinear mesh, clamped at supplied endpoints."""
    column = np.array([np.interp(px, x, row) for row in field])
    return float(np.interp(py, y, column))


def solve(data, step, deadline):
    xe, ye, x, y, k = mesh(data, step)
    dx, dy = np.diff(xe), np.diff(ye)
    ny, nx = k.shape
    # Conductance per metre of extension; material-interface resistances in series.
    gx = dy[:, None] / (dx[:-1][None, :] / (2 * k[:, :-1]) + dx[1:][None, :] / (2 * k[:, 1:]))
    gy = dx[None, :] / (dy[:-1, None] / (2 * k[:-1]) + dy[1:, None] / (2 * k[1:]))
    diagonal = np.zeros_like(k)
    diagonal[:, :-1] += gx
    diagonal[:, 1:] += gx
    diagonal[:-1] += gy
    diagonal[1:] += gy
    boundary = {}
    reference = float(np.mean([b['temperature_c'] for b in data['boundaries'].values() if b['mode'] != 'adiabatic']))
    rhs = np.zeros_like(k)
    for side, index, length, distance in [('left', (slice(None), 0), dy, dx[0] / 2),
                                         ('right', (slice(None), -1), dy, dx[-1] / 2),
                                         ('bottom', (0, slice(None)), dx, dy[0] / 2),
                                         ('top', (-1, slice(None)), dx, dy[-1] / 2)]:
        b = data['boundaries'][side]
        resistance = b['resistance_m2k_w'] if b['mode'] == 'film' else 0.
        g = np.zeros_like(length) if b['mode'] == 'adiabatic' else length / (resistance + distance / k[index])
        diagonal[index] += g
        if b['mode'] != 'adiabatic':
            rhs[index] += g * (b['temperature_c'] - reference)
        boundary[side] = (index, length, distance, g, resistance, b)
    if np.any(diagonal <= 0):
        raise ValueError('Unanchored or disconnected thermal system')

    def apply(v):
        # Flux differences avoid subtracting large near-equal diagonal products
        # in high-conductivity regions. Keep the same symmetric operator.
        result = np.zeros_like(v)
        horizontal = gx * (v[:, :-1] - v[:, 1:])
        vertical = gy * (v[:-1] - v[1:])
        result[:, :-1] += horizontal
        result[:, 1:] -= horizontal
        result[:-1] += vertical
        result[1:] -= vertical
        for index, _, _, g, _, _ in boundary.values():
            result[index] += g * v[index]
        return result

    # Diagonally preconditioned conjugate gradients. No dense N x N matrix.
    theta = np.zeros_like(k)
    residual = rhs.copy()
    z = residual / diagonal
    direction = z.copy()
    rz = float(np.sum(residual * z))
    norm_rhs = float(np.linalg.norm(rhs))
    tolerance = 1e-11 * norm_rhs + 1e-13
    iterations = 0
    residual_restarts = 0
    while True:
        if float(np.linalg.norm(residual)) <= tolerance:
            actual = rhs - apply(theta)
            if float(np.linalg.norm(actual)) <= max(tolerance * 20, 1e-10):
                break
            if residual_restarts >= 3:
                raise ValueError('True linear residual did not converge after residual replacement')
            # Recursive CG residual drifts in high-contrast composite materials.
            # Restart from the measured residual without relaxing the tolerance.
            residual = actual
            z = residual / diagonal
            direction = z.copy()
            rz = float(np.sum(residual * z))
            residual_restarts += 1
        if iterations >= MAX_ITERATIONS or time.monotonic() > deadline:
            raise ValueError('Conduction solver exceeded iteration/time budget; no converged result')
        product = apply(direction)
        denominator = float(np.sum(direction * product))
        if not math.isfinite(denominator) or denominator <= 0:
            raise ValueError('Conduction solver lost positive definiteness')
        alpha = rz / denominator
        theta += alpha * direction
        residual -= alpha * product
        z = residual / diagonal
        next_rz = float(np.sum(residual * z))
        direction = z + (next_rz / rz) * direction
        rz = next_rz
        iterations += 1
    actual_residual = rhs - apply(theta)
    residual_norm = float(np.linalg.norm(actual_residual))
    if not math.isfinite(residual_norm) or residual_norm > max(tolerance * 20, 1e-10):
        raise ValueError(f'Recomputed linear residual {residual_norm:.6g} exceeds numerical tolerance {max(tolerance * 20, 1e-10):.6g}')
    temperature = theta + reference
    anchors = [b['temperature_c'] for b in data['boundaries'].values() if b['mode'] != 'adiabatic']
    if not np.isfinite(temperature).all() or temperature.min() < min(anchors) - 1e-7 or temperature.max() > max(anchors) + 1e-7:
        raise ValueError('Temperature field violates finite maximum principle')
    flux, surfaces = {}, {}
    positive, negative = 0., 0.
    for side, (index, length, distance, g, resistance, b) in boundary.items():
        q = np.zeros_like(length) if b['mode'] == 'adiabatic' else g * (b['temperature_c'] - temperature[index])
        surface = temperature[index] + q * distance / (length * k[index])
        flux[side] = float(np.sum(q))
        positive += float(np.maximum(q, 0).sum())
        negative += float(np.minimum(q, 0).sum())
        surfaces[side] = {'temperature_c': surface.tolist(), 'heat_into_domain_w_per_m': q.tolist(),
                          'face_length_m': length.tolist(), 'heat_flux_density_into_domain_w_m2': (q / length).tolist()}
    balance = positive + negative
    if abs(balance) > 1e-8 * max(positive, -negative, 1.) + 1e-10:
        raise ValueError('Thermal energy balance failed')
    return {'xe': xe, 'ye': ye, 'x': x, 'y': y, 'temperature': temperature,
            'flux': flux, 'surfaces': surfaces, 'positive_heat_in': positive,
            'balance': balance, 'iterations': iterations, 'residual_norm': residual_norm,
            'rhs_norm': norm_rhs, 'cells': nx * ny, 'conductivity': k, 'residual_restarts': residual_restarts}


def sample_line(centres, edges, values, conductivity, point, first_surface, last_surface):
    if point <= centres[0]:
        return float(np.interp(point, [edges[0], centres[0]], [first_surface, values[0]])), float(conductivity[0])
    if point >= centres[-1]:
        return float(np.interp(point, [centres[-1], edges[-1]], [values[-1], last_surface])), float(conductivity[-1])
    left = int(np.searchsorted(centres, point)) - 1
    right = left + 1
    face = edges[right]
    dl, dr = face - centres[left], centres[right] - face
    kl, kr = conductivity[left], conductivity[right]
    interface = (kl / dl * values[left] + kr / dr * values[right]) / (kl / dl + kr / dr)
    if abs(point - face) <= 1e-12:
        return float(interface), float((dr * kl + dl * kr) / (dl + dr))
    if point < face:
        return float(np.interp(point, [centres[left], face], [values[left], interface])), float(kl)
    return float(np.interp(point, [face, centres[right]], [interface, values[right]])), float(kr)


def probes(data, run):
    """Reconstruct across each material interface by its two half-cell resistances.

    Values at intersections remain a grid approximation, not exact continuum data.
    Conductivity-weighted intermediate rows retain the equal-grid four-cell rule.
    """
    t, k = run['temperature'], run['conductivity']
    surfaces = {side: row['temperature_c'] for side, row in run['surfaces'].items()}
    def corner(horizontal, vertical):
        b1, b2 = data['boundaries'][horizontal], data['boundaries'][vertical]
        ix, iy = (0 if vertical == 'left' else -1), (0 if horizontal == 'bottom' else -1)
        if b1['mode'] == 'fixed_temperature':
            return b1['temperature_c']
        if b2['mode'] == 'fixed_temperature':
            return b2['temperature_c']
        if b2['mode'] == 'adiabatic':
            return surfaces[horizontal][ix]
        if b1['mode'] == 'adiabatic':
            return surfaces[vertical][iy]
        return (surfaces[horizontal][ix] + surfaces[vertical][iy]) / 2
    rows = []
    for point in data['probes']:
        tx, kx = zip(*(sample_line(run['x'], run['xe'], row, conduct, point['x'], surfaces['left'][j], surfaces['right'][j])
                       for j, (row, conduct) in enumerate(zip(t, k))))
        lower, _ = sample_line(run['x'], run['xe'], surfaces['bottom'], k[0], point['x'], corner('bottom', 'left'), corner('bottom', 'right'))
        upper, _ = sample_line(run['x'], run['xe'], surfaces['top'], k[-1], point['x'], corner('top', 'left'), corner('top', 'right'))
        value, _ = sample_line(run['y'], run['ye'], tx, kx, point['y'], lower, upper)
        rows.append({**point, 'temperature_c': value, 'method': 'resistance_weighted_piecewise_reconstruction',
                     'not_an_exact_continuum_value': True})
    return rows


def calculate(data):
    deadline = time.monotonic() + 25
    coarse = solve(data, data['cell_size'], deadline)
    fine = solve(data, data['cell_size'] / 2, deadline)
    # Compare at the same physical coarse-cell centres, not matching array indices.
    intermediate = np.array([np.interp(coarse['x'], fine['x'], row) for row in fine['temperature']])
    resampled = np.array([np.interp(coarse['y'], fine['y'], column) for column in intermediate.T]).T
    temperature_difference = float(np.abs(coarse['temperature'] - resampled).max())
    scale = max(coarse['positive_heat_in'], fine['positive_heat_in'], 1e-10)
    flux_difference = max(abs(fine['flux'][s] - coarse['flux'][s]) for s in fine['flux']) / scale
    discontinuities = []
    for first, second in [('left', 'top'), ('top', 'right'), ('right', 'bottom'), ('bottom', 'left')]:
        a, b = data['boundaries'][first], data['boundaries'][second]
        if a['mode'] == b['mode'] == 'fixed_temperature' and a['temperature_c'] != b['temperature_c']:
            discontinuities.append(first + '/' + second)
    converged = temperature_difference <= .1 and flux_difference <= .01 and not discontinuities
    return {'status': 'calculated' if converged else 'needs_refinement',
            'method': '2d_cell_centred_finite_volume_interface_aligned_harmonic_conductance',
            'temperature_c': fine['temperature'].tolist(), 'x_centres_m': fine['x'].tolist(), 'y_centres_m': fine['y'].tolist(),
            'x_edges_m': fine['xe'].tolist(), 'y_edges_m': fine['ye'].tolist(),
            'boundary_heat_into_domain_w_per_m': fine['flux'], 'boundary_samples': fine['surfaces'],
            'total_positive_heat_in_w_per_m': fine['positive_heat_in'], 'energy_balance_w_per_m': fine['balance'],
            'probes': probes(data, fine),
            'mesh_check': {'coarse_cells': coarse['cells'], 'fine_cells': fine['cells'],
                           'max_temperature_difference_k': temperature_difference,
                           'max_edge_heat_difference_relative': flux_difference,
                           'temperature_limit_k': .1, 'relative_heat_limit': .01, 'passed': converged,
                           'fixed_temperature_corner_discontinuities': discontinuities,
                           'notice': 'Two-grid difference is an estimate, not a rigorous continuum error bound. Corner temperature discontinuities may have singular total heat flow.'},
            'linear_solver': {'coarse_iterations': coarse['iterations'], 'fine_iterations': fine['iterations'],
                              'coarse_residual_restarts': coarse['residual_restarts'], 'fine_residual_restarts': fine['residual_restarts'],
                              'residual_l2_w_per_m': fine['residual_norm'], 'rhs_l2_w_per_m': fine['rhs_norm'],
                              'residual_is_not_discretization_error': True},
            'compliance_status': 'NOT_ASSESSED', 'linear_thermal_transmittance_psi_w_mk': None,
            'limitations': ['恒定各向同性导热系数，无内部热源；仅矩形外边界及完整矩形材料分区。',
                            '热流单位为W/m延伸长度，正值进入截面；不是全楼W或全年kWh。',
                            '网格未通过时数值仅作诊断；两网格接近不证明全部工程精度。',
                            '没有计算线性热桥系数ψ、结露、辐射空腔、结构安全或节能合规。']}
