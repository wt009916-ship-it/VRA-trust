"""Declared homogeneous beam/column material measured from the voided Body mesh."""
import math
import numpy as np

try:
    from .ifc_details import material_declarations, project_units, unit_scale
    from .ifc_geometry import inspect_shapes
except ImportError:
    from ifc_details import material_declarations, project_units, unit_scale
    from ifc_geometry import inspect_shapes


def body_profiles(element):
    bodies = [r for r in element.Representation.Representations if r.RepresentationIdentifier == 'Body'] if element.Representation else []
    if len(bodies) != 1:
        raise ValueError('one_body_required_for_material_profile')
    found, visited = set(), set()
    def walk(item, stack=()):
        if item.id() in stack or len(stack) > 16 or len(visited) >= 128:
            raise ValueError('material_body_traversal_budget')
        visited.add(item.id())
        if item.is_a('IfcMappedItem'):
            for child in item.MappingSource.MappedRepresentation.Items:
                walk(child, (*stack, item.id()))
        elif item.is_a('IfcBooleanResult') and item.Operator == 'DIFFERENCE':
            walk(item.FirstOperand, (*stack, item.id()))
        elif item.is_a('IfcSweptAreaSolid'):
            found.add(item.SweptArea.id())
            if getattr(item, 'EndSweptArea', None):
                found.add(item.EndSweptArea.id())
        else:
            raise ValueError('material_profile_body_mapping_unverified')
    for item in bodies[0].Items:
        walk(item)
    return found


def single_material(binding, element):
    declared = binding['material']
    if declared['type'] == 'IfcMaterial':
        return declared, {'kind':'whole_body_material', 'material_definition_id':declared['id']}
    group = declared.get('profile_set') if declared['type'] == 'IfcMaterialProfileSetUsage' else declared
    if not group or group['type'] != 'IfcMaterialProfileSet':
        raise ValueError('member_material_definition_not_supported')
    profiles = group['profiles']
    if not 1 <= len(profiles) <= 32 or any(p['type'] != 'IfcMaterialProfile' or p['material']['type'] != 'IfcMaterial' or not p['profile'] for p in profiles):
        raise ValueError('member_profile_material_missing_or_unsupported')
    if len({p['material']['id'] for p in profiles}) != 1:
        raise ValueError('heterogeneous_member_material_partition_required')
    if {p['profile']['id'] for p in profiles} != body_profiles(element):
        raise ValueError('member_material_profile_body_mismatch')
    return profiles[0]['material'], {'kind':'homogeneous_body_profiles', 'material_definition_id':declared['id'],
        'profile_set_id':group['id'], 'material_profile_ids':[p['id'] for p in profiles],
        'body_profile_ids':sorted(p['profile']['id'] for p in profiles)}


def measure_member(doc, element, *, mesh_sink=None):
    result = {'status':'unavailable','product_id':element.id(),'layers':[], 'reason':None,
        'total_layer_envelope_m3':None, 'host_volume_m3':None, 'layer_set_id':None,
        'method':'voided_body_mesh_bound_to_declared_homogeneous_material',
        'quantity_kind':'model_member_material_envelope_after_ifc_openings',
        'limitations':['梁柱有效材料声明与模型Body体积绑定；不是施工净量、采购量或实测材料量。',
                       '不把材料名推断成密度或性能，不补未建模的钢筋、连接件或施工损耗。',
                       '复合不同材料须明确几何分区；本次不按截面面积比例分摊。']}
    def refuse(reason):
        result['reason'] = reason
        return result
    units = project_units(doc.by_type('IfcProject')[0])
    if len(units.get('LENGTHUNIT', [])) != 1:
        return refuse('length_unit_unavailable')
    try:
        scale = unit_scale(units['LENGTHUNIT'][0], 'LENGTHUNIT')
        assignment = material_declarations(element, units)['material_assignment']
        active = [r for r in assignment['associations'] if r['selection'] == 'effective_declaration']
        result['material_assignment'] = assignment
        if assignment['status'] != 'declared' or len(active) != 1:
            return refuse('material_assignment_missing_or_ambiguous')
        binding = active[0]
        declared = binding['material']
        group = declared.get('profile_set') if declared['type'] == 'IfcMaterialProfileSetUsage' else declared
        if (group and group['type'] == 'IfcMaterialProfileSet' and len(group['profiles']) > 1
                and (group.get('composite_profile_id') or len({p['material']['id'] for p in group['profiles']}) > 1)):
            try:
                from .ifc_composite_materials import measure_composite
            except ImportError:
                from ifc_composite_materials import measure_composite
            return measure_composite(doc, element, binding, group, scale, result, mesh_sink)
        material, mapping = single_material(binding, element)
        meshes = []
        inspected = inspect_shapes(doc, [element], scale, mesh_sink=meshes)
        host = inspected['objects'][0]
        result['host_geometry'] = host
        if host['volume_m3'] is None or host['volume_m3'] <= 0 or len(meshes) != 1:
            return refuse('member_body_mesh_not_verified')
        mesh = meshes[0]
        if len(mesh['faces']) > 20000:
            return refuse('input_triangle_budget')
        vertices, remap = np.unique(mesh['vertices'], axis=0, return_inverse=True)
        faces = remap[mesh['faces']]
        if math.fsum(s['signed_volume_m3'] for s in host['topology']['shells']) < 0:
            faces = faces[:, ::-1]
        # Existing downstream contracts use layer_id for source slices. Here it
        # identifies the actual IFC material definition; it is not an invented layer.
        row = {'layer_id':binding['material']['id'], 'source_slice_kind':'whole_member_material',
               'material_id':material['id'], 'material_name':material['name'], 'thickness_m':None,
               'envelope_volume_m3':host['volume_m3'], 'mesh_check':host}
        result.update(status='measured', layers=[row], host_volume_m3=host['volume_m3'],
                      total_layer_envelope_m3=host['volume_m3'], source_relation_id=binding['relation_id'],
                      layer_reference={**mapping,'source_scope':binding['scope'],'source_relation_id':binding['relation_id'],
                                       'source_owner_id':binding['owner_id'],'coordinate_system':'product_local_body'},
                      material_mapping=mapping)
        if mesh_sink is not None:
            mesh_sink.append({'vertices':vertices,'faces':faces})
        return result
    except (ValueError, RuntimeError, TypeError, AttributeError, OverflowError) as exc:
        return refuse(str(exc) if isinstance(exc, ValueError) else 'member_material_geometry_unverified')
