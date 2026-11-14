"""Selected IFC mesh union, with independently checked inputs/output and no gross-sum fallback."""
import math
from pathlib import Path
import numpy as np

try:
    from .ifc_geometry import inspect_shapes, mesh_measurements
    from .ifc_details import unit_scale
except ImportError:
    from ifc_geometry import inspect_shapes, mesh_measurements
    from ifc_details import unit_scale

MAX_OPERANDS = 64
MAX_INPUT_TRIANGLES = 20000
MAX_OUTPUT_TRIANGLES = 40000


def validate_selection(ids):
    if (not isinstance(ids, list) or not 2 <= len(ids) <= MAX_OPERANDS
            or any(type(v) is not int or not 0 < v <= 2147483647 for v in ids)
            or len(set(ids)) != len(ids)):
        raise ValueError('Choose 2..64 distinct IFC entity IDs')
    return sorted(ids)



def placement_chain(placement):
    from ifcopenshell.util.placement import get_axis2placement
    chain, seen = [], set()
    while placement is not None:
        if not placement.is_a('IfcLocalPlacement') or placement.id() in seen or len(chain) >= 128:
            raise ValueError('Unsupported or cyclic IFC placement')
        seen.add(placement.id())
        axis = get_axis2placement(placement.RelativePlacement)
        if not np.isfinite(axis).all():
            raise ValueError('Nonfinite IFC placement')
        chain.append(axis)
        placement = placement.PlacementRelTo
    if not chain:
        raise ValueError('Missing IFC placement')
    return chain[::-1]


def relative_placement(chain, origin, scale, basis):
    # Cancel the root engineering offset before composing any child translation.
    # Subtracting it from the already composed native matrix loses precision.
    matrix = np.array(chain[0], dtype=float, copy=True)
    matrix[:3, 3] = basis.T @ (matrix[:3, 3] - origin)
    matrix[:3, :3] = np.eye(3) if np.array_equal(matrix[:3, :3], basis) else basis.T @ matrix[:3, :3]
    for local in chain[1:]:
        matrix = matrix @ local
    matrix[:3, 3] *= scale
    if not np.isfinite(matrix).all():
        raise ValueError('Nonfinite IFC relative placement')
    return matrix


def measure_union(path, ids):
    import ifcopenshell
    import manifold3d as manifold
    from importlib.metadata import version

    ids = validate_selection(ids)
    path = Path(path)
    if path.suffix.lower() != '.ifc' or not 0 < path.stat().st_size <= 10*1024**2:
        raise ValueError('IFC source must be 1 byte..10 MiB')
    doc = ifcopenshell.open(str(path))
    projects, products = doc.by_type('IfcProject'), doc.by_type('IfcProduct')
    if len(projects) != 1 or len(products) > 10000:
        raise ValueError('Exactly one project and at most 10000 products required')
    gids = [p.GlobalId for p in products]
    if any(not gid for gid in gids) or len(set(gids)) != len(gids):
        raise ValueError('Missing or duplicate GlobalId')
    lookup = {p.id(): p for p in products}
    if any(i not in lookup or not lookup[i].is_a('IfcElement')
           or lookup[i].is_a('IfcFeatureElement') for i in ids):
        raise ValueError('Selection must contain physical IfcElement objects, excluding features/openings')
    selected = [lookup[i] for i in ids]
    chains = [placement_chain(element.ObjectPlacement) for element in selected]
    units = [u for u in (projects[0].UnitsInContext.Units if projects[0].UnitsInContext else [])
             if getattr(u, 'UnitType', None) == 'LENGTHUNIT']
    if len(units) != 1:
        raise ValueError('Exactly one length unit required')
    scale = unit_scale(units[0], 'LENGTHUNIT')
    meshes = []
    inspected = inspect_shapes(doc, selected, scale, mesh_sink=meshes)
    rows = inspected['objects']
    result = {'status': 'unavailable', 'reason': None, 'selected_ids': ids,
        'operands': rows, 'sum_operand_volume_m3': None, 'union_volume_m3': None,
        'overlap_deduction_m3': None, 'union_surface_area_m2': None,
        'method': 'manifold3d_mesh64_boolean_union_checked_boundary_integral',
        'library_version': version('manifold3d'), 'native_settings': inspected['settings'],
        'limits': {'operands': MAX_OPERANDS, 'input_triangles': MAX_INPUT_TRIANGLES,
                   'output_triangles': MAX_OUTPUT_TRIANGLES},
        'measurement_kind': 'approximate_selected_geometric_union_not_material_quantity',
        'limitations': [
            'Only the explicitly selected physical elements in this original IFC are included.',
            'Openings are applied by the native IFC tessellator; no additional construction measurement rules.',
            'Mixed material overlaps have no material ownership assignment. This is not a priced or certified quantity.',
            'Coordinates are IFC engineering coordinates in metres, not a transformed map projection.',
            'Numerical consistency tolerance is not a guarantee of original CAD surface or field accuracy.']}
    def refuse(reason):
        result['reason'] = reason
        return result
    if any(r['volume_m3'] is None or r['volume_m3'] <= 0 for r in rows) or len(meshes) != len(ids):
        return refuse('operand_geometry_unavailable')
    if sum(len(mesh['faces']) for mesh in meshes) > MAX_INPUT_TRIANGLES:
        return refuse('input_triangle_budget_exceeded')
    # Subtract a common translation BEFORE applying it to vertices; avoid loss
    # of sub-metre detail when a building is located far from the IFC origin.
    origin = chains[0][0][:3, 3].copy()
    basis = chains[0][0][:3, :3]
    if not np.allclose(basis.T @ basis, np.eye(3), atol=1e-12, rtol=0):
        return refuse('unsupported_relative_placement')
    result['common_origin_m'] = (origin*scale).tolist()
    result['common_basis_world'] = basis.tolist()
    operands = []
    flipped = []
    for mesh, row, chain in zip(meshes, rows, chains):
        matrix = relative_placement(chain, origin, scale, basis)
        vertices = mesh['vertices'] @ matrix[:3, :3].T + matrix[:3, 3]
        if not np.isfinite(vertices).all() or np.max(np.abs(vertices)) > 1e9:
            return refuse('relative_coordinate_range_exceeded')
        vertices, remap = np.unique(vertices, axis=0, return_inverse=True)
        faces = remap[mesh['faces']]
        signed = math.fsum(s['signed_volume_m3'] for s in row['topology']['shells'])
        # Global orientation normalization only, after cavity/shell consistency
        # has been independently checked. No tolerance welding or hole repair.
        if signed < 0:
            faces = faces[:, ::-1]
            flipped.append(row['id'])
        solid = manifold.Manifold(manifold.Mesh64(np.ascontiguousarray(vertices, dtype=np.float64),
                                                  np.ascontiguousarray(faces, dtype=np.uint64)))
        if solid.status() != manifold.Error.NoError:
            return refuse('boolean_operand_rejected')
        tolerance = max(1e-9, row['volume_m3']*1e-8)
        if not math.isfinite(solid.volume()) or abs(solid.volume()-row['volume_m3']) > tolerance:
            return refuse('operand_world_volume_mismatch')
        operands.append(solid)
    result['orientation_normalized_ids'] = flipped
    try:
        combined = manifold.Manifold.batch_boolean(operands, manifold.OpType.Add)
        if combined.status() != manifold.Error.NoError or combined.is_empty():
            return refuse('boolean_result_unavailable')
        if combined.num_tri() > MAX_OUTPUT_TRIANGLES:
            return refuse('output_triangle_budget_exceeded')
        mesh = combined.to_mesh64()
        checked = mesh_measurements(mesh.vert_properties[:, :3], mesh.tri_verts)
        result['output_check'] = checked
        if checked['volume_m3'] is None:
            return refuse('union_topology_unverified')
        total = math.fsum(r['volume_m3'] for r in rows)
        value, native = checked['volume_m3'], combined.volume()
        tolerance = max(1e-9, total*1e-8)
        if (not math.isfinite(native) or abs(value-native) > tolerance
                or value > total+tolerance or value < max(r['volume_m3'] for r in rows)-tolerance):
            return refuse('union_volume_consistency_failed')
        # Never manufacture a positive deduction from floating-point noise.
        overlap = total-value
        if overlap < 0:
            if abs(overlap) > tolerance:
                return refuse('negative_overlap_deduction')
            overlap = 0.
        result.update(status='measured', sum_operand_volume_m3=total, union_volume_m3=value,
            overlap_deduction_m3=overlap, union_surface_area_m2=checked['surface_area_m2'],
            numeric_consistency_tolerance_m3=tolerance, native_tolerance_m=combined.get_tolerance())
        return result
    except (RuntimeError, ValueError, OverflowError):
        return refuse('boolean_operation_failed')
