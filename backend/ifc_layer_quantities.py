"""Planar wall layer envelopes clipped from the actual voided mesh, not volume ratios."""
import math
from pathlib import Path

import numpy as np

try:
    from .ifc_details import material_declarations, project_units, unit_scale
    from .ifc_geometry import inspect_shapes, mesh_measurements
except ImportError:
    from ifc_details import material_declarations, project_units, unit_scale
    from ifc_geometry import inspect_shapes, mesh_measurements


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
            'limitations':['只测单个直线参考轴墙体的分层几何包络；不合并其他构件或套用施工计量扣减规范。',
                '空腔、龙骨等非均质层包络不等于实物材料净量；采购数量、实体比例、密度须另有依据。',
                '原生三角化和布尔切分为近似几何，材料性能、真实施工及工程合规未核验。']}
    def refuse(reason):
        result.update(reason=reason,layers=[],total_layer_envelope_m3=None)
        return result
    if not element.is_a('IfcWall'):
        return refuse('wall_layer_reference_not_supported')
    units=project_units(projects[0]);lengths=units.get('LENGTHUNIT',[])
    if len(lengths)!=1:return refuse('length_unit_unavailable')
    scale=unit_scale(lengths[0],'LENGTHUNIT')
    assignment=material_declarations(element,units)['material_assignment']
    active=[r for r in assignment['associations'] if r['selection']=='effective_declaration']
    if assignment['status']!='declared' or len(active)!=1:
        return refuse('material_assignment_missing_or_ambiguous')
    binding=active[0];usage=binding['material']
    if usage['type']!='IfcMaterialLayerSetUsage' or usage['direction']!='AXIS2' or usage['sense'] not in {'POSITIVE','NEGATIVE'}:
        return refuse('wall_layer_usage_not_supported')
    layers=usage['layer_set']['layers']
    if not 1<=len(layers)<=32:return refuse('layer_count_out_of_range')
    if any(r['type']!='IfcMaterialLayer' or r['thickness']['value_m'] is None or r['thickness']['value_m']<=0
           or r['material']['type']!='IfcMaterial' for r in layers):
        return refuse('layer_thickness_or_material_unavailable')
    axes=[r for r in element.Representation.Representations if r.RepresentationIdentifier=='Axis'] if element.Representation else []
    if len(axes)!=1 or len(axes[0].Items)!=1 or not axes[0].Items[0].is_a('IfcPolyline'):
        return refuse('straight_reference_axis_required')
    points=axes[0].Items[0].Points
    if len(points)!=2 or any(len(p.Coordinates)!=2 for p in points):
        return refuse('two_point_planar_reference_axis_required')
    a,b=(np.array(p.Coordinates,dtype=float)*scale for p in points)
    if not np.isfinite([a,b]).all() or b[0]<=a[0] or abs(b[1]-a[1])>1e-10:
        return refuse('reference_axis_must_follow_local_positive_x')
    offset=usage['offset_raw']
    if not isinstance(offset,(float,int)) or not math.isfinite(offset):
        return refuse('invalid_layer_offset')
    cursor=a[1]+offset*scale;sense=1 if usage['sense']=='POSITIVE' else -1
    planes=[]
    for layer in layers:
        end=cursor+sense*layer['thickness']['value_m'];planes.append((min(cursor,end),max(cursor,end)));cursor=end
    meshes=[];inspected=inspect_shapes(doc,[element],scale,mesh_sink=meshes)
    host=inspected['objects'][0];result['host_geometry']=host
    if host['volume_m3'] is None or host['volume_m3']<=0 or len(meshes)!=1:
        return refuse('host_mesh_not_verified')
    mesh=meshes[0]
    if len(mesh['faces'])>20000:return refuse('input_triangle_budget')
    vertices,remap=np.unique(mesh['vertices'],axis=0,return_inverse=True);faces=remap[mesh['faces']]
    if math.fsum(s['signed_volume_m3'] for s in host['topology']['shells'])<0:faces=faces[:,::-1]
    low=min(p[0] for p in planes);high=max(p[1] for p in planes)
    tolerance_m=max(1e-9,(high-low)*1e-8)
    if abs(vertices[:,1].min()-low)>tolerance_m or abs(vertices[:,1].max()-high)>tolerance_m:
        return refuse('layer_envelope_does_not_match_body')
    solid=manifold.Manifold(manifold.Mesh64(np.ascontiguousarray(vertices,dtype=np.float64),np.ascontiguousarray(faces,dtype=np.uint64)))
    tolerance_m3=max(1e-9,host['volume_m3']*1e-8)
    if solid.status()!=manifold.Error.NoError or not math.isfinite(solid.volume()) or abs(solid.volume()-host['volume_m3'])>tolerance_m3:
        return refuse('boolean_operand_not_verified')
    result['source_relation_id']=binding['relation_id'];result['layer_set_id']=usage['layer_set']['id']
    rows=[];triangles=0;clipped_meshes=[]
    try:
        for layer,(lo,hi) in zip(layers,planes):
            cut=solid.trim_by_plane((0.,1.,0.),lo).trim_by_plane((0.,-1.,0.),-hi)
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
                'thickness_m':layer['thickness']['value_m'],'bounds_local_y_m':[lo,hi],
                'envelope_volume_m3':value,'mesh_check':check})
    except (RuntimeError,ValueError,OverflowError):
        return refuse('layer_boolean_failed')
    total=math.fsum(r['envelope_volume_m3'] for r in rows)
    if abs(total-host['volume_m3'])>tolerance_m3:return refuse('layer_volume_conservation_failed')
    if mesh_sink is not None:mesh_sink.extend(clipped_meshes)
    result.update(status='measured',layers=rows,total_layer_envelope_m3=total,host_volume_m3=host['volume_m3'],
                  numeric_consistency_tolerance_m3=tolerance_m3)
    return result
