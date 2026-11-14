"""Read one IFC beam's explicit constant swept profile, never infer a beam model."""
import math
from pathlib import Path

import numpy as np

try:
    from .beam_sections import properties
    from .ifc_details import unit_scale
    from .ifc_union import placement_chain
except ImportError:
    from beam_sections import properties
    from ifc_details import unit_scale
    from ifc_union import placement_chain


def rigid_scale(matrix, allow_scale=False):
    matrix = np.asarray(matrix, dtype=float)
    if matrix.shape != (4, 4) or not np.isfinite(matrix).all() or not np.allclose(matrix[3], [0, 0, 0, 1], atol=1e-12, rtol=0):
        raise ValueError('invalid_profile_transform')
    basis = matrix[:3, :3]
    scale = float(np.linalg.norm(basis[:, 0]))
    if not math.isfinite(scale) or scale <= 0 or not np.allclose((basis/scale).T@(basis/scale), np.eye(3), atol=1e-12, rtol=1e-12):
        raise ValueError('nonuniform_or_singular_profile_transform')
    if np.linalg.det(basis) <= 0:
        raise ValueError('reflected_profile_transform')
    if not allow_scale and not math.isclose(scale, 1., abs_tol=1e-12, rel_tol=0):
        raise ValueError('nonrigid_profile_placement')
    return scale


def profile_input(profile, scale):
    if profile.ProfileType != 'AREA':
        raise ValueError('profile_is_not_area')
    kind = profile.is_a()
    fields = {
        'IfcRectangleProfileDef': ('rectangle', {'b': 'XDim', 'h': 'YDim'}),
        'IfcCircleProfileDef': ('circle', {'r': 'Radius'}),
        'IfcRectangleHollowProfileDef': ('rectangular_hollow', {'b':'XDim', 'h':'YDim', 't':'WallThickness'}),
        'IfcCircleHollowProfileDef': ('circular_hollow', {'r':'Radius', 't':'WallThickness'}),
        'IfcIShapeProfileDef': ('i_section', {'b':'OverallWidth', 'h':'OverallDepth', 'tw':'WebThickness', 'tf':'FlangeThickness', 'r':'FilletRadius'}),
    }
    if kind not in fields:
        raise ValueError('unsupported_profile_type:'+kind)
    # Omitting optional radii means none per the IFC profile definition, not a missing required dimension.
    for field in ('InnerFilletRadius', 'OuterFilletRadius', 'FlangeEdgeRadius', 'FlangeSlope'):
        value = getattr(profile, field, None)
        if value is not None and (not math.isfinite(value) or value != 0):
            raise ValueError('unsupported_profile_detail:'+field)
    label, mapping = fields[kind]
    raw = {key: getattr(profile, attr) for key, attr in mapping.items()}
    if label == 'i_section' and raw['r'] is None:
        raw['r'] = 0.
    if any(type(v) not in (float, int) or not math.isfinite(v) for v in raw.values()):
        raise ValueError('invalid_or_missing_profile_dimension')
    dimensions = {k: v*scale for k, v in raw.items()}
    result = properties(label, dimensions)
    return {'kind': label, 'dimensions': dimensions, 'unit': 'm'}, result, raw


def extract(doc, product_id):
    from ifcopenshell.util.placement import get_axis2placement, get_mappeditem_transformation
    if type(product_id) is not int or not 0 < product_id <= 2147483647:
        raise ValueError('invalid_product_id')
    element = doc.by_id(product_id)
    if not element.is_a('IfcBeam'):
        raise ValueError('selected_product_is_not_ifc_beam')
    result = {'product_id': element.id(), 'global_id': element.GlobalId, 'ifc_type': element.is_a(),
              'name': element.Name, 'status': 'unsupported', 'section_profile': None,
              'section_properties': None, 'extrusion_length_m': None, 'engineering_span_m': None,
              'elastic_modulus_pa': None, 'supports': None, 'loads': None,
              'source_kind': 'MODEL_GEOMETRY_NOT_MEASURED', 'structural_safety': 'NOT_ASSESSED',
              'issues': [], 'limitations': [
                  '挤出长度是模型实体长度，不是支承间距或工程跨度。',
                  '轮廓主轴只描述模型几何；必须明确弯曲轴、支承、材料模量及荷载依据。',
                  '不从材料名称、空间接触或构件类别推断力学参数；没有安全/规范验算。',
                  '截面只来自选定Body轮廓，不把材料类型声明或包围盒当作受力截面。']}
    try:
        projects = doc.by_type('IfcProject')
        if len(projects) != 1:
            raise ValueError('exactly_one_project_required')
        units = projects[0].UnitsInContext
        length_units = [u for u in units.Units if getattr(u, 'UnitType', None) == 'LENGTHUNIT'] if units else []
        if len(length_units) != 1:
            raise ValueError('missing_or_conflicting_length_units')
        scale = unit_scale(length_units[0], 'LENGTHUNIT')
        if list(element.HasOpenings) or list(getattr(element, 'HasProjections', ())):
            raise ValueError('voided_or_projected_beam_not_constant_section')
        body = [r for r in element.Representation.Representations if r.RepresentationIdentifier == 'Body'] if element.Representation else []
        if len(body) != 1 or len(body[0].Items) != 1:
            raise ValueError('one_body_one_item_required')
        item, mapping, path = body[0].Items[0], np.eye(4), []
        while item.is_a('IfcMappedItem'):
            if item.id() in path or len(path) >= 8:
                raise ValueError('cyclic_or_deep_profile_mapping')
            path.append(item.id())
            transform = get_mappeditem_transformation(item)
            rigid_scale(transform, allow_scale=True)
            mapping = mapping@transform
            children = item.MappingSource.MappedRepresentation.Items
            if len(children) != 1:
                raise ValueError('one_mapped_item_required')
            item = children[0]
        map_scale = rigid_scale(mapping, allow_scale=True)
        if item.is_a() != 'IfcExtrudedAreaSolid':
            raise ValueError('constant_straight_extruded_solid_required:'+item.is_a())
        direction = np.asarray(item.ExtrudedDirection.DirectionRatios, dtype=float)
        if direction.shape != (3,) or not np.isfinite(direction).all() or np.linalg.norm(direction) <= 1e-12:
            raise ValueError('invalid_extrusion_direction')
        direction = direction/np.linalg.norm(direction)
        if abs(direction[0]) > 1e-12 or abs(direction[1]) > 1e-12 or not math.isclose(abs(direction[2]), 1., abs_tol=1e-12):
            raise ValueError('oblique_extrusion_not_supported')
        length = float(item.Depth)*scale*map_scale
        if not math.isfinite(length) or not 1e-6 <= length <= 1e4:
            raise ValueError('invalid_extrusion_length')
        profile = item.SweptArea
        profile_values, section, raw = profile_input(profile, scale*map_scale)
        placement = np.eye(4)
        for local in placement_chain(element.ObjectPlacement):
            rigid_scale(local)
            placement = placement@local
        solid_position = get_axis2placement(item.Position) if item.Position else np.eye(4)
        rigid_scale(solid_position)
        profile_position = get_axis2placement(profile.Position) if profile.Position else np.eye(4)
        rigid_scale(profile_position)
        world = placement@mapping@solid_position@profile_position
        rigid_scale(world, allow_scale=True)
        basis = world[:3, :3]/map_scale
        origin = world[:3, 3]*scale
        if np.max(np.abs(origin)) > 1e9:
            raise ValueError('profile_world_coordinate_range')
        result.update(status='extracted', section_profile=profile_values, section_properties=section,
                      extrusion_length_m=length, axes_world={'x':basis[:, 0].tolist(), 'y':basis[:, 1].tolist(),
                      'extrusion':((placement@mapping@solid_position)[:3, :3].dot(direction)/map_scale).tolist()},
                      centroid_start_world_m=origin.tolist(),
                      source={'representation_id':body[0].id(), 'item_path':[*path,item.id()],
                              'profile_id':profile.id(), 'profile_type':profile.is_a(), 'profile_name':profile.ProfileName,
                              'profile_dimensions_native':raw, 'length_unit_id':length_units[0].id(),
                              'length_unit_definition':str(length_units[0]), 'length_scale_to_m':scale,
                              'mapping_scale':map_scale, 'effective_dimension_scale_to_m':scale*map_scale})
    except (ValueError, TypeError, AttributeError, RuntimeError, IndexError, np.linalg.LinAlgError) as exc:
        result['issues'] = [str(exc)[:300]]
    return result


def inspect_beam(path, product_id):
    import ifcopenshell
    path = Path(path)
    if path.suffix.lower() != '.ifc' or not 0 < path.stat().st_size <= 10*1024**2:
        raise ValueError('IFC input size or type invalid')
    doc = ifcopenshell.open(str(path))
    if len(doc.by_type('IfcProduct')) > 10000:
        raise ValueError('IFC product budget exceeded')
    return extract(doc, product_id)
