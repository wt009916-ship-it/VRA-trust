"""Closed source polyhedra, including sloping faces; no prism approximation."""
from collections import Counter, defaultdict, deque
import numpy as np
from shapely.geometry import Polygon
from shapely.ops import unary_union

from . import core


def from_mesh(vertices, triangles):
    from .model_geometry import frame, face_points, simple_pieces
    v = np.asarray(vertices, dtype=float).reshape(-1, 3)
    f = np.asarray(triangles, dtype=int).reshape(-1, 3)
    if not len(v) or len(v) > 100000 or len(f) > 100000:
        raise ValueError('源实体网格为空或超过处理预算')
    # Weld equal exporter vertices at 0.1 micrometre, recording that precision.
    indices, points = {}, []
    remap = []
    for p in v:
        key = tuple(np.round(p, 7))
        if key not in indices:
            indices[key] = len(points)
            points.append(key)
        remap.append(indices[key])
    faces, edges = [], defaultdict(list)
    for triangle in f:
        t = [remap[i] for i in triangle]
        if len(set(t)) < 3:
            continue
        p = np.asarray([points[i] for i in t])
        if np.linalg.norm(np.cross(p[1]-p[0], p[2]-p[0])) < 1e-12:
            continue
        n = len(faces)
        faces.append(t)
        for a, b in zip(t, t[1:]+t[:1]):
            edges[tuple(sorted((a, b)))].append((n, a < b))
    if any(len(items) != 2 for items in edges.values()):
        raise ValueError('源实体网格不闭合或非流形，不能恢复热体积')
    adjacent = defaultdict(list)
    for items in edges.values():
        (a, da), (b, db) = items
        adjacent[a].append((b, da == db))
        adjacent[b].append((a, da == db))
    flips, q = {0: False}, deque([0])
    while q:
        a = q.popleft()
        for b, reverse in adjacent[a]:
            value = flips[a] ^ reverse
            if b in flips and flips[b] != value:
                raise ValueError('源实体不可定向')
            if b not in flips:
                flips[b] = value
                q.append(b)
    if len(flips) != len(faces):
        raise ValueError('一个空间包含多个分离壳体，须明确拆分空间')
    xyz = [[list(points[i]) for i in (list(reversed(t)) if flips[n] else t)] for n, t in enumerate(faces)]
    if volume(xyz) < 0:
        xyz = [list(reversed(r)) for r in xyz]
    groups = defaultdict(list)
    for ring in xyz:
        plane = frame(ring)
        groups[(plane['key'], plane['side'])].append(plane)
    shell = []
    for planes in groups.values():
        p = planes[0]
        for part in simple_pieces(unary_union([s['poly'] for s in planes])):
            shell.append({'points': face_points(part, p)})
    validate(shell)
    return shell


def volume(rings):
    total = 0.
    for ring in rings:
        p = np.asarray(ring, dtype=float)
        for i in range(1, len(p)-1):
            total += float(p[0] @ np.cross(p[i], p[i+1]))/6
    return total


def validate(shell):
    from .model_geometry import frame
    if not 4 <= len(shell) <= 2000:
        raise ValueError('空间实体须有4–2000个平面')
    edges = Counter()
    for face in shell:
        ring = face['points']
        frame(ring)
        keys = [tuple(round(float(v), 7) for v in p) for p in ring]
        for a, b in zip(keys, keys[1:]+keys[:1]):
            edges[(a, b)] += 1
    # Coplanar dissolution may introduce T junctions; Honeybee checks the closed
    # polyface using its edge subdivision rather than assuming identical rings.
    from ladybug_geometry.geometry3d import Face3D, Point3D, Polyface3D
    poly = Polyface3D.from_faces([Face3D(tuple(Point3D(*p) for p in f['points'])) for f in shell], 1e-6)
    if not poly.is_solid or volume([f['points'] for f in shell]) <= 1e-6:
        raise ValueError('空间壳体未闭合、方向错误或体积为零')
    return poly


def footprint(shell):
    from .model_geometry import frame
    floors = []
    for face in shell:
        p = frame(face['points'])
        if (p['normal']*p['side'])[2] < -.5:
            floors.append(Polygon([(x, y) for x, y, _ in face['points']]))
    shape = unary_union(floors)
    if shape.geom_type != 'Polygon' or not shape.is_valid or shape.area < .05:
        raise core.ValidationError('源实体没有单一可核对的地板投影')
    return shape
