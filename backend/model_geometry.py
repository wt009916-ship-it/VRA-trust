"""Stepped space geometry, with explicit refusals instead of bounding-box solids."""
from collections import Counter, defaultdict
import copy
import numpy as np
from shapely import constrained_delaunay_triangles
from shapely.geometry import LineString, Polygon
from shapely.geometry.polygon import orient
from shapely.ops import polygonize, unary_union

from . import core

EPS = 1e-7


def parts(room):
    return room.get("segments") or [room]


def floor_area(room):
    if room.get('shell'):
        total = 0.
        for face in room['shell']:
            plane = frame(face['points'])
            if (plane['normal']*plane['side'])[2] < -.5:
                total += Polygon([(x,y) for x,y,_ in face['points']]).area
        return total
    sections = parts(room)
    levels = []
    for z in sorted(s['elevation_m'] for s in sections):
        if not levels or z-levels[-1] > EPS:
            levels.append(z)
    total = 0.
    for low in levels:
        above = unary_union([Polygon(s['polygon'], s.get('holes', [])) for s in sections if abs(s['elevation_m']-low) <= EPS])
        beneath = unary_union([Polygon(s['polygon'], s.get('holes', [])) for s in sections
            if s['elevation_m'] < low-EPS and s['elevation_m']+s['height_m'] >= low-EPS])
        total += above.difference(beneath).area
    return total


def room_volume(room):
    if room.get('shell'):
        from .solid_geometry import volume
        return volume([f['points'] for f in room['shell']])
    return sum(Polygon(s['polygon'], s.get('holes', [])).area*s['height_m'] for s in parts(room))


def polygons(shape):
    if shape.is_empty:
        return []
    if shape.geom_type == "Polygon":
        return [shape] if shape.area > EPS else []
    if shape.geom_type not in {"MultiPolygon", "GeometryCollection"}:
        return []
    return [p for child in shape.geoms for p in polygons(child)]


def simple_pieces(shape):
    """Convex faces with at most four vertices, including exact hole subtraction."""
    result = []
    for poly in polygons(shape):
        poly = poly.simplify(1e-8, preserve_topology=True)
        if not poly.interiors and len(poly.exterior.coords) <= 5 and poly.convex_hull.area - poly.area < EPS:
            result.append(orient(poly, sign=1))
        elif not poly.interiors and poly.convex_hull.area-poly.area < 1e-10:
            # A fan avoids arbitrarily thin ears on faceted curves while
            # preserving every source edge and the exact polygon area.
            center = tuple(poly.centroid.coords[0])
            ring = list(poly.exterior.coords)
            fan = [orient(Polygon([a, b, center]), sign=1) for a, b in zip(ring, ring[1:])]
            result.extend(fan if all(t.area > EPS for t in fan) else
                          [orient(t, sign=1) for t in constrained_delaunay_triangles(poly).geoms if t.area > EPS])
        else:
            result.extend(orient(t, sign=1) for t in constrained_delaunay_triangles(poly).geoms if t.area > EPS)
    return result


def mesh_segments(vertices, triangles):
    """Exact slicing for horizontal/vertical polyhedra; sloping solids are refused."""
    v = np.asarray(vertices, dtype=float).reshape(-1, 3)
    f = np.asarray(triangles, dtype=int).reshape(-1, 3)
    if not len(v) or len(v) > 100000 or len(f) > 100000:
        raise ValueError("空间网格为空或超过处理上限")
    edges = Counter()
    for tri in f:
        pts = v[tri]
        n = np.cross(pts[1] - pts[0], pts[2] - pts[0])
        length = np.linalg.norm(n)
        if length < 1e-12:
            continue
        nz = abs(n[2]) / length
        if 1e-7 < nz < 1 - 1e-7:
            raise ValueError("空间含斜面，不能精确表示为水平分段；请保留原模型另行建模")
        keys = [tuple(np.round(p, 7)) for p in pts]
        for a, b in zip(keys, keys[1:] + keys[:1]):
            if a != b:
                edges[tuple(sorted((a, b)))] += 1
    if any(count != 2 for count in edges.values()):
        raise ValueError("空间网格不闭合或非流形，不能确认内部截面")
    levels = sorted(set(float(z) for z in np.round(v[:, 2], 7)))
    if len(levels) > 65:
        raise ValueError("空间高度分段超过 64")
    sections = []
    for low, high in zip(levels, levels[1:]):
        if high - low < 1e-6:
            continue
        z = (low + high) / 2
        lines = []
        for tri in f:
            pts = v[tri].tolist()
            crossings = set()
            for a, b in zip(pts, pts[1:] + pts[:1]):
                if (a[2] - z) * (b[2] - z) < 0:
                    t = (z - a[2]) / (b[2] - a[2])
                    crossings.add(tuple(round(a[k] + t * (b[k] - a[k]), 7) for k in (0, 1)))
            if len(crossings) == 2:
                lines.append(LineString(list(crossings)))
        # Even/odd winding excludes holes, irrespective of inconsistent face normals.
        regions = []
        for poly in polygonize(unary_union(lines)):
            p = poly.representative_point()
            intersections = []
            for line in lines:
                a, b = line.coords
                if (a[1] > p.y) != (b[1] > p.y):
                    x = a[0] + (p.y - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
                    if x > p.x:
                        intersections.append(round(x, 7))
            if len(set(intersections)) % 2:
                regions.append(poly)
        shape = unary_union(regions)
        if shape.is_empty:
            raise ValueError("空间截面未形成可验证的闭合区域")
        if sections and sections[-1][2].symmetric_difference(shape).area < EPS:
            sections[-1] = (sections[-1][0], high, shape)
        else:
            sections.append((low, high, shape))
    result = []
    for low, high, shape in sections:
        for poly in polygons(shape):
            pieces = simple_pieces(poly) if poly.interiors else [orient(poly, sign=1)]
            for piece in pieces:
                result.append({"polygon": list(piece.exterior.coords)[:-1],
                               "elevation_m": low, "height_m": high - low})
    if len(result) > 128:
        raise ValueError("空间分段超过 128")
    return result


def frame(points):
    """Canonical plane plus an orthonormal 2D projection, independent of winding."""
    xyz = np.asarray(points, dtype=float)
    normal = np.zeros(3)
    for i in range(1, len(xyz) - 1):
        normal += np.cross(xyz[i] - xyz[0], xyz[i + 1] - xyz[0])
    length = np.linalg.norm(normal)
    if length < 1e-10:
        raise core.ValidationError("热边界面积为零")
    normal /= length
    side = 1
    first = next(c for c in normal if abs(c) > 1e-7)
    if first < 0:
        normal *= -1
        side = -1
    distance = float(np.dot(normal, xyz[0]))
    if np.max(np.abs(xyz @ normal - distance)) > 1e-5:
        raise core.ValidationError("热边界不是平面")
    axis = np.array([1., 0., 0.]) if abs(normal[2]) > .99 else np.array([-normal[1], normal[0], 0.])
    axis /= np.linalg.norm(axis)
    second = np.cross(normal, axis)
    poly = Polygon([(float(p @ axis), float(p @ second)) for p in xyz])
    if not poly.is_valid:
        raise core.ValidationError("热边界自交")
    return {"normal": normal, "distance": distance, "axis": axis, "second": second,
            "side": side, "poly": poly,
            "key": tuple(np.round(normal, 6)) + (round(distance, 5),)}


def face_points(poly, plane):
    xy = list(orient(poly, sign=plane["side"]).exterior.coords)[:-1]
    return [(plane["normal"] * plane["distance"] + plane["axis"] * x + plane["second"] * y).tolist()
            for x, y in xy]


def geometry(model, *, return_report=False):
    """Split partial contacts, remove interfaces inside a room, preserve closed zones."""
    from shapely import intersection, difference
    from shapely.errors import GEOSException
    retries = []

    def overlay(a, b, operation):
        try:
            return getattr(a, operation)(b)
        except GEOSException:
            if not a.is_valid or not b.is_valid:
                raise core.ValidationError('热边界输入多边形无效，须修复源几何') from None
            try:
                out = (intersection if operation == 'intersection' else difference)(a, b, grid_size=1e-8)
            except GEOSException as exc:
                raise core.ValidationError('热边界布尔运算失败，未删除空间或改变边界：'+str(exc)[:300]) from exc
            retries.append({'operation': operation, 'grid_m': 1e-8, 'input_area_m2': a.area, 'output_area_m2': out.area})
            return out
    rooms = model["rooms"]
    hint_cache = defaultdict(list)
    for room in rooms:
        for hint in room.get('boundary_hints', []):
            if hint.get('basis') in ('source_window', 'inferred_window') and (model.get('thermal') or {}).get('window_geometry') != 'source':
                continue
            hp = frame(hint['points'])
            hint_cache[(room['id'], tuple(np.round(hp['normal'], 5)))].append((hint, hp))
    all_parts = [s for room in rooms for s in parts(room)]
    if len(all_parts) > 20000:
        raise core.ValidationError("建筑分段超过 20000")
    minimum = min(s["elevation_m"] for s in all_parts)
    maximum = max(s['elevation_m']+s['height_m'] for s in all_parts)
    raw = []
    for room in rooms:
        if room.get('shell'):
            for face in room['shell']:
                plane = frame(face['points'])
                nz = (plane['normal']*plane['side'])[2]
                raw.append({'zone': room['id'], 'kind': 'Roof' if nz > .5 else 'Floor' if nz < -.5 else 'Wall',
                            'room': room, 'plane': plane})
            continue
        for section in parts(room):
            z, high = section["elevation_m"], section["elevation_m"] + section["height_m"]
            shape = orient(Polygon(section['polygon'], section.get('holes', [])), sign=1)
            coords = list(shape.exterior.coords)[:-1]
            for kind, level, ring in (("Floor", z, list(reversed(coords))), ("Roof", high, coords)):
                plane = frame([[x, y, level] for x, y in ring])
                if shape.interiors:
                    holes = [[(float(np.dot([x, y, level], plane['axis'])), float(np.dot([x, y, level], plane['second'])))
                              for x, y in list(hole.coords)[:-1]] for hole in shape.interiors]
                    plane['poly'] = Polygon(plane['poly'].exterior, holes)
                raw.append({'zone': room['id'], 'kind': kind, 'room': room, 'plane': plane})
            for outline in [shape.exterior, *shape.interiors]:
                coords = list(outline.coords)[:-1]
                for a, b in zip(coords, coords[1:] + coords[:1]):
                    if a == b:
                        continue  # Exact duplicate ring vertex has zero area; no physical edge is removed.
                    raw.append({"zone": room["id"], "kind": "Wall", "room": room, "plane": frame([
                        [a[0], a[1], z], [b[0], b[1], z], [b[0], b[1], high], [a[0], a[1], high]])})
    groups = defaultdict(list)
    for surface in raw:
        surface["remaining"] = surface["plane"]["poly"]
        groups[surface["plane"]["key"]].append(surface)
    result = []

    def emit(source, polygon, boundary, other="", reverse=False, reason=""):
        name = f'{source["zone"]}_S{len(result)+1}'
        construction = "Wall" if source["kind"] == "Wall" else "Floor" if boundary == "Surface" else source["kind"]
        if construction == "Roof" and boundary == "Adiabatic":
            construction = "Roof"
        if reverse:
            construction += "Reverse"
        result.append({"name": name, "zone": source["zone"], "kind": source["kind"],
                       "construction": construction, "boundary": boundary, "other": other,
                       "points": face_points(polygon, source["plane"]), "boundary_basis": reason})
        return result[-1]

    for group in groups.values():
        from shapely.strtree import STRtree
        tree = STRtree([s['plane']['poly'] for s in group])
        for i, a in enumerate(group):
            for j in sorted(tree.query(a['plane']['poly'], predicate='intersects')):
                if j <= i:
                    continue
                b = group[j]
                if a["plane"]["side"] == b["plane"]["side"]:
                    continue
                overlap = overlay(a['remaining'], b['remaining'], 'intersection')
                if overlap.area <= EPS:
                    continue
                a["remaining"] = overlay(a['remaining'], overlap, 'difference')
                b["remaining"] = overlay(b['remaining'], overlap, 'difference')
                if a["zone"] == b["zone"]:
                    continue
                for poly in simple_pieces(overlap):
                    sa = emit(a, poly, "Surface", reason="共面空间接触")
                    sb = emit(b, poly, "Surface", sa["name"], True, "共面空间接触")
                    sa["other"] = sb["name"]
    # A finite wall thickness separates room air volumes. Pair only facing, parallel
    # portions, nearest first. This is an explicit scenario, never source geometry repair.
    gap_limit = (model.get("thermal") or {}).get("adjacency_gap_m", 0)
    if gap_limit:
        orientations = defaultdict(list)
        for surface in raw:
            orientations[surface["plane"]["key"][:3]].append(surface)
        contacts = []
        for candidates in orientations.values():
            ordered = sorted(candidates, key=lambda s: s["plane"]["distance"])
            tree = STRtree([s['plane']['poly'] for s in ordered])
            for i, a in enumerate(ordered):
                if a["plane"]["side"] != 1:
                    continue
                for j in sorted(tree.query(a['plane']['poly'], predicate='intersects')):
                    if j <= i:
                        continue
                    b = ordered[j]
                    gap = b["plane"]["distance"]-a["plane"]["distance"]
                    if gap > gap_limit:
                        continue
                    if gap > 1e-5 and b["plane"]["side"] == -1 and a["zone"] != b["zone"]:
                        contacts.append((gap, a, b))
        for gap, a, b in sorted(contacts, key=lambda c: c[0]):
            overlap = overlay(a['remaining'], b['remaining'], 'intersection')
            if overlap.area <= EPS:
                continue
            a["remaining"] = overlay(a['remaining'], overlap, 'difference')
            b["remaining"] = overlay(b['remaining'], overlap, 'difference')
            reason = f"ASSUMED: facing parallel room surfaces across {gap:.6f} m; allowed gap {gap_limit:g} m"
            for poly in simple_pieces(overlap):
                sa = emit(a, poly, "Surface", reason=reason)
                sb = emit(b, poly, "Surface", sa["name"], True, reason)
                sa["other"] = sb["name"]
    for surface in raw:
        remaining = surface["remaining"]
        room, plane = surface["room"], surface["plane"]
        if room.get("ifc_source"):
            hints = []
            for hint, hp in hint_cache[(room['id'], tuple(np.round(plane['normal'], 5)))]:
                offset = abs(hp["distance"] - plane["distance"])
                bounds = hint.get("element_plane_range_m")
                supported = bounds and bounds[0]-1e-5 <= plane["distance"] <= bounds[1]+1e-5
                if np.linalg.norm(hp["normal"] - plane["normal"]) < 1e-6 and (offset <= .05 or supported):
                    # IFC boundary can lie at slab reference elevation, a few mm from finished floor.
                    hints.append((offset, hint, hp))
            hints.sort(key=lambda x: (1 if x[1].get('basis') == 'inferred_window' else
                                     2 if x[1]['classification'] == 'NOTDEFINED' else 0, x[0]))
            for offset, hint, hp in hints:
                match = overlay(remaining, hp['poly'], 'intersection')
                if match.area <= EPS:
                    continue
                classification = hint["classification"]
                if hint.get('basis') == 'inferred_window' and (model.get('thermal') or {}).get('source_window_exterior_policy') != 'outdoor_scenario':
                    raise core.ValidationError('源窗缺少内外分类；请复核或明确选择外窗假设情景：'+hint['source_id'])
                if hint.get('basis') == 'inferred_outline':
                    if (model.get('thermal') or {}).get('reconstructed_exterior_policy') != 'outline_scenario':
                        raise core.ValidationError('构件推导的楼板外缘不是已知幕墙；须核对外立面或显式选择外包络假设情景')
                if classification == "EXTERNAL_EARTH":
                    boundary = "Ground"
                elif classification == "EXTERNAL":
                    boundary = "Ground" if surface["kind"] == "Floor" and abs(plane["distance"]-minimum) < .05 else "Outdoors"
                else:
                    boundary = "Adiabatic"
                if boundary == "Adiabatic" and (model.get("thermal") or {}).get("ifc_unpaired_policy", "reject") != "adiabatic_scenario":
                    raise core.ValidationError("IFC 内部边界尚未配对；须补充邻接，或明确选择未配对边界绝热的假设情景")
                for poly in simple_pieces(match):
                    prefix = 'ASSUMED '+hint['basis']+'; ' if hint.get('basis') in ('inferred_outline', 'inferred_window') else ''
                    emit(surface, poly, boundary, reason=prefix+f'IFC {hint["source_id"]}; {classification}; offset={offset:.6f}m')
                remaining = overlay(remaining, match, 'difference')
            if remaining.area > EPS:
                inferred = (room.get('reconstruction') or {}).get('method') == 'IFC_ELEMENT_SECTION'
                exterior = (model.get('thermal') or {}).get('reconstructed_exterior_policy') == 'outline_scenario'
                level = float((plane['normal']*plane['distance'])[2]) if abs(plane['normal'][2]) > .99 else None
                if inferred and exterior and level is not None and (
                        (surface['kind'] == 'Floor' and abs(level-minimum) < .05) or
                        (surface['kind'] == 'Roof' and abs(level-maximum) < .05)):
                    for poly in simple_pieces(remaining):
                        emit(surface, poly, 'Ground' if surface['kind'] == 'Floor' else 'Outdoors',
                             reason='ASSUMED reconstructed building lowest floor/highest roof envelope')
                    continue
                if (model.get("thermal") or {}).get("ifc_unpaired_policy", "reject") != "adiabatic_scenario":
                    raise core.ValidationError("IFC 部分热边界缺少可匹配依据；禁止自动当成外墙")
                for poly in simple_pieces(remaining):
                    emit(surface, poly, "Adiabatic", reason="ASSUMED: 未匹配 IFC 边界明确按绝热处理")
        else:
            boundary = "Ground" if surface["kind"] == "Floor" and abs(plane["distance"]-minimum) < EPS else "Outdoors"
            for poly in simple_pieces(remaining):
                emit(surface, poly, boundary, reason="人工空间模型外围边界")
    # Remove artificial cuts introduced by overlapping first-level boundary hints.
    # Paired interzone faces retain their reciprocal identities.
    compacted = [s for s in result if s["boundary"] == "Surface"]
    dissolve = defaultdict(list)
    for surface in result:
        if surface["boundary"] != "Surface":
            p = frame(surface["points"])
            key = (surface["zone"], surface["kind"], surface["boundary"], p["key"])
            dissolve[key].append((surface, p))
    for group in dissolve.values():
        source, plane = group[0]
        shape = unary_union([p["poly"] for _, p in group])
        basis = "；".join(sorted(set(s["boundary_basis"] for s, _ in group)))
        for i, poly in enumerate(simple_pieces(shape)):
            compacted.append({**source, "name": source["name"]+f"_M{i}", "points": face_points(poly, plane),
                              "boundary_basis": basis})
    if len(compacted) > 100000:
        counts = Counter(s['zone'] for s in compacted)
        raise core.ValidationError(f'热边界超过100000（{len(compacted)}）；最多的空间：{counts.most_common(5)}')
    report = {'overlay_fallbacks': retries, 'overlay_grid_m': 1e-8,
              'scope': 'Only valid-input GEOS failures retry on a 10 nanometre projected grid; no engineering gap closure'}
    return (compacted, report) if return_report else compacted


def thermal_geometry_model(model):
    tolerance = (model.get('thermal') or {}).get('geometry_tolerance_m', 0)
    adaptive = (model.get('thermal') or {}).get('geometry_tolerance_policy') == 'bounded_retry'
    attempts = []
    for value in ([tolerance/(2**i) for i in range(8)]+[0] if adaptive and tolerance else [tolerance]):
        try:
            derived, report = _normalize_geometry_once(model, value)
            report.update(requested_tolerance_m=tolerance, attempts=attempts,
                          policy='bounded_retry' if adaptive else 'strict')
            return derived, report
        except core.ValidationError as exc:
            if not adaptive:
                raise
            attempts.append({'tolerance_m': value, 'status': 'rejected', 'reason': str(exc)})
    raise core.ValidationError('有界几何归并未通过，原空间保留：'+str(attempts))


def _normalize_geometry_once(model, tolerance):
    """Optional, recorded coordinate normalization for the engine's 1 cm vertex limit."""
    if not tolerance:
        return model, {"tolerance_m": 0, "max_axis_displacement_m": 0, "rooms": []}
    normalized = copy.deepcopy(model)
    points = []
    for room in normalized["rooms"]:
        if room.get('shell'):
            continue
        for section in [room, *room.get("segments", [])]:
            points.extend([x, y, section["elevation_m"]] for x, y in section["polygon"])
            points.extend([x, y, section["elevation_m"]+section["height_m"]] for x, y in section["polygon"])
            for ring in section.get('holes', []):
                points.extend([x, y, section['elevation_m']] for x, y in ring)
        for ring in room.get("holes", []):
            points.extend([x, y, room["elevation_m"]] for x, y in ring)
        for hint in room.get("boundary_hints", []):
            points.extend(hint["points"])
    maps = []
    maximum = 0
    for axis in range(3):
        values = sorted(set(round(p[axis], 7) for p in points))
        groups = []
        for value in values:
            if not groups or value-groups[-1][0] > tolerance:
                groups.append([value])
            else:
                groups[-1].append(value)
        mapping = {}
        for group in groups:
            center = round((group[0]+group[-1])/2, 7)
            for value in group:
                mapping[value] = center
                maximum = max(maximum, abs(center-value))
        maps.append(mapping)

    def snapped(value, axis):
        return maps[axis][round(value, 7)]

    report, topology_repairs = [], []
    for original, room in zip(model["rooms"], normalized["rooms"]):
        if room.get('shell'):
            report.append({'room_id': room['id'], 'original_area_m2': floor_area(room),
                           'normalized_area_m2': floor_area(room), 'original_volume_m3': room_volume(room),
                           'normalized_volume_m3': room_volume(room), 'shell_policy': 'source planes preserved; no axis snapping'})
            continue
        preserved = False
        for section in [room, *room.get("segments", [])]:
            low = snapped(section["elevation_m"], 2)
            high = snapped(section["elevation_m"]+section["height_m"], 2)
            if high-low < 1e-6:
                raise core.ValidationError("几何公差会消除空间分段，请减小公差或修正源模型")
            holes = [[(snapped(x, 0), snapped(y, 1)) for x, y in ring] for ring in section.get('holes', [])]
            shape = Polygon([(snapped(x, 0), snapped(y, 1)) for x, y in section["polygon"]], holes)
            if not shape.is_valid and (model.get('thermal') or {}).get('geometry_tolerance_policy') == 'bounded_retry':
                original_shape = Polygon(section['polygon'], section.get('holes', []))
                repaired = shape.buffer(0)
                if (repaired.geom_type == 'Polygon' and repaired.is_valid and
                        len(repaired.interiors) == len(original_shape.interiors) and
                        original_shape.symmetric_difference(repaired).area <= min(.01, original_shape.area*.001) and
                        original_shape.boundary.hausdorff_distance(repaired.boundary) <= tolerance+1e-7):
                    topology_repairs.append({'room_id': room['id'], 'method': 'Bounded zero-width spur cleanup after axis normalization',
                        'symmetric_difference_m2': original_shape.symmetric_difference(repaired).area,
                        'hausdorff_m': original_shape.boundary.hausdorff_distance(repaired.boundary),
                        'source_holes': len(original_shape.interiors), 'derived_holes': len(repaired.interiors)})
                    shape = repaired
            if not shape.is_valid or shape.area < EPS:
                if (model.get('thermal') or {}).get('geometry_tolerance_policy') == 'bounded_retry':
                    room.clear()
                    room.update(copy.deepcopy(original))
                    preserved = True
                    break
                raise core.ValidationError("几何公差产生无效空间，请减小公差")
            section.update(polygon=list(shape.simplify(1e-8).exterior.coords)[:-1],
                           holes=[list(r.coords)[:-1] for r in shape.interiors],
                           elevation_m=low, height_m=high-low)
        if preserved:
            report.append({'room_id': room['id'], 'original_area_m2': floor_area(original),
                'normalized_area_m2': floor_area(room), 'original_volume_m3': room_volume(original),
                'normalized_volume_m3': room_volume(room), 'normalization_policy': 'Original room preserved because the requested normalization broke topology'})
            continue
        if room.get('segments') and (model.get('thermal') or {}).get('geometry_tolerance_policy') == 'bounded_retry':
            level = min(part['elevation_m'] for part in room['segments'])
            bottom = unary_union([Polygon(part['polygon'], part.get('holes', [])) for part in room['segments']
                                  if abs(part['elevation_m']-level) < 1e-7])
            if bottom.geom_type != 'Polygon' or not bottom.is_valid:
                raise core.ValidationError('有界归并后的底面不连通，须收紧公差：'+room['id'])
            room['polygon'] = list(bottom.exterior.coords)[:-1]
            room['holes'] = [list(ring.coords)[:-1] for ring in bottom.interiors]
            room['elevation_m'] = level
            room['height_m'] = max(part['elevation_m']+part['height_m'] for part in room['segments'])-level
        if (model.get('thermal') or {}).get('geometry_tolerance_policy') == 'bounded_retry':
            area, volume = floor_area(original), room_volume(original)
            if abs(floor_area(room)-area) > max(.01, area*.005) or abs(room_volume(room)-volume) > max(.01, volume*.005):
                raise core.ValidationError('有界归并超过单空间0.5%面积或体积预算，须收紧公差：'+room['id'])
        hints = []
        for hint in room.get("boundary_hints", []):
            hint["points"] = [[snapped(value, axis) for axis, value in enumerate(p)] for p in hint["points"]]
            try:
                frame(hint["points"])
            except core.ValidationError:
                continue  # Degenerate source hints are recorded, not used as outside-air evidence.
            hints.append(hint)
        discarded = len(room.get("boundary_hints", []))-len(hints)
        room["boundary_hints"] = hints
        report.append({"room_id": room["id"], "original_area_m2": floor_area(original),
                       "normalized_area_m2": floor_area(room),
                       "original_volume_m3": room_volume(original),
                       "normalized_volume_m3": room_volume(room),
                       "degenerate_boundary_hints": discarded})
    from .model_schema import ModelDraft
    # Only validate the public draft fields; persisted metadata is unchanged.
    draft = {key: normalized[key] for key in ModelDraft.model_fields if key in normalized}
    try:
        ModelDraft.model_validate(draft)
    except ValueError as exc:
        raise core.ValidationError("几何公差后的模型未通过校验，请减小公差或修正源模型：" + str(exc)[:500]) from exc
    return normalized, {"tolerance_m": tolerance, "max_axis_displacement_m": maximum, "rooms": report,
                        'bounded_topology_repairs': topology_repairs,
                        "floor_area_basis": "Original reviewed bottom footprints; not the normalized simulation envelope."}


def ifc_boundary_hints(document, space):
    """Read first-level physical/virtual boundary geometry; never infer a wall from a box."""
    from ifcopenshell.util.placement import get_axis2placement, get_local_placement
    from ifcopenshell.util.unit import calculate_unit_scale
    import ifcopenshell.geom
    factor = calculate_unit_scale(document)
    placement = get_local_placement(space.ObjectPlacement)
    hints, skipped = [], 0
    for boundary in space.BoundedBy:
        try:
            item = boundary.ConnectionGeometry.SurfaceOnRelatingElement
            rings = []
            if item.is_a("IfcCurveBoundedPlane"):
                if item.InnerBoundaries:
                    raise ValueError("带孔边界需额外分割")
                transform = get_axis2placement(item.BasisSurface.Position)
                rings = [[list(p.Coordinates) + [0.] for p in item.OuterBoundary.Points]]
                rings = [[p[:3] for p in ring] for ring in rings]
            elif item.is_a("IfcSurfaceOfLinearExtrusion"):
                transform = get_axis2placement(item.Position)
                curve = item.SweptCurve.Curve
                points = [list(p.Coordinates) + [0.] * (3-len(p.Coordinates)) for p in curve.Points]
                direction = np.array(item.ExtrudedDirection.DirectionRatios, dtype=float)
                direction = direction / np.linalg.norm(direction) * item.Depth
                for a, b in zip(points, points[1:]):
                    rings.append([a, b, (np.array(b)+direction).tolist(), (np.array(a)+direction).tolist()])
            else:
                raise ValueError("不支持此边界曲面")
            for ring in rings:
                xyz = [(placement @ transform @ np.array([*p, 1.]))[:3] * factor for p in ring]
                if len(xyz) > 3 and np.linalg.norm(xyz[0]-xyz[-1]) < EPS:
                    xyz.pop()
                points = [p.tolist() for p in xyz]
                plane = frame(points)
                hint = {"points": points, "classification": boundary.InternalOrExternalBoundary,
                        "source_id": boundary.GlobalId}
                element = boundary.RelatedBuildingElement
                if element:
                    hint['source_element_id'] = element.GlobalId
                if element and element.is_a("IfcWall") and boundary.PhysicalOrVirtualBoundary == "PHYSICAL":
                    # Some IFC exporters place first-level boundaries on the wall
                    # centreline. Project only through the associated physical wall.
                    try:
                        settings = ifcopenshell.geom.settings()
                        settings.set(settings.USE_WORLD_COORDS, True)
                        shape = ifcopenshell.geom.create_shape(settings, element)
                        vertices = np.array(shape.geometry.verts).reshape(-1, 3)
                        distances = vertices @ plane["normal"]
                        low, high = float(min(distances)), float(max(distances))
                        if high-low <= 1 and low-1e-5 <= plane["distance"] <= high+1e-5:
                            hint["element_plane_range_m"] = [low, high]
                    except (RuntimeError, ValueError):
                        pass  # No supported projection; ordinary matching/refusal remains.
                hints.append(hint)
        except (AttributeError, ValueError, TypeError, core.ValidationError):
            skipped += 1
    return hints, skipped
