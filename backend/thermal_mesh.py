"""Conforming heat-transfer faces for EnergyPlus' edge-based closure checks.

Adds existing junction vertices and triangulates affected polygons. No coordinate
snapping, lost slivers, moved room boundaries or changed boundary conditions.
Reciprocal surfaces use the same triangulation even across an explicit wall gap.
"""
from collections import defaultdict
from itertools import product
import numpy as np
from shapely import constrained_delaunay_triangles

from . import core
from .model_geometry import frame, face_points


# IDF coordinates are emitted at six decimal places. Intersection/projection
# residuals must share vertices before checking the geometry sent to the engine.
PRECISION_M = 1e-6
WELD_LIMIT_M = 1e-5


def measures(points):
    xyz = np.asarray(points, dtype=float)
    normal = np.zeros(3)
    volume = 0.
    for i in range(1, len(xyz)-1):
        normal += np.cross(xyz[i]-xyz[0], xyz[i+1]-xyz[0])
        volume += float(xyz[0] @ np.cross(xyz[i], xyz[i+1]))/6
    return float(np.linalg.norm(normal)/2), volume


def engine_vertices(surfaces):
    """Bounded numerical welding, never a source-footprint or boundary-policy edit."""
    points = sorted({tuple(p) for s in surfaces for p in s['points']})
    parents = list(range(len(points)))
    buckets = defaultdict(list)
    def find(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i
    for i, point in enumerate(points):
        cell = tuple(int(np.floor(v/WELD_LIMIT_M)) for v in point)
        for offset in product((-1, 0, 1), repeat=3):
            for j in buckets[tuple(cell[k]+offset[k] for k in range(3))]:
                if np.linalg.norm(np.asarray(point)-points[j]) <= WELD_LIMIT_M:
                    parents[find(i)] = find(j)
        buckets[cell].append(i)
    groups = defaultdict(list)
    for i, point in enumerate(points):
        groups[find(i)].append(point)
    mapping, maximum = {}, 0.
    for group in groups.values():
        representative = np.mean(group, axis=0).round(6).tolist()
        displacement = max(np.linalg.norm(np.asarray(p)-representative) for p in group)
        if displacement > WELD_LIMIT_M:
            raise core.ValidationError('数值顶点归并超过10微米，拒绝代替工程几何修复')
        maximum = max(maximum, float(displacement))
        for point in group:
            mapping[point] = representative
    before, after = defaultdict(lambda: [0., 0.]), defaultdict(lambda: [0., 0.])
    output, collapsed = [], []
    for surface in surfaces:
        zone = surface['zone']
        area, volume = measures(surface['points'])
        before[zone][0] += area
        before[zone][1] += volume
        ring = []
        for point in surface['points']:
            point = mapping[tuple(point)]
            if not ring or point != ring[-1]:
                ring.append(point)
        if len(ring) > 1 and ring[-1] == ring[0]:
            ring.pop()
        new_area, new_volume = measures(ring)
        if len(ring) < 3 or new_area < 5e-11:
            if area > .0001:
                raise core.ValidationError('归并会消除具有实际面积的热面，拒绝发布')
            collapsed.append({'name': surface['name'], 'zone': zone, 'original_area_m2': area})
            continue
        frame(ring)  # Preserve self-intersection and planarity refusals.
        after[zone][0] += new_area
        after[zone][1] += new_volume
        output.append({**surface, 'points': ring})
    names = {s['name'] for s in output}
    if any(s['boundary'] == 'Surface' and s['other'] not in names for s in output):
        raise core.ValidationError('数值归并导致成对热面不一致，拒绝单侧删除')
    changes = []
    for zone, (area, volume) in before.items():
        new_area, new_volume = after[zone]
        if (abs(new_area-area) > max(.0001, area*1e-6) or
                abs(new_volume-volume) > max(.0001, abs(volume)*1e-6)):
            raise core.ValidationError('数值归并面积或体积变化超过绝对/相对限额，拒绝发布：'+zone)
        changes.append({'zone': zone, 'area_before_m2': area, 'area_after_m2': new_area,
                        'volume_before_m3': volume, 'volume_after_m3': new_volume})
    return output, {'coordinate_precision_m': PRECISION_M, 'weld_limit_m': WELD_LIMIT_M,
                    'max_displacement_m': maximum, 'collapsed_faces': collapsed, 'zones': changes,
                    'relative_change_limit': 1e-6, 'absolute_area_change_limit_m2': .0001,
                    'absolute_volume_change_limit_m3': .0001,
                    'basis': 'Numerical intersections and IDF serialization only; source geometry and boundary classes unchanged.'}


def conform(surfaces, *, return_report=False):
    faces = [{**s, 'points': [list(p) for p in s['points']]} for s in surfaces]
    lookup = {s['name']: s for s in faces}
    original = {s['name']: len(s['points']) for s in faces}
    for _ in range(8):
        pools = {}
        for face in faces:
            pools.setdefault(face['zone'], []).extend(face['points'])
        pools = {k: np.unique(np.round(v, 8), axis=0) for k, v in pools.items()}
        changed = False
        for face in faces:
            points = pools[face['zone']]
            if face['boundary'] == 'Surface':
                other = lookup[face['other']]
                plane, op = frame(face['points']), frame(other['points'])
                candidates = pools[other['zone']]
                valid = np.abs(candidates @ op['normal'] - op['distance']) < 1e-7
                shifted = candidates[valid] + plane['normal']*(plane['distance']-op['distance'])
                points = np.unique(np.round(np.concatenate((points, shifted)), 8), axis=0)
            ring, output = face['points'], []
            for a, b in zip(ring, ring[1:]+ring[:1]):
                start, vector = np.array(a), np.array(b)-a
                t = (points-start) @ vector / float(vector @ vector)
                distance = np.linalg.norm(points-(start+t[:, None]*vector), axis=1)
                indices = np.flatnonzero((t > 1e-6) & (t < 1-1e-6) & (distance < 1e-7))
                output.append(a)
                for i in indices[np.argsort(t[indices])]:
                    point = (start+t[i]*vector).tolist()
                    if np.linalg.norm(np.array(point)-output[-1]) > 1e-7:
                        output.append(point)
            if len(output) > len(ring):
                changed = True
                face['points'] = output
        if not changed:
            break
    else:
        raise core.ValidationError('热边界分段未收敛；须拆分复杂邻接后重试')
    result, done = [], set()
    for face in faces:
        if face['name'] in done:
            continue
        done.add(face['name'])
        other = lookup[face['other']] if face['boundary'] == 'Surface' else None
        if other:
            done.add(other['name'])
        split = len(face['points']) != original[face['name']] or (other and len(other['points']) != original[other['name']])
        if not split:
            result.append(face)
            if other:
                result.append(other)
            continue
        plane = frame(face['points'])
        # frame retains collinear boundary vertices, required by constrained triangulation.
        triangles = list(constrained_delaunay_triangles(plane['poly']).geoms)
        if abs(sum(t.area for t in triangles)-plane['poly'].area) > 1e-7:
            raise core.ValidationError('热边界剖分面积不守恒')
        for i, triangle in enumerate(triangles):
            a_name = face['name']+f'_T{i}'
            b_name = other['name']+f'_T{i}' if other else ''
            result.append({**face, 'name': a_name, 'other': b_name,
                           'points': face_points(triangle, plane)})
            if other:
                result.append({**other, 'name': b_name, 'other': a_name,
                               'points': face_points(triangle, frame(other['points']))})
    result, precision = engine_vertices(result)
    # Merge numerical small triangles with a compatible neighbour only when the
    # result is a convex quad retaining every exterior vertex (no T-junction loss).
    for face in list(result):
        if face not in result or face["boundary"] == "Surface":
            continue
        p = frame(face["points"])
        if p["poly"].area >= .001:
            continue
        for other in list(result):
            if other is face or any(face[k] != other[k] for k in ("zone", "kind", "boundary", "construction")):
                continue
            q = frame(other["points"])
            if p["key"] != q["key"] or p["poly"].intersection(q["poly"]).length < .001:
                continue
            union = p["poly"].union(q["poly"])
            if union.geom_type != "Polygon" or union.interiors or len(union.exterior.coords) != 5:
                continue
            xy = list(union.exterior.coords)[:-1]
            crosses = [abs((xy[i][0]-xy[i-1][0])*(xy[(i+1)%4][1]-xy[i][1]) -
                           (xy[i][1]-xy[i-1][1])*(xy[(i+1)%4][0]-xy[i][0])) for i in range(4)]
            if min(crosses) < 1e-8 or union.convex_hull.area-union.area > 1e-8:
                continue
            if abs(union.area-p["poly"].area-q["poly"].area) > 1e-8:
                raise core.ValidationError("热面合并面积不守恒")
            other.update(points=face_points(union, q), boundary_basis=other["boundary_basis"]+"; small coplanar triangle merged without area loss")
            result.remove(face)
            break
    if len(result) > 10000:
        raise core.ValidationError('一致热网格超过 10000 面，请拆分项目')
    precision["output_faces"] = len(result)
    return (result, precision) if return_report else result
