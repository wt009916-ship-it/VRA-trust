"""Bounded native IFC tessellation with explicit approximate measurement semantics."""
import math
from collections import defaultdict

import numpy as np

try:
    from . import mesh_topology
except ImportError:
    import mesh_topology

MAX_VERTICES = 100000
MAX_TRIANGLES = 200000


def mesh_measurements(vertices, faces, topology_budget=None):
    """Origin-shifted integration; never assign volume to open/inconsistently oriented mesh."""
    verts = np.asarray(vertices, dtype=float).reshape((-1, 3))
    tris = np.asarray(faces, dtype=np.int64).reshape((-1, 3))
    if not len(verts) or not len(tris):
        return {'surface_area_m2': None, 'volume_m3': None, 'mesh_status': 'empty_mesh'}
    if len(verts) > MAX_VERTICES or len(tris) > MAX_TRIANGLES:
        raise ValueError('IFC mesh budget exceeded')
    if not np.isfinite(verts).all() or np.max(np.abs(verts)) > 1e12:
        raise ValueError('IFC nonfinite or excessive coordinate')
    if tris.min() < 0 or tris.max() >= len(verts):
        raise ValueError('IFC invalid triangle index')
    # Weld identical coordinates only; no implicit tolerance merges or topology repair.
    verts, remap = np.unique(verts, axis=0, return_inverse=True)
    tris = remap[tris]
    points = verts[tris]
    cross = np.cross(points[:, 1] - points[:, 0], points[:, 2] - points[:, 0])
    areas = np.linalg.norm(cross, axis=1) / 2
    edges = defaultdict(list)
    for i, triangle in enumerate(tris):
        for a, b in zip(triangle, np.roll(triangle, -1)):
            edges[(min(a, b), max(a, b))].append((i, 1 if a < b else -1))
    bad_edges = sum(len(e) != 2 or sum(x[1] for x in e) != 0 for e in edges.values())
    degenerate = int(np.count_nonzero(areas == 0))
    duplicate = len(tris) - len({tuple(sorted(t)) for t in tris})
    volume = None
    components = []
    topology = {'status':'not_checked','reason':'open_or_invalid_topology'}
    if not bad_edges and not degenerate and not duplicate:
        adjacency = [[] for _ in tris]
        for pairs in edges.values():
            a, b = pairs[0][0], pairs[1][0]
            adjacency[a].append(b)
            adjacency[b].append(a)
        unseen = set(range(len(tris)))
        signed_volumes = []
        while unseen:
            todo = [unseen.pop()]
            component = []
            while todo:
                i = todo.pop()
                component.append(i)
                for neighbor in adjacency[i]:
                    if neighbor in unseen:
                        unseen.remove(neighbor)
                        todo.append(neighbor)
            components.append(component)
            p = points[component]
            origin = p[0, 0]
            shifted = p - origin
            terms = np.einsum('ij,ij->i', shifted[:, 0], np.cross(shifted[:, 1], shifted[:, 2])) / 6
            signed_volumes.append(math.fsum(float(v) for v in terms))
        topology = mesh_topology.validate(verts,tris,components,signed_volumes,edges,topology_budget)
        if topology['status']=='checked':volume = abs(math.fsum(signed_volumes))
    area = math.fsum(float(a) for a in areas)
    if not math.isfinite(area) or (volume is not None and not math.isfinite(volume)):
        raise ValueError('IFC measurement overflow')
    return {'surface_area_m2': area, 'volume_m3': volume,
            'mesh_status': 'oriented_edge_closed' if volume is not None else 'open_or_invalid_topology',
            'bad_edges': bad_edges, 'degenerate_triangles': degenerate, 'duplicate_triangles': duplicate,
            'connected_shells': len(components) if components else None,
            'topology':topology,'surface_area_kind':'sum_of_input_triangles_not_union_area',
            'vertices': len(verts), 'triangles': len(tris)}


def inspect_shapes(doc, products, length_scale):
    import ifcopenshell.geom
    from ifcopenshell.util.shape import get_shape_matrix

    settings = ifcopenshell.geom.settings()
    values = {'use-world-coords': False, 'convert-back-units': False, 'weld-vertices': True,
              'mesher-linear-deflection': .001, 'mesher-angular-deflection': .5,
              'disable-opening-subtractions': False}
    for key, value in values.items():
        settings.set(key, value)
    rows = []
    used_vertices = used_triangles = 0
    topology_budget = mesh_topology.Budget()
    for element in products:
        row = {'id': element.id(), 'global_id': element.GlobalId, 'type': element.is_a(), 'name': element.Name,
               'surface_area_m2': None, 'volume_m3': None, 'bbox_world_m': None,
               'measurement_kind': 'approximate_native_tessellation_not_certified_quantity'}
        representation = getattr(element, 'Representation', None)
        reps = list(representation.Representations) if representation else []
        bodies = [r for r in reps if r.RepresentationIdentifier == 'Body']
        row['representation_ids'] = [r.id() for r in bodies]
        row['item_ids'] = [i.id() for r in bodies for i in r.Items]
        if not bodies:
            row['status'] = 'no_body_representation'
        elif len(bodies) != 1:
            row['status'] = 'ambiguous_body_representations'
        elif length_scale is None:
            row['status'] = 'missing_or_unsupported_length_unit'
        elif not element.ObjectPlacement:
            row['status'] = 'missing_placement'
        else:
            try:
                shape = ifcopenshell.geom.create_shape(settings, element, bodies[0])
            except (RuntimeError, ValueError):
                row['status'] = 'native_geometry_failed'
                rows.append(row)
                continue
            verts = np.asarray(shape.geometry.verts, dtype=float).reshape((-1, 3))
            faces = np.asarray(shape.geometry.faces, dtype=np.int64).reshape((-1, 3))
            used_vertices += len(verts)
            used_triangles += len(faces)
            if used_vertices > MAX_VERTICES or used_triangles > MAX_TRIANGLES:
                raise ValueError('IFC total mesh budget exceeded')
            row.update(mesh_measurements(verts, faces, topology_budget))
            if len(verts):
                matrix = get_shape_matrix(shape)
                world = verts @ matrix[:3, :3].T + matrix[:3, 3]
                if not np.isfinite(world).all() or np.max(np.abs(world)) > 1e12:
                    raise ValueError('IFC invalid world coordinates')
                row['bbox_world_m'] = {'min': world.min(axis=0).tolist(), 'max': world.max(axis=0).tolist()}
                row['placement_matrix_si'] = matrix.tolist()
            row['status'] = 'measured_mesh' if row['volume_m3'] is not None else 'partial_mesh'
        rows.append(row)
    return {'objects': rows, 'settings': values, 'vertices_processed': used_vertices, 'triangles_processed': used_triangles,
            'limitations': ['三角网格表面积及定向闭合边界积分体积为近似几何量，不是模型声明工程量或专业认证。',
                           '保留原模型开洞关系；不做跨构件去重叠、相交检查或工程量规则扣减。',
                           '体积须通过边/顶点流形、三角面接触及壳嵌套方向检查；拒绝或预算内未能核验时为未知，不自动修复或布尔合并。',
                           '检查针对原生三角化后的二进制浮点坐标；不能证明原CAD曲面精度或专业净量。面积始终是原网格三角面之和，非去重叠并集面积。',
                           '局部SI坐标用于测量，世界米制包围盒用于定位；未应用地图投影转换。',
                           '仅处理唯一Body表示；缺单位/位置/Body及原生转换失败保持缺口，不默认补齐。']}
