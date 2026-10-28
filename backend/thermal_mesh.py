"""Conforming heat-transfer faces for EnergyPlus' edge-based closure checks.

Adds existing junction vertices and triangulates affected polygons. No coordinate
snapping, lost slivers, moved room boundaries or changed boundary conditions.
Reciprocal surfaces use the same triangulation even across an explicit wall gap.
"""
from collections import Counter, defaultdict
from itertools import product
import numpy as np
from shapely import constrained_delaunay_triangles, points as shapely_points, STRtree
from shapely.geometry import Polygon, box

from . import core
from .model_geometry import frame as source_frame, face_points


# IDF coordinates are emitted at six decimal places. Intersection/projection
# residuals must share vertices before checking the geometry sent to the engine.
PRECISION_M = 1e-6
WELD_LIMIT_M = 1e-5


def frame(points):
    """Stable canonical orientation for nearly axial emitted heat-transfer planes.

    The source boundary projection convention stays unchanged. At this stage a
    tiny first normal component must not flip the UV basis after serialization.
    """
    plane = source_frame(points)
    dominant = int(np.argmax(np.abs(np.round(plane['normal'], 6))))
    if plane['normal'][dominant] >= 0:
        return plane
    normal = -plane['normal']
    axis = np.array([1., 0., 0.]) if abs(normal[2]) > .99 else np.array([-normal[1], normal[0], 0.])
    axis /= np.linalg.norm(axis)
    second = np.cross(normal, axis)
    xyz = np.asarray(points)
    return {**plane, 'normal': normal, 'distance': -plane['distance'], 'side': -plane['side'],
            'axis': axis, 'second': second, 'poly': Polygon(np.column_stack((xyz @ axis, xyz @ second))),
            'key': tuple(np.round(normal, 6))+(-round(plane['distance'], 5),)}


def measures(points):
    xyz = np.asarray(points, dtype=float)
    normal = np.zeros(3)
    volume = 0.
    for i in range(1, len(xyz)-1):
        normal += np.cross(xyz[i]-xyz[0], xyz[i+1]-xyz[0])
        volume += float(xyz[0] @ np.cross(xyz[i], xyz[i+1]))/6
    return float(np.linalg.norm(normal)/2), volume


def engine_vertices(surfaces, *, bounded_chains=False):
    """Bounded numerical welding, never a source-footprint or boundary-policy edit."""
    points = sorted({tuple(p) for s in surfaces for p in s['points']})
    parents = list(range(len(points)))
    members = {i: [i] for i in parents}
    rejected_chains = 0
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
                    left, right = find(i), find(j)
                    if not bounded_chains:
                        parents[left] = right
                        continue
                    if left != right:
                        combined = members[left]+members[right]
                        values = np.asarray([points[k] for k in combined])
                        representative = values.mean(axis=0).round(6)
                        if np.max(np.linalg.norm(values-representative, axis=1)) <= WELD_LIMIT_M:
                            parents[left] = right
                            members[right] = combined
                            del members[left]
                        else:
                            rejected_chains += 1
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
    zone_points = defaultdict(list)
    for surface in surfaces:
        zone_points[surface['zone']].extend(surface['points'])
    origins = {zone: np.mean(values, axis=0) for zone, values in zone_points.items()}
    before, after = defaultdict(lambda: [0., 0.]), defaultdict(lambda: [0., 0.])
    output, collapsed, repaired = [], [], []
    for surface in surfaces:
        zone = surface['zone']
        area, volume = measures(np.asarray(surface['points'])-origins[zone])
        before[zone][0] += area
        before[zone][1] += volume
        ring = []
        for point in surface['points']:
            point = mapping[tuple(point)]
            if not ring or point != ring[-1]:
                ring.append(point)
        if len(ring) > 1 and ring[-1] == ring[0]:
            ring.pop()
        changed = True
        while changed and len(ring) > 3:
            changed = False
            for i in range(len(ring)):
                if ring[i-1] == ring[(i+1) % len(ring)]:
                    ring.pop(i)
                    ring.pop(i % len(ring))
                    changed = True
                    break
        new_area, new_volume = measures(np.asarray(ring)-origins[zone])
        if len(ring) < 3 or new_area < 5e-11:
            if area > .0001:
                raise core.ValidationError('归并会消除具有实际面积的热面，拒绝发布')
            collapsed.append({'name': surface['name'], 'zone': zone, 'original_area_m2': area})
            continue
        try:
            frame(ring)
        except core.ValidationError as exc:
            original_plane = frame(surface.get('_source_convex_points', surface['points']))
            original_shape = original_plane['poly']
            if original_shape.convex_hull.area-original_shape.area > 1e-9:
                raise core.ValidationError('数值归并后面无效，源面非凸，未擅自补面：'+surface['name']) from exc
            from shapely.geometry import Polygon
            xy = [(float(np.dot(p, original_plane['axis'])), float(np.dot(p, original_plane['second']))) for p in ring]
            hull = Polygon(xy).convex_hull
            if hull.geom_type != 'Polygon':
                raise core.ValidationError('数值归并后源凸面退化：'+surface['name']) from exc
            ring = face_points(hull, original_plane)
            displacement = max(min(np.linalg.norm(np.array(p)-q) for q in surface['points']) for p in ring)
            if displacement > WELD_LIMIT_M:
                raise core.ValidationError('源凸面数值修复超过10微米：'+surface['name']) from exc
            maximum = max(maximum, float(displacement))
            repaired.append({'face': surface['name'], 'method': 'restore source convex topology after numerical welding',
                             'max_vertex_displacement_m': float(displacement)})
            frame(ring)
            new_area, new_volume = measures(np.asarray(ring)-origins[zone])
        after[zone][0] += new_area
        after[zone][1] += new_volume
        output.append({**surface, 'points': ring})
    names = {s['name'] for s in output}
    missing = [s for s in output if s['boundary'] == 'Surface' and s['other'] not in names]
    if missing and bounded_chains:
        sources = {s['name']: s for s in surfaces}
        paired_collapse = set()
        for surface in missing:
            source = sources[surface['other']]
            area, _ = measures(source['points'])
            kept_area, kept_volume = measures(np.asarray(surface['points'])-origins[surface['zone']])
            if area <= .0001 and kept_area <= .0001:
                paired_collapse.add(surface['name'])
                after[surface['zone']][0] -= kept_area
                after[surface['zone']][1] -= kept_volume
                collapsed.append({'name': surface['name'], 'zone': surface['zone'], 'original_area_m2': kept_area,
                    'reverse_collapsed_name': surface['other'], 'method': 'Symmetric numerical collapse; both sides below existing 0.0001m2 bound, cumulative budgets still checked'})
        output = [s for s in output if s['name'] not in paired_collapse]
        names = {s['name'] for s in output}
        missing = [s for s in output if s['boundary'] == 'Surface' and s['other'] not in names]
    if missing:
        detail = ', '.join(s['name']+' ↔ '+s['other'] for s in missing[:10])
        raise core.ValidationError('数值归并导致成对热面不一致，拒绝单侧删除：'+detail)
    changes = []
    for zone, (area, volume) in before.items():
        new_area, new_volume = after[zone]
        if (abs(new_area-area) > max(.0001, area*1e-6) or
                abs(new_volume-volume) > max(.0001, abs(volume)*1e-6)):
            raise core.ValidationError(f'数值归并面积或体积变化超过绝对/相对限额，拒绝发布：{zone}; '
                f'area {area:.9f}->{new_area:.9f} m2; volume {volume:.9f}->{new_volume:.9f} m3')
        changes.append({'zone': zone, 'area_before_m2': area, 'area_after_m2': new_area,
                        'volume_before_m3': volume, 'volume_after_m3': new_volume})
    return output, {'coordinate_precision_m': PRECISION_M, 'weld_limit_m': WELD_LIMIT_M,
                    'rejected_overbudget_transitive_links': rejected_chains,
                    'max_displacement_m': maximum, 'collapsed_faces': collapsed, 'zones': changes,
                    'restored_source_convex_faces': repaired,
                    'relative_change_limit': 1e-6, 'absolute_area_change_limit_m2': .0001,
                    'absolute_volume_change_limit_m3': .0001,
                    'volume_reference': 'Per-zone local origin; signed-volume change is translation invariant',
                    'basis': 'Numerical intersections and IDF serialization only; source geometry and boundary classes unchanged.'}


def engine_collinear(points):
    """Vertices v9 CheckConvexity would remove (one microradian turn test)."""
    if len(points) <= 3:
        return False
    xyz = np.round(np.asarray(points), 6)
    a, b = xyz-np.roll(xyz, 1, axis=0), np.roll(xyz, -1, axis=0)-xyz
    denominator = np.linalg.norm(a, axis=1)*np.linalg.norm(b, axis=1)
    return bool(np.any(denominator <= 1e-16) or
                np.any(np.linalg.norm(np.cross(a, b), axis=1)/np.maximum(denominator, 1e-30) <= 1e-6))


def engine_fragile_polygon(points):
    if len(points) <= 3:
        return False
    if engine_collinear(points):
        return True
    try:
        polygon = frame(np.round(points, 6))['poly']
    except core.ValidationError:
        return True
    # Serialization can make an exactly collinear point slightly concave.
    # Preserve it in consistent triangles, rather than let the legacy engine
    # derive a reversed azimuth from a tiny first corner.
    return polygon.convex_hull.area-polygon.area > 1e-12


def conform(surfaces, *, return_report=False, preserve_window_walls=False, progress_callback=None, bounded_chains=False):
    source_surfaces = surfaces
    surfaces, pair_merges = merge_small_pairs(surfaces)
    faces = [{**s, 'points': [list(p) for p in s['points']]} for s in surfaces]
    input_precision = {'policy': 'Source coordinates preserved until final serialization'}
    for face in faces:
        face['_source_convex_points'] = [list(p) for p in face['points']]
    lookup = {s['name']: s for s in faces}
    planes = {s['name']: frame(s['points']) for s in faces}
    original = {s['name']: len(s['points']) for s in faces}
    iteration_sizes = []
    for _ in range(32):
        pools = {}
        for face in faces:
            pools.setdefault(face['zone'], []).extend(face['points'])
        pools = {k: np.unique(np.round(v, 8), axis=0) for k, v in pools.items()}
        indexed = {}
        def index(values):
            return (values, STRtree(shapely_points(values[:, :2])) if len(values) > 128 else None)
        for zone, values in pools.items():
            indexed[zone] = index(values)
        if sum(len(p) for p in pools.values()) > 500000:
            raise core.ValidationError('热边界一致化超过500000节点预算，未截断模型')
        changed = False
        for face in faces:
            points, tree = indexed[face['zone']]
            if face['boundary'] == 'Surface':
                other = lookup[face['other']]
                plane, op = planes[face['name']], planes[other['name']]
                # Exact frame values, not rounded plane-index keys. Reuse a
                # companion projection across triangles on the same plane.
                key = (face['zone'], other['zone'], tuple(plane['normal']), plane['distance'],
                       tuple(op['normal']), op['distance'])
                if key not in indexed:
                    candidates = pools[other['zone']]
                    valid = np.abs(candidates @ op['normal'] - op['distance']) < 1e-7
                    uv = np.column_stack((candidates[valid] @ op['axis'], candidates[valid] @ op['second']))
                    shifted = (uv[:, :1]*plane['axis']+uv[:, 1:]*plane['second']+
                               plane['normal']*plane['distance'])
                    indexed[key] = index(np.unique(np.round(np.concatenate((points, shifted)), 8), axis=0))
                points, tree = indexed[key]
            # Always subdivide original edges. Reprojecting onto an already
            # rounded sub-edge can accumulate zigzags and self intersections.
            ring, output = face['_source_convex_points'], []
            for a, b in zip(ring, ring[1:]+ring[:1]):
                start, vector = np.array(a), np.array(b)-a
                if float(vector @ vector) < 1e-16:
                    continue
                candidates = points
                if tree is not None:
                    bounds = box(min(a[0], b[0])-PRECISION_M, min(a[1], b[1])-PRECISION_M,
                                 max(a[0], b[0])+PRECISION_M, max(a[1], b[1])+PRECISION_M)
                    candidates = points[tree.query(bounds)]
                t = (candidates-start) @ vector / float(vector @ vector)
                distance = np.linalg.norm(candidates-(start+t[:, None]*vector), axis=1)
                indices = np.flatnonzero((t > 1e-6) & (t < 1-1e-6) & (distance < PRECISION_M))
                if output and np.linalg.norm(np.array(a)-output[-1]) <= 1e-7:
                    output[-1] = a
                else:
                    output.append(a)
                for i in indices[np.argsort(t[indices])]:
                    point = (start+t[i]*vector).tolist()
                    if np.linalg.norm(np.array(point)-output[-1]) > WELD_LIMIT_M and np.linalg.norm(np.array(point)-b) > WELD_LIMIT_M:
                        output.append(point)
            if len(output) > 1 and np.linalg.norm(np.array(output[0])-output[-1]) <= 1e-7:
                output.pop()
            if len(output) > len(face['points']):
                changed = True
                face['points'] = output
        # Suppress newly inserted near-duplicate junctions; original source
        # vertices stay untouched until the final bounded serialization pass.
        iteration_sizes.append(sum(len(s['points']) for s in faces))
        if progress_callback:
            progress_callback({'iteration': len(iteration_sizes), 'vertices': iteration_sizes[-1], 'changed': changed})
        if not changed:
            break
    else:
        raise core.ValidationError('热边界分段未收敛；须拆分复杂邻接后重试')
    junction_precision = {'policy': 'new junction spacing only; no source-coordinate welding before tessellation'}
    lookup = {s['name']: s for s in faces}
    result, done, degenerate_triangles = [], set(), []
    for face in faces:
        if face['name'] in done:
            continue
        done.add(face['name'])
        other = lookup[face['other']] if face['boundary'] == 'Surface' else None
        if other:
            done.add(other['name'])
        split = (len(face['points']) != original[face['name']] or engine_fragile_polygon(face['points']) or
                 (other and (len(other['points']) != original[other['name']] or engine_fragile_polygon(other['points']))))
        if not split:
            result.append(face)
            if other:
                result.append(other)
            continue
        if preserve_window_walls and face.get('aperture_parent'):
            result.append(face)
            continue
        plane = frame(face['points'])
        # frame retains collinear boundary vertices, required by constrained triangulation.
        triangles = list(constrained_delaunay_triangles(plane['poly']).geoms)
        if abs(sum(t.area for t in triangles)-plane['poly'].area) > 1e-7:
            raise core.ValidationError('热边界剖分面积不守恒')
        for i, triangle in enumerate(triangles):
            a_name = face['name']+f'_T{i}'
            b_name = other['name']+f'_T{i}' if other else ''
            if triangle.area < 5e-11:
                degenerate_triangles.append({'name': a_name, 'reverse_name': b_name or None,
                    'projected_area_m2': triangle.area,
                    'basis': 'CDT zero-area collinear artifact below existing numerical collapse threshold; both sides omitted'})
                continue
            result.append({**face, 'name': a_name, 'other': b_name,
                           'points': face_points(triangle, plane)})
            if other:
                result.append({**other, 'name': b_name, 'other': a_name,
                               'points': face_points(triangle, frame(other['points']))})
    result, after_pair_merges = merge_small_pairs(result)
    pair_merges.extend(after_pair_merges)
    result, precision = engine_vertices(result, bounded_chains=bounded_chains)
    # Merge numerical small triangles with a compatible neighbour only when the
    # result is a convex quad retaining every exterior vertex (no T-junction loss).
    compatible = defaultdict(list)
    cached_frames = {id(s): frame(s['points']) for s in result}
    for surface in result:
        compatible[tuple(surface[k] for k in ('zone', 'kind', 'boundary', 'construction'))+
                   cached_frames[id(surface)]['key']].append(surface)
    active = {id(s) for s in result}
    skipped_merges = 0
    for face in list(result):
        if id(face) not in active or face["boundary"] == "Surface" or face.get('aperture_parent'):
            continue
        p = cached_frames[id(face)]
        if p["poly"].area >= .001:
            continue
        key = tuple(face[k] for k in ('zone', 'kind', 'boundary', 'construction'))+p['key']
        for other in compatible[key]:
            if other is face or id(other) not in active or other.get('aperture_parent'):
                continue
            xyz = np.asarray(other['points'])
            q = cached_frames[id(other)]
            if p['side'] != q['side'] or np.max(np.abs(xyz @ p['normal']-p['distance'])) > 1e-10:
                continue
            # Rounded plane keys are an index, not a shared coordinate frame.
            # Reproject both polygons into p's exact basis before set operations.
            other_poly = Polygon(np.column_stack((xyz @ p['axis'], xyz @ p['second'])))
            if p['poly'].intersection(other_poly).length < .001:
                continue
            union = p["poly"].union(other_poly)
            if union.geom_type != "Polygon" or union.interiors or len(union.exterior.coords) != 5:
                continue
            xy = list(union.exterior.coords)[:-1]
            crosses = [abs((xy[i][0]-xy[i-1][0])*(xy[(i+1)%4][1]-xy[i][1]) -
                           (xy[i][1]-xy[i-1][1])*(xy[(i+1)%4][0]-xy[i][0])) for i in range(4)]
            if min(crosses) < 1e-8 or union.convex_hull.area-union.area > 1e-8:
                continue
            if abs(union.area-p["poly"].area-other_poly.area) > 1e-8:
                # This optional optimization must leave the input untouched if
                # exact area conservation cannot be proved. The full audit still
                # checks every retained face; no area is discarded or patched.
                skipped_merges += 1
                continue
            merged_points = face_points(union, p)
            if engine_fragile_polygon(merged_points):
                continue
            origin = np.asarray(face['points'][0])
            old_volume = measures(np.asarray(face['points'])-origin)[1]+measures(xyz-origin)[1]
            if abs(measures(np.asarray(merged_points)-origin)[1]-old_volume) > 1e-10:
                skipped_merges += 1
                continue
            other.update(points=merged_points, boundary_basis=other["boundary_basis"]+"; small coplanar triangle merged without area loss")
            cached_frames[id(other)] = frame(other['points'])
            active.remove(id(face))
            result.remove(face)
            break
    if len(result) > 100000:
        raise core.ValidationError('一致热网格超过 100000 面，请选择建筑范围')
    precision["output_faces"] = len(result)
    precision['input_normalization'] = input_precision
    precision['junction_normalization'] = junction_precision
    precision['conforming_iteration_vertices'] = iteration_sizes
    precision['paired_coplanar_merges'] = pair_merges
    precision['degenerate_tessellation_artifacts'] = degenerate_triangles
    precision['cumulative_conservation'] = conservation(source_surfaces, result)
    precision['skipped_nonconservative_optional_merges'] = skipped_merges
    for surface in result:
        surface.pop('_source_convex_points', None)
    return (result, precision) if return_report else result


def conservation(before, after):
    """The strict budget applies to the entire pipeline, not once per pass."""
    origins = {}
    for s in before:
        origins.setdefault(s['zone'], np.array(s['points'][0]))
    totals = []
    for collection in (before, after):
        sums = defaultdict(lambda: np.zeros(2))
        for s in collection:
            sums[s['zone']] += measures(np.asarray(s['points'])-origins[s['zone']])
        totals.append(sums)
    report = []
    if totals[0].keys() != totals[1].keys():
        raise core.ValidationError('热网格处理丢失空间，拒绝发布')
    for zone, (area, volume) in totals[0].items():
        new_area, new_volume = totals[1][zone]
        if (abs(new_area-area) > max(.0001, area*1e-6) or
                abs(new_volume-volume) > max(.0001, abs(volume)*1e-6)):
            raise core.ValidationError(f'完整热网格面积/体积累计变化超过限额：{zone}')
        report.append({'zone': zone, 'area_before_m2': float(area), 'area_after_m2': float(new_area),
                       'volume_before_m3': float(volume), 'volume_after_m3': float(new_volume)})
    return report


def merge_small_pairs(surfaces):
    """Union exact shared contact pieces on BOTH sides before numerical welding.

    Tiny overlay triangles are not missing architecture. A convex union retaining
    all exterior vertices avoids engine-invalid slivers without deleting contact
    area or changing either boundary class. No disconnected pieces are bridged.
    """
    faces = [{**s, 'points': [list(p) for p in s['points']]} for s in surfaces]
    lookup = {s['name']: s for s in faces}
    planes = {s['name']: frame(s['points']) for s in faces}
    groups = defaultdict(list)
    for face in faces:
        if face['boundary'] == 'Surface':
            key = (face['zone'], lookup[face['other']]['zone'], face['kind'], face['construction'], *planes[face['name']]['key'])
            groups[key].append(face)
    active, report = set(lookup), []
    for face in faces:
        if face['name'] not in active or face['boundary'] != 'Surface':
            continue
        p = planes[face['name']]
        if p['poly'].area >= .001:
            continue
        reciprocal = lookup[face['other']]
        key = (face['zone'], reciprocal['zone'], face['kind'], face['construction'], *p['key'])
        for neighbour in groups[key]:
            if neighbour is face or neighbour['name'] not in active:
                continue
            opposite = lookup[neighbour['other']]
            xyz = np.asarray(neighbour['points'])
            if (p['side'] != planes[neighbour['name']]['side'] or
                    np.max(np.abs(xyz @ p['normal']-p['distance'])) > 1e-10):
                continue
            q = Polygon(np.column_stack((xyz @ p['axis'], xyz @ p['second'])))
            if p['poly'].intersection(q).length < 1e-6:
                continue
            union = p['poly'].union(q)
            if (union.geom_type != 'Polygon' or union.interiors or len(union.exterior.coords) > 13 or
                    union.convex_hull.area-union.area > 1e-10 or
                    abs(union.area-p['poly'].area-q.area) > 1e-9):
                continue
            other_plane = planes[opposite['name']]
            # A single canonical projection must describe the reverse union too.
            expected = planes[reciprocal['name']]['poly'].area+other_plane['poly'].area
            if (abs(union.area-expected) > 1e-9 or np.linalg.norm(p['normal']-other_plane['normal']) > 1e-10 or
                    planes[reciprocal['name']]['side'] != other_plane['side']):
                continue
            front, back = face_points(union, p), face_points(union, other_plane)
            if engine_fragile_polygon(front) or engine_fragile_polygon(back):
                continue
            valid = True
            for old_a, old_b, new in ((face, neighbour, front), (reciprocal, opposite, back)):
                origin = np.asarray(old_a['points'][0])
                old_volume = measures(np.asarray(old_a['points'])-origin)[1]+measures(np.asarray(old_b['points'])-origin)[1]
                if abs(measures(np.asarray(new)-origin)[1]-old_volume) > 1e-10:
                    valid = False
            if not valid:
                continue
            neighbour['points'], opposite['points'] = front, back
            planes[neighbour['name']] = frame(neighbour['points'])
            planes[opposite['name']] = frame(opposite['points'])
            active.difference_update((face['name'], reciprocal['name']))
            report.append({'removed_face': face['name'], 'reverse_removed_face': reciprocal['name'],
                           'into_face': neighbour['name'], 'reverse_into_face': opposite['name'],
                           'contact_area_m2': p['poly'].area, 'union_area_m2': union.area,
                           'method': 'Exact convex coplanar union on both sides; no contact area discarded'})
            break
    return [s for s in faces if s['name'] in active], report


def edge_incidence(surfaces):
    zones = defaultdict(Counter)
    for face in surfaces:
        ring = [tuple(round(float(v), 6) for v in p) for p in face['points']]
        for a, b in zip(ring, ring[1:]+ring[:1]):
            zones[face['zone']][tuple(sorted((a, b)))] += 1
    return {zone: {'unmatched_edges': sum(n != 2 for n in edges.values()),
                   'examples': [{'points': edge, 'count': count} for edge, count in edges.items() if count != 2][:10]}
            for zone, edges in zones.items()}
