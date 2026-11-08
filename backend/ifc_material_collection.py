"""Union same-declared-material layer envelopes; refuse cross-material overlap."""
import math
from pathlib import Path
import numpy as np

try:
    from .ifc_details import project_units, unit_scale
    from .ifc_geometry import mesh_measurements
    from .ifc_layer_quantities import measure_layers
    from .ifc_union import placement_chain, relative_placement
except ImportError:
    from ifc_details import project_units, unit_scale
    from ifc_geometry import mesh_measurements
    from ifc_layer_quantities import measure_layers
    from ifc_union import placement_chain, relative_placement

MAX_PRODUCTS = 16
MAX_LAYERS = 256
MAX_TRIANGLES = 40000


def measure_collection(path, ids):
    import ifcopenshell
    import manifold3d as manifold

    if (not isinstance(ids, list) or not 2 <= len(ids) <= MAX_PRODUCTS
            or any(type(v) is not int or not 0 < v <= 2147483647 for v in ids)
            or len(set(ids)) != len(ids)):
        raise ValueError('Choose 2..16 distinct IFC product IDs')
    ids = sorted(ids)
    path = Path(path)
    if path.suffix.lower() != '.ifc' or not 0 < path.stat().st_size <= 10*1024**2:
        raise ValueError('IFC source must be 1 byte..10 MiB')
    doc = ifcopenshell.open(str(path))
    projects, products = doc.by_type('IfcProject'), doc.by_type('IfcProduct')
    if len(projects) != 1 or len(products) > 10000:
        raise ValueError('Exactly one project and at most 10000 products required')
    lookup = {p.id(): p for p in products}
    if any(i not in lookup or not lookup[i].is_a('IfcWall') for i in ids):
        raise ValueError('Selection must contain physical IfcWall entities')
    # Validate every placement before any native geometry operation.
    chains = [placement_chain(lookup[i].ObjectPlacement) for i in ids]
    units = project_units(projects[0]).get('LENGTHUNIT', [])
    if len(units) != 1:
        raise ValueError('Exactly one length unit required')
    scale = unit_scale(units[0], 'LENGTHUNIT')
    origin, basis = chains[0][0][:3, 3].copy(), chains[0][0][:3, :3]
    result = {'status': 'unavailable', 'reason': None, 'selected_ids': ids,
              'materials': [], 'source_layers': [], 'failed_products': [],
              'sum_layer_envelope_m3': None, 'union_envelope_m3': None,
              'same_material_overlap_deduction_m3': None,
              'cross_material_overlap_detected': None,
              'method': 'voided_layer_mesh_union_by_source_material_entity',
              'quantity_kind': 'selected_model_material_envelope_not_purchase_quantity',
              'limitations': [
                  'Only selected straight-axis layered walls in one IFC are included.',
                  'Grouping uses IFC material entity IDs, never equality of material names.',
                  'Same-material spatial overlap is counted once; cross-material overlap blocks all totals.',
                  'Layer envelopes may include cavities/studs; no density, solid fraction or purchasing rule is inferred.',
                  'Model accuracy, construction rules and functional equivalence require separate review.']}

    def refuse(reason):
        result['reason'] = reason
        return result

    if not np.allclose(basis.T @ basis, np.eye(3), atol=1e-12, rtol=0):
        return refuse('nonrigid_common_basis')
    groups, source_rows = {}, []
    triangles = 0
    for ident, chain in zip(ids, chains):
        matrix = relative_placement(chain, origin, scale, basis)
        if (not np.allclose(matrix[:3, :3].T @ matrix[:3, :3], np.eye(3), atol=1e-12, rtol=0)
                or abs(np.linalg.det(matrix[:3, :3])-1) > 1e-12):
            return refuse('nonrigid_relative_placement')
        meshes = []
        measured = measure_layers(path, ident, mesh_sink=meshes, _document=doc)
        if measured['status'] != 'measured' or len(meshes) != len(measured['layers']):
            result['failed_products'].append({'product_id': ident, 'reason': measured['reason']})
            return refuse('selected_layer_geometry_unavailable')
        if len(source_rows) + len(meshes) > MAX_LAYERS:
            return refuse('layer_budget_exceeded')
        for row, mesh in zip(measured['layers'], meshes):
            triangles += len(mesh['faces'])
            if triangles > MAX_TRIANGLES:
                return refuse('input_triangle_budget_exceeded')
            vertices = mesh['vertices'] @ matrix[:3, :3].T + matrix[:3, 3]
            if not np.isfinite(vertices).all() or np.max(np.abs(vertices)) > 1e9:
                return refuse('relative_coordinate_range_exceeded')
            solid = manifold.Manifold(manifold.Mesh64(np.ascontiguousarray(vertices, dtype=np.float64),
                                                      np.ascontiguousarray(mesh['faces'], dtype=np.uint64)))
            tolerance = max(1e-9, row['envelope_volume_m3']*1e-8)
            if (solid.status() != manifold.Error.NoError or not math.isfinite(solid.volume())
                    or abs(solid.volume()-row['envelope_volume_m3']) > tolerance):
                return refuse('world_layer_volume_mismatch')
            source = {'product_id': ident, 'layer_id': row['layer_id'], 'material_id': row['material_id'],
                      'material_name': row['material_name'], 'envelope_volume_m3': row['envelope_volume_m3']}
            source_rows.append(source)
            groups.setdefault(row['material_id'], []).append((solid, source))

    def checked_union(solids, total):
        merged = manifold.Manifold.batch_boolean(solids, manifold.OpType.Add)
        if merged.status() != manifold.Error.NoError or merged.is_empty() or merged.num_tri() > MAX_TRIANGLES:
            raise ValueError('Union output unavailable or exceeds triangle budget')
        mesh = merged.to_mesh64()
        checked = mesh_measurements(mesh.vert_properties[:, :3], mesh.tri_verts)
        value, native = checked['volume_m3'], merged.volume()
        tolerance = max(1e-9, total*1e-8)
        if (value is None or not math.isfinite(native) or abs(value-native) > tolerance
                or value > total+tolerance or value < max(s.volume() for s in solids)-tolerance):
            raise ValueError('Union topology/volume not verified')
        return merged, value, checked

    try:
        materials, merged_solids = [], []
        for material_id, operands in sorted(groups.items()):
            total = math.fsum(r['envelope_volume_m3'] for _, r in operands)
            merged, value, check = checked_union([s for s, _ in operands], total)
            merged_solids.append(merged)
            materials.append({'material_id': material_id, 'material_name': operands[0][1]['material_name'],
                              'source_sum_m3': total, 'union_envelope_m3': value,
                              'overlap_deduction_m3': max(0., total-value),
                              'sources': [{'product_id': r['product_id'], 'layer_id': r['layer_id']} for _, r in operands],
                              'mesh_check': check})
        group_sum = math.fsum(r['union_envelope_m3'] for r in materials)
        _, whole, whole_check = checked_union(merged_solids, group_sum)
        tolerance = max(1e-9, group_sum*1e-8)
        if group_sum-whole > tolerance:
            result['cross_material_overlap_detected'] = True
            return refuse('cross_material_overlap_ownership_unresolved')
        total = math.fsum(r['envelope_volume_m3'] for r in source_rows)
        result.update(status='measured', materials=materials, source_layers=source_rows,
                      sum_layer_envelope_m3=total, union_envelope_m3=whole,
                      same_material_overlap_deduction_m3=max(0., total-whole),
                      cross_material_overlap_detected=False, numeric_consistency_tolerance_m3=tolerance,
                      output_check=whole_check, common_origin_m=(origin*scale).tolist(),
                      common_basis_world=basis.tolist())
        return result
    except (ValueError, RuntimeError, OverflowError):
        return refuse('material_union_geometry_unverified')
