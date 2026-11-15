"""Wall and planar slab/plate layers clipped from voided meshes in their actual reference frame."""
import math
from pathlib import Path

import numpy as np

try:
    from .ifc_details import material_declarations, project_units, unit_scale
    from .ifc_geometry import inspect_shapes, mesh_measurements
except ImportError:
    from ifc_details import material_declarations, project_units, unit_scale
    from ifc_geometry import inspect_shapes, mesh_measurements



def slab_reference(element, scale):
    """IFC slab/plate layers use the extruded profile plane, not product-local Z.

    Clipping may change the body but must retain one unambiguous swept base.
    Mapped/composite/BRep-only references are not guessed from a bounding box.
    """
    bodies = [r for r in element.Representation.Representations if r.RepresentationIdentifier == 'Body'] if element.Representation else []
    if len(bodies) != 1 or len(bodies[0].Items) != 1:
        raise ValueError('slab_single_body_reference_required')
    item, seen = bodies[0].Items[0], set()
    while item.is_a('IfcBooleanClippingResult'):
        if item.id() in seen or len(seen) >= 32 or item.Operator != 'DIFFERENCE' or not item.SecondOperand.is_a('IfcHalfSpaceSolid'):
            raise ValueError('slab_clipping_reference_ambiguous')
        seen.add(item.id()); item = item.FirstOperand
    if not item.is_a('IfcExtrudedAreaSolid'):
        raise ValueError('slab_extruded_profile_reference_required')
    position = item.Position
    if position is None or not position.is_a('IfcAxis2Placement3D'):
        raise ValueError('slab_profile_position_required')
    origin = np.array(position.Location.Coordinates, dtype=float)
    normal = np.array(position.Axis.DirectionRatios if position.Axis else (0., 0., 1.), dtype=float)
    x = np.array(position.RefDirection.DirectionRatios if position.RefDirection else (1., 0., 0.), dtype=float)
    if any(v.shape != (3,) or not np.isfinite(v).all() for v in (origin, normal, x)):
        raise ValueError('slab_profile_position_invalid')
    nlen, xlen = np.linalg.norm(normal), np.linalg.norm(x)
    if not math.isfinite(nlen*xlen) or min(nlen, xlen) <= 1e-12:
        raise ValueError('slab_profile_axes_invalid')
    normal /= nlen; x /= xlen
    if np.linalg.norm(np.cross(normal, x)) <= 1e-12:
        raise ValueError('slab_profile_axes_parallel')
    origin *= scale
    if not np.isfinite(origin).all() or np.max(np.abs(origin)) > 1e9:
        raise ValueError('slab_reference_coordinate_range')
    return normal, float(np.dot(origin, normal)), {'coordinate_system':'extruded_solid_position',
        'axis':'AXIS3', 'solid_id':item.id(), 'position_id':position.id(),
        'origin_product_local_m':origin.tolist(), 'normal_product_local':normal.tolist()}



def inspect_slab_in_reference_frame(doc, element, reference, scale, mesh_sink):
    """Rigid re-expression of direct swept solids; source document is never edited.

    Native face triangulation after a rotated boolean can emit different floating
    coordinates for one vertex. Compute in the actual profile frame and apply
    one matrix to the resulting shared vertices. No welding tolerance or repair.
    Unsupported opening representations keep the ordinary conservative path.
    """
    import ifcopenshell
    from ifcopenshell.util.placement import get_axis2placement
    try:
        from .ifc_union import placement_chain, relative_placement
    except ImportError:
        from ifc_union import placement_chain, relative_placement
    bodies = [r for r in element.Representation.Representations if r.RepresentationIdentifier == 'Body']
    if len(bodies) != 1 or len(bodies[0].Items) != 1 or not bodies[0].Items[0].is_a('IfcExtrudedAreaSolid'):
        return inspect_shapes(doc, [element], scale, mesh_sink=mesh_sink)
    openings = list(element.HasOpenings)
    if len(openings) > 64:
        raise ValueError('slab_opening_reference_budget')
    chain = placement_chain(element.ObjectPlacement)
    origin, basis = chain[0][:3, 3], chain[0][:3, :3]
    host = relative_placement(chain, origin, scale, basis)
    base = get_axis2placement(doc.by_id(reference['solid_id']).Position)
    base[:3, 3] *= scale
    if not np.allclose(base[:3, :3].T @ base[:3, :3], np.eye(3), atol=1e-12, rtol=0):
        raise ValueError('slab_nonrigid_reference')
    inverse = np.linalg.inv(base)
    opening_positions = []
    for relation in openings:
        opening = relation.RelatedOpeningElement
        reps = [r for r in opening.Representation.Representations if r.RepresentationIdentifier == 'Body'] if opening.Representation else []
        if len(reps) != 1 or len(reps[0].Items) != 1 or not reps[0].Items[0].is_a('IfcExtrudedAreaSolid'):
            return inspect_shapes(doc, [element], scale, mesh_sink=mesh_sink)
        solid = reps[0].Items[0]
        if solid.Position is None:
            return inspect_shapes(doc, [element], scale, mesh_sink=mesh_sink)
        position = get_axis2placement(solid.Position); position[:3, 3] *= scale
        relative = np.linalg.inv(host) @ relative_placement(placement_chain(opening.ObjectPlacement), origin, scale, basis)
        matrix = inverse @ relative @ position
        if not np.isfinite(matrix).all() or not np.allclose(matrix[:3, :3].T @ matrix[:3, :3], np.eye(3), atol=1e-12, rtol=0):
            raise ValueError('slab_opening_nonrigid_reference')
        opening_positions.append((opening.id(), solid.id(), matrix))
    clone = ifcopenshell.file.from_string(doc.to_string())
    target = clone.by_id(element.id())
    def axis(matrix):
        return clone.create_entity('IfcAxis2Placement3D',
            Location=clone.create_entity('IfcCartesianPoint', Coordinates=tuple(float(v/scale) for v in matrix[:3, 3])),
            Axis=clone.create_entity('IfcDirection', DirectionRatios=tuple(float(v) for v in matrix[:3, 2])),
            RefDirection=clone.create_entity('IfcDirection', DirectionRatios=tuple(float(v) for v in matrix[:3, 0])))
    clone.by_id(reference['solid_id']).Position = axis(np.eye(4))
    for opening_id, solid_id, matrix in opening_positions:
        opening, solid = clone.by_id(opening_id), clone.by_id(solid_id)
        opening.ObjectPlacement = target.ObjectPlacement
        # Opening occurrences may share a solid/representation at different
        # placements. Give each transformed occurrence private geometry.
        replacement = clone.create_entity('IfcExtrudedAreaSolid', SweptArea=solid.SweptArea,
            Position=axis(matrix), ExtrudedDirection=solid.ExtrudedDirection, Depth=solid.Depth)
        old_shape = opening.Representation
        reps = []
        for rep in old_shape.Representations:
            reps.append(clone.create_entity('IfcShapeRepresentation', ContextOfItems=rep.ContextOfItems,
                RepresentationIdentifier=rep.RepresentationIdentifier, RepresentationType=rep.RepresentationType,
                Items=[replacement]) if rep.RepresentationIdentifier == 'Body' else rep)
        opening.Representation = clone.create_entity('IfcProductDefinitionShape', Name=old_shape.Name,
            Description=old_shape.Description, Representations=reps)
    normalized = []
    inspected = inspect_shapes(clone, [target], scale, mesh_sink=normalized)
    row = inspected['objects'][0]
    row['rigid_reference_normalization'] = {'source_position_id':reference['position_id'],
        'method':'native_boolean_in_profile_frame_then_shared_vertex_rigid_transform',
        'source_document_modified':False, 'tolerance_welding':False}
    if row['volume_m3'] is None or len(normalized) != 1:
        return inspected
    mesh = normalized[0]
    vertices = mesh['vertices'] @ base[:3, :3].T + base[:3, 3]
    checked = mesh_measurements(vertices, mesh['faces'])
    expected = row['volume_m3']
    row.update(checked)
    if checked['volume_m3'] is None or abs(checked['volume_m3']-expected) > max(1e-9, expected*1e-8):
        row.update(volume_m3=None, status='reference_transform_unverified')
        return inspected
    world = np.array(row['placement_matrix_si'])
    points = vertices @ world[:3, :3].T + world[:3, 3]
    row['bbox_world_m'] = {'min':points.min(axis=0).tolist(), 'max':points.max(axis=0).tolist()}
    mesh_sink.append({**mesh, 'vertices':vertices})
    return inspected


def measure_layers(path, product_id, *, mesh_sink=None, _document=None):
    import ifcopenshell
    import manifold3d as manifold

    if type(product_id) is not int or not 0 < product_id <= 2147483647:
        raise ValueError('Explicit IFC product ID required')
    path=Path(path)
    if path.suffix.lower()!='.ifc' or not 0 < path.stat().st_size <= 10*1024**2:
        raise ValueError('IFC source must be 1 byte..10 MiB')
    doc=_document if _document is not None else ifcopenshell.open(str(path));projects=doc.by_type('IfcProject');products=doc.by_type('IfcProduct')
    if len(projects)!=1 or len(products)>10000:
        raise ValueError('Exactly one project and at most 10000 products required')
    gids=[p.GlobalId for p in products]
    if any(not gid for gid in gids) or len(set(gids))!=len(gids):
        raise ValueError('Missing or duplicate GlobalId')
    element=doc.by_id(product_id)
    result={'status':'unavailable','product_id':product_id,'layers':[], 'reason':None,
            'total_layer_envelope_m3':None,'host_volume_m3':None,
            'method':'voided_mesh_clipped_at_declared_layer_planes',
            'quantity_kind':'model_layer_envelope_after_ifc_openings',
            'limitations':['测单个直线参考轴墙或具有明确挤出参考面的楼板/屋面板/板材分层包络；不套用施工计量规则。',
                '空腔、龙骨等非均质层包络不等于实物材料净量；采购数量、实体比例、密度须另有依据。',
                '原生三角化和布尔切分为近似几何，材料性能、真实施工及工程合规未核验。']}
    def refuse(reason):
        result.update(reason=reason,layers=[],total_layer_envelope_m3=None)
        return result
    wall = element.is_a('IfcWall')
    if not (wall or element.is_a('IfcSlab') or element.is_a('IfcPlate')):
        return refuse('element_layer_reference_not_supported')
    units=project_units(projects[0]);lengths=units.get('LENGTHUNIT',[])
    if len(lengths)!=1:return refuse('length_unit_unavailable')
    scale=unit_scale(lengths[0],'LENGTHUNIT')
    assignment=material_declarations(element,units)['material_assignment']
    active=[r for r in assignment['associations'] if r['selection']=='effective_declaration']
    if assignment['status']!='declared' or len(active)!=1:
        return refuse('material_assignment_missing_or_ambiguous')
    binding=active[0];usage=binding['material']
    if usage['type']!='IfcMaterialLayerSetUsage' or usage['direction']!=('AXIS2' if wall else 'AXIS3') or usage['sense'] not in {'POSITIVE','NEGATIVE'}:
        return refuse('wall_layer_usage_not_supported' if wall else 'slab_layer_usage_not_supported')
    layers=usage['layer_set']['layers']
    if not 1<=len(layers)<=32:return refuse('layer_count_out_of_range')
    if any(r['type']!='IfcMaterialLayer' or r['thickness']['value_m'] is None or r['thickness']['value_m']<=0
           or r['material']['type']!='IfcMaterial' for r in layers):
        return refuse('layer_thickness_or_material_unavailable')
    if wall:
        axes=[r for r in element.Representation.Representations if r.RepresentationIdentifier=='Axis'] if element.Representation else []
        if len(axes)!=1 or len(axes[0].Items)!=1 or not axes[0].Items[0].is_a('IfcPolyline'):
            return refuse('straight_reference_axis_required')
        points=axes[0].Items[0].Points
        if len(points)!=2 or any(len(p.Coordinates)!=2 for p in points):
            return refuse('two_point_planar_reference_axis_required')
        a,b=(np.array(p.Coordinates,dtype=float)*scale for p in points)
        if not np.isfinite([a,b]).all() or b[0]<=a[0] or abs(b[1]-a[1])>1e-10:
            return refuse('reference_axis_must_follow_local_positive_x')
        normal = np.array([0., 1., 0.]); base_distance = float(a[1])
        reference = {'coordinate_system':'product_axis_line', 'axis':'AXIS2', 'axis_representation_id':axes[0].id(),
                     'normal_product_local':normal.tolist(), 'base_distance_m':base_distance}
    else:
        try:
            normal, base_distance, reference = slab_reference(element, scale)
        except (ValueError, TypeError, AttributeError, OverflowError) as error:
            return refuse(str(error) if isinstance(error, ValueError) else 'slab_profile_reference_invalid')
    offset=usage['offset_raw']
    if not isinstance(offset,(float,int)) or not math.isfinite(offset):
        return refuse('invalid_layer_offset')
    cursor=base_distance+offset*scale;sense=1 if usage['sense']=='POSITIVE' else -1
    reference.update(offset_m=offset*scale, direction_sense=usage['sense'])
    result['layer_reference']=reference
    planes=[]
    for layer in layers:
        end=cursor+sense*layer['thickness']['value_m'];planes.append((min(cursor,end),max(cursor,end)));cursor=end
    meshes=[]
    try:
        inspected = inspect_shapes(doc,[element],scale,mesh_sink=meshes) if wall else inspect_slab_in_reference_frame(doc,element,reference,scale,meshes)
    except (ValueError, RuntimeError, TypeError, AttributeError, np.linalg.LinAlgError):
        return refuse('slab_reference_normalization_unavailable')
    host=inspected['objects'][0];result['host_geometry']=host
    if host['volume_m3'] is None or host['volume_m3']<=0 or len(meshes)!=1:
        return refuse('host_mesh_not_verified')
    mesh=meshes[0]
    if len(mesh['faces'])>20000:return refuse('input_triangle_budget')
    vertices,remap=np.unique(mesh['vertices'],axis=0,return_inverse=True);faces=remap[mesh['faces']]
    if math.fsum(s['signed_volume_m3'] for s in host['topology']['shells'])<0:faces=faces[:,::-1]
    low=min(p[0] for p in planes);high=max(p[1] for p in planes)
    tolerance_m=max(1e-9,(high-low)*1e-8)
    if abs((vertices @ normal).min()-low)>tolerance_m or abs((vertices @ normal).max()-high)>tolerance_m:
        return refuse('layer_envelope_does_not_match_body')
    solid=manifold.Manifold(manifold.Mesh64(np.ascontiguousarray(vertices,dtype=np.float64),np.ascontiguousarray(faces,dtype=np.uint64)))
    tolerance_m3=max(1e-9,host['volume_m3']*1e-8)
    if solid.status()!=manifold.Error.NoError or not math.isfinite(solid.volume()) or abs(solid.volume()-host['volume_m3'])>tolerance_m3:
        return refuse('boolean_operand_not_verified')
    result['source_relation_id']=binding['relation_id'];result['layer_set_id']=usage['layer_set']['id']
    rows=[];triangles=0;clipped_meshes=[]
    try:
        for layer,(lo,hi) in zip(layers,planes):
            cut=solid.trim_by_plane(tuple(normal),lo).trim_by_plane(tuple(-normal),-hi)
            if cut.status()!=manifold.Error.NoError or cut.is_empty():
                return refuse('layer_intersection_empty_or_unverified')
            triangles+=cut.num_tri()
            if triangles>40000:return refuse('output_triangle_budget')
            clipped=cut.to_mesh64();check=mesh_measurements(clipped.vert_properties[:,:3],clipped.tri_verts)
            value=check['volume_m3']
            if value is None or not math.isfinite(cut.volume()) or abs(value-cut.volume())>tolerance_m3:
                return refuse('layer_mesh_not_verified')
            clipped_meshes.append({'vertices':np.array(clipped.vert_properties[:,:3],copy=True),'faces':np.array(clipped.tri_verts,copy=True)})
            rows.append({'layer_id':layer['id'],'material_id':layer['material']['id'],'material_name':layer['material']['name'],
                'thickness_m':layer['thickness']['value_m'],'bounds_reference_m':[lo-base_distance,hi-base_distance],
                **({'bounds_local_y_m':[lo,hi]} if wall else {}),
                'envelope_volume_m3':value,'mesh_check':check})
    except (RuntimeError,ValueError,OverflowError):
        return refuse('layer_boolean_failed')
    total=math.fsum(r['envelope_volume_m3'] for r in rows)
    if abs(total-host['volume_m3'])>tolerance_m3:return refuse('layer_volume_conservation_failed')
    if mesh_sink is not None:mesh_sink.extend(clipped_meshes)
    result.update(status='measured',layers=rows,total_layer_envelope_m3=total,host_volume_m3=host['volume_m3'],
                  numeric_consistency_tolerance_m3=tolerance_m3)
    return result
