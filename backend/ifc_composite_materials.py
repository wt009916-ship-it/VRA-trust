"""Explicit composite-profile partitions, measured in private native geometry copies."""
import math
import numpy as np

try:
    from .ifc_geometry import inspect_shapes, mesh_measurements
except ImportError:
    from ifc_geometry import inspect_shapes, mesh_measurements

MAX_PARTS = 16
MAX_TRIANGLES = 40000


def partition_reference(element, group):
    bodies = [r for r in element.Representation.Representations if r.RepresentationIdentifier == 'Body'] if element.Representation else []
    if len(bodies) != 1 or len(bodies[0].Items) != 1:
        raise ValueError('composite_single_body_path_required')
    item, path = bodies[0].Items[0], []
    while not item.is_a('IfcExtrudedAreaSolid'):
        if item.id() in [x.id() for x in path] or len(path) >= 16:
            raise ValueError('composite_body_path_budget')
        path.append(item)
        if item.is_a('IfcMappedItem'):
            items = item.MappingSource.MappedRepresentation.Items
            if len(items) != 1:
                raise ValueError('composite_mapping_path_ambiguous')
            item = items[0]
        elif item.is_a('IfcBooleanResult') and item.Operator == 'DIFFERENCE':
            item = item.FirstOperand
        else:
            raise ValueError('composite_sweep_mapping_unsupported')
    if item.is_a() != 'IfcExtrudedAreaSolid' or not item.SweptArea.is_a('IfcCompositeProfileDef'):
        raise ValueError('composite_constant_extrusion_required')
    composite = item.SweptArea
    if composite.ProfileType != 'AREA' or not math.isfinite(item.Depth) or item.Depth <= 0:
        raise ValueError('composite_source_sweep_invalid')
    profiles = list(composite.Profiles)
    declared = group['profiles']
    if not 2 <= len(profiles) <= MAX_PARTS or len(declared) != len(profiles):
        raise ValueError('composite_profile_count_or_coverage')
    if any(p.ProfileType != 'AREA' or p.is_a('IfcCompositeProfileDef') for p in profiles):
        raise ValueError('composite_flat_area_profiles_required')
    if any(p['type'] != 'IfcMaterialProfile' or p['material']['type'] != 'IfcMaterial' or not p['profile'] for p in declared):
        raise ValueError('composite_material_profile_missing')
    source_ids = [p.id() for p in profiles]
    declared_ids = [p['profile']['id'] for p in declared]
    if (len(set(source_ids)) != len(source_ids) or len(set(declared_ids)) != len(declared_ids)
            or set(source_ids) != set(declared_ids) or group.get('composite_profile_id') != composite.id()):
        raise ValueError('composite_profile_ownership_mismatch')
    return bodies[0], path, item, composite, declared


def private_partition(doc, element, body, path, solid, profile_id):
    """Copy only the occurrence's geometry path; never mutate shared source items."""
    import ifcopenshell
    clone = ifcopenshell.file.from_string(doc.to_string())
    source = clone.by_id(solid.id())
    child = clone.create_entity('IfcExtrudedAreaSolid', SweptArea=clone.by_id(profile_id),
        Position=source.Position, ExtrudedDirection=source.ExtrudedDirection, Depth=source.Depth)
    for original in reversed(path):
        node = clone.by_id(original.id())
        if node.is_a('IfcMappedItem'):
            rep = node.MappingSource.MappedRepresentation
            replacement = clone.create_entity('IfcShapeRepresentation', ContextOfItems=rep.ContextOfItems,
                RepresentationIdentifier=rep.RepresentationIdentifier, RepresentationType=rep.RepresentationType, Items=[child])
            mapping = clone.create_entity('IfcRepresentationMap', MappingOrigin=node.MappingSource.MappingOrigin,
                MappedRepresentation=replacement)
            child = clone.create_entity('IfcMappedItem', MappingSource=mapping, MappingTarget=node.MappingTarget)
        else:
            child = clone.create_entity(node.is_a(), Operator=node.Operator, FirstOperand=child, SecondOperand=node.SecondOperand)
    rep = clone.by_id(body.id())
    replacement = clone.create_entity('IfcShapeRepresentation', ContextOfItems=rep.ContextOfItems,
        RepresentationIdentifier=rep.RepresentationIdentifier, RepresentationType=rep.RepresentationType, Items=[child])
    target = clone.by_id(element.id())
    old = target.Representation
    target.Representation = clone.create_entity('IfcProductDefinitionShape', Name=old.Name, Description=old.Description,
        Representations=[replacement if r.id() == body.id() else r for r in old.Representations])
    return clone, target


def measure_composite(doc, element, binding, group, scale, result, mesh_sink):
    import manifold3d as manifold

    def refuse(reason):
        result.update(reason=reason, layers=[], total_layer_envelope_m3=None, host_volume_m3=None)
        return result
    try:
        body, path, sweep, composite, declared = partition_reference(element, group)
        solids, meshes, rows = [], [], []
        triangles = 0
        for profile in declared:
            clone, target = private_partition(doc, element, body, path, sweep, profile['profile']['id'])
            native_meshes = []
            check = inspect_shapes(clone, [target], scale, mesh_sink=native_meshes)['objects'][0]
            value = check['volume_m3']
            if value is None or value <= 0 or len(native_meshes) != 1:
                return refuse('composite_partition_mesh_unverified')
            mesh = native_meshes[0]
            triangles += len(mesh['faces'])
            if triangles > MAX_TRIANGLES:
                return refuse('composite_input_triangle_budget')
            vertices, remap = np.unique(mesh['vertices'], axis=0, return_inverse=True)
            faces = remap[mesh['faces']]
            if math.fsum(s['signed_volume_m3'] for s in check['topology']['shells']) < 0:
                faces = faces[:, ::-1]
            solid = manifold.Manifold(manifold.Mesh64(np.ascontiguousarray(vertices, dtype=np.float64),
                np.ascontiguousarray(faces, dtype=np.uint64)))
            tolerance = max(1e-9, value*1e-8)
            if solid.status() != manifold.Error.NoError or not math.isfinite(solid.volume()) or abs(solid.volume()-value) > tolerance:
                return refuse('composite_boolean_operand_unverified')
            solids.append(solid)
            meshes.append({'vertices':vertices, 'faces':faces})
            rows.append({'layer_id':profile['id'], 'source_slice_kind':'material_profile_partition',
                'material_id':profile['material']['id'], 'material_name':profile['material']['name'],
                'profile_id':profile['profile']['id'], 'thickness_m':None, 'envelope_volume_m3':value,
                'mesh_check':check, 'geometry_origin':'private_occurrence_copy_with_original_openings',
                'source_body_id':body.id(), 'source_sweep_id':sweep.id()})
        total = math.fsum(row['envelope_volume_m3'] for row in rows)
        tolerance = max(1e-9, total*1e-8)
        whole = manifold.Manifold.batch_boolean(solids, manifold.OpType.Add)
        if whole.status() != manifold.Error.NoError or whole.is_empty() or whole.num_tri() > MAX_TRIANGLES:
            return refuse('composite_union_unverified')
        mesh = whole.to_mesh64()
        check = mesh_measurements(mesh.vert_properties[:, :3], mesh.tri_verts)
        value = check['volume_m3']
        if value is None or not math.isfinite(whole.volume()) or abs(value-whole.volume()) > tolerance or value > total+tolerance:
            return refuse('composite_union_topology_unverified')
        if total-value > tolerance:
            result['partition_overlap_detected'] = True
            return refuse('composite_profile_spatial_overlap')
        mapping = {'kind':'exact_composite_sweep_partitions', 'material_definition_id':binding['material']['id'],
            'profile_set_id':group['id'], 'composite_profile_id':composite.id(), 'body_id':body.id(),
            'sweep_id':sweep.id(), 'body_wrapper_ids':[x.id() for x in path],
            'material_profile_ids':[p['id'] for p in declared], 'body_profile_ids':[p['profile']['id'] for p in declared],
            'coverage':'every_declared_profile_matches_exactly_one_source_composite_profile',
            'host_volume_method':'verified_union_of_complete_source_partitions_not_raw_whole_mesh'}
        result.update(status='measured', layers=rows, total_layer_envelope_m3=total, host_volume_m3=value,
            method='native_composite_profile_partitions_after_original_openings_and_clipping',
            source_relation_id=binding['relation_id'], partition_overlap_detected=False,
            numeric_consistency_tolerance_m3=tolerance, partition_union_check=check, material_mapping=mapping,
            layer_reference={**mapping, 'source_scope':binding['scope'], 'source_relation_id':binding['relation_id'],
                'source_owner_id':binding['owner_id'], 'coordinate_system':'product_local_body'},
            limitations=['材料轮廓与原Body复合轮廓一一对应后分别原生求解；各分区须通过网格和并集检查。',
                '整体体积由完整分区的空间并集计算；不是原始整体网格独立通过声明。',
                '支持恒截面挤出、单路径映射和DIFFERENCE截切；不推断缺失材质、钢筋、实体率或采购量。',
                '原模型和共享几何不修改；原生核验回执中的新表示ID属于临时计算副本，原始ID单列。'])
        if mesh_sink is not None:
            mesh_sink.extend(meshes)
        return result
    except (ValueError, RuntimeError, TypeError, AttributeError, OverflowError) as exc:
        return refuse(str(exc) if isinstance(exc, ValueError) else 'composite_material_geometry_unverified')
