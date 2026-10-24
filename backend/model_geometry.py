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
    sections = parts(room)
    low = min(s["elevation_m"] for s in sections)
    return unary_union([Polygon(s["polygon"]) for s in sections
                        if abs(s["elevation_m"] - low) < EPS]).area


def polygons(shape):
    if shape.is_empty:
        return []
    if shape.geom_type == "Polygon":
        return [shape] if shape.area > EPS else []
    return [p for child in shape.geoms for p in polygons(child)]


def simple_pieces(shape):
    """Convex faces with at most four vertices, including exact hole subtraction."""
    result = []
    for poly in polygons(shape):
        poly = poly.simplify(1e-8, preserve_topology=True)
        if not poly.interiors and len(poly.exterior.coords) <= 5 and poly.convex_hull.area - poly.area < EPS:
            result.append(orient(poly, sign=1))
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


def geometry(model):
    """Split partial contacts, remove interfaces inside a room, preserve closed zones."""
    rooms = model["rooms"]
    all_parts = [s for room in rooms for s in parts(room)]
    if len(all_parts) > 1000:
        raise core.ValidationError("建筑分段超过 1000")
    minimum = min(s["elevation_m"] for s in all_parts)
    raw = []
    for room in rooms:
        for section in parts(room):
            z, high = section["elevation_m"], section["elevation_m"] + section["height_m"]
            coords = list(orient(Polygon(section["polygon"]), sign=1).exterior.coords)[:-1]
            for kind, level, ring in (("Floor", z, list(reversed(coords))), ("Roof", high, coords)):
                raw.append({"zone": room["id"], "kind": kind, "room": room,
                            "plane": frame([[x, y, level] for x, y in ring])})
            for a, b in zip(coords, coords[1:] + coords[:1]):
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
        for i, a in enumerate(group):
            for b in group[i+1:]:
                if a["plane"]["side"] == b["plane"]["side"]:
                    continue
                overlap = a["remaining"].intersection(b["remaining"])
                if overlap.area <= EPS:
                    continue
                a["remaining"] = a["remaining"].difference(overlap)
                b["remaining"] = b["remaining"].difference(overlap)
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
            for i, a in enumerate(ordered):
                if a["plane"]["side"] != 1:
                    continue
                for b in ordered[i+1:]:
                    gap = b["plane"]["distance"]-a["plane"]["distance"]
                    if gap > gap_limit:
                        break
                    if gap > 1e-5 and b["plane"]["side"] == -1 and a["zone"] != b["zone"]:
                        contacts.append((gap, a, b))
        for gap, a, b in sorted(contacts, key=lambda c: c[0]):
            overlap = a["remaining"].intersection(b["remaining"])
            if overlap.area <= EPS:
                continue
            a["remaining"] = a["remaining"].difference(overlap)
            b["remaining"] = b["remaining"].difference(overlap)
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
            for hint in room.get("boundary_hints", []):
                hp = frame(hint["points"])
                offset = abs(hp["distance"] - plane["distance"])
                bounds = hint.get("element_plane_range_m")
                supported = bounds and bounds[0]-1e-5 <= plane["distance"] <= bounds[1]+1e-5
                if np.linalg.norm(hp["normal"] - plane["normal"]) < 1e-6 and (offset <= .05 or supported):
                    # IFC boundary can lie at slab reference elevation, a few mm from finished floor.
                    hints.append((offset, hint, hp))
            hints.sort(key=lambda x: x[0])
            for offset, hint, hp in hints:
                match = remaining.intersection(hp["poly"])
                if match.area <= EPS:
                    continue
                classification = hint["classification"]
                if classification == "EXTERNAL_EARTH":
                    boundary = "Ground"
                elif classification == "EXTERNAL":
                    boundary = "Ground" if surface["kind"] == "Floor" and abs(plane["distance"]-minimum) < .05 else "Outdoors"
                else:
                    boundary = "Adiabatic"
                if boundary == "Adiabatic" and (model.get("thermal") or {}).get("ifc_unpaired_policy", "reject") != "adiabatic_scenario":
                    raise core.ValidationError("IFC 内部边界尚未配对；须补充邻接，或明确选择未配对边界绝热的假设情景")
                for poly in simple_pieces(match):
                    emit(surface, poly, boundary, reason=f'IFC {hint["source_id"]}; {classification}; offset={offset:.6f}m')
                remaining = remaining.difference(match)
            if remaining.area > EPS:
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
    if len(compacted) > 10000:
        raise core.ValidationError("热边界超过 10000")
    return compacted


def thermal_geometry_model(model):
    """Optional, recorded coordinate normalization for the engine's 1 cm vertex limit."""
    tolerance = (model.get("thermal") or {}).get("geometry_tolerance_m", 0)
    if not tolerance:
        return model, {"tolerance_m": 0, "max_axis_displacement_m": 0, "rooms": []}
    normalized = copy.deepcopy(model)
    points = []
    for room in normalized["rooms"]:
        for section in [room, *room.get("segments", [])]:
            points.extend([x, y, section["elevation_m"]] for x, y in section["polygon"])
            points.extend([x, y, section["elevation_m"]+section["height_m"]] for x, y in section["polygon"])
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

    report = []
    for original, room in zip(model["rooms"], normalized["rooms"]):
        for section in [room, *room.get("segments", [])]:
            low = snapped(section["elevation_m"], 2)
            high = snapped(section["elevation_m"]+section["height_m"], 2)
            if high-low < 1e-6:
                raise core.ValidationError("几何公差会消除空间分段，请减小公差或修正源模型")
            shape = Polygon([(snapped(x, 0), snapped(y, 1)) for x, y in section["polygon"]])
            if not shape.is_valid or shape.area < EPS:
                raise core.ValidationError("几何公差产生无效空间，请减小公差")
            section.update(polygon=list(shape.simplify(1e-8).exterior.coords)[:-1],
                           elevation_m=low, height_m=high-low)
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
                       "original_volume_m3": sum(Polygon(s["polygon"]).area*s["height_m"] for s in parts(original)),
                       "normalized_volume_m3": sum(Polygon(s["polygon"]).area*s["height_m"] for s in parts(room)),
                       "degenerate_boundary_hints": discarded})
    from .model_schema import ModelDraft
    # Only validate the public draft fields; persisted metadata is unchanged.
    draft = {key: normalized[key] for key in ModelDraft.model_fields if key in normalized}
    try:
        ModelDraft.model_validate(draft)
    except ValueError as exc:
        raise core.ValidationError("几何公差后的模型未通过校验，请减小公差或修正源模型：" + str(exc)[:500]) from exc
    return normalized, {"tolerance_m": tolerance, "max_axis_displacement_m": maximum, "rooms": report,
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
