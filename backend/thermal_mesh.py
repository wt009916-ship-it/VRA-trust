"""Conforming heat-transfer faces for EnergyPlus' edge-based closure checks.

Adds existing junction vertices and triangulates affected polygons. No coordinate
snapping, lost slivers, moved room boundaries or changed boundary conditions.
Reciprocal surfaces use the same triangulation even across an explicit wall gap.
"""
import numpy as np
from shapely import constrained_delaunay_triangles

from . import core
from .model_geometry import frame, face_points


def conform(surfaces):
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
    return result
