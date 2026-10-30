"""Source-window assembly projections with explicit mapping/area failures."""
from collections import defaultdict
import numpy as np
from shapely.geometry import Polygon
from shapely.ops import unary_union

from . import core, model_geometry as geo


def room_faces(room):
    if room.get('shell'):
        return [f['points'] for f in room['shell']]
    faces = []
    for part in geo.parts(room):
        low, high = part['elevation_m'], part['elevation_m']+part['height_m']
        p = Polygon(part['polygon'], part.get('holes', []))
        for piece in geo.simple_pieces(p):
            ring = list(piece.exterior.coords)[:-1]
            faces.extend([[[x, y, low] for x, y in reversed(ring)], [[x, y, high] for x, y in ring]])
        for ring in [p.exterior, *p.interiors]:
            xy = list(ring.coords)
            for a, b in zip(xy, xy[1:]):
                faces.append([[a[0], a[1], low], [b[0], b[1], low], [b[0], b[1], high], [a[0], a[1], high]])
    return faces


def attach(document, rooms, origin, tolerance=0.):
    import ifcopenshell.geom
    from ifcopenshell.util.element import get_psets
    from .model_import import space_storey
    settings = ifcopenshell.geom.settings()
    settings.set('use-world-coords', True)
    if not document.by_type('IfcWindow'):
        return {'eligible_source_windows': 0, 'mapped_source_windows': 0, 'excluded_by_scope': 0,
                'issues': [], 'geometry_scope': 'No IfcWindow supplied; absence is not proof of no glazing'}
    candidates = defaultdict(list)
    for room in rooms:
        for points in room_faces(room):
            plane = geo.frame(points)
            candidates[tuple(np.round(plane['normal'], 5))].append((room, plane))
    low = min(r['elevation_m'] for r in rooms)
    high = max(r['elevation_m']+r['height_m'] for r in rooms)
    scope = {r.get('storey_id') for r in rooms}-{None}
    parent_settings = ifcopenshell.geom.settings()
    parent_settings.set('use-world-coords', True)
    parent_settings.set('disable-opening-subtractions', True)
    parent_vertices = {}
    meshes = {}
    iterator = ifcopenshell.geom.iterator(settings, document, 2, include=document.by_type('IfcWindow'))
    if iterator.initialize():
        while True:
            shape = iterator.get()
            meshes[shape.id] = (np.asarray(shape.geometry.verts).reshape(-1, 3).copy(),
                                np.asarray(shape.geometry.faces).reshape(-1, 3).copy())
            if not iterator.next():
                break
    issues, eligible, mapped, outside = [], 0, 0, 0
    for window in document.by_type('IfcWindow'):
        floor = space_storey(window)
        if scope and floor and floor.GlobalId not in scope:
            outside += 1
            continue
        try:
            parents = [r.RelatingOpeningElement.VoidsElements[0].RelatingBuildingElement for r in window.FillsVoids
                       if r.RelatingOpeningElement.VoidsElements]
            source_v, source_t = meshes[window.id()]
            source_opening_id = None
            if len(window.FillsVoids) == 1:
                opening = window.FillsVoids[0].RelatingOpeningElement
                source_opening_id = opening.GlobalId
                void_shape = ifcopenshell.geom.create_shape(parent_settings, opening)
                source_v = np.asarray(void_shape.geometry.verts).reshape(-1, 3)
                source_t = np.asarray(void_shape.geometry.faces).reshape(-1, 3)
            v = source_v-origin
            if v[:, 2].max() < low-.05 or v[:, 2].min() > high+.05:
                outside += 1
                continue
            eligible += 1
            groups = defaultdict(list)
            for t in source_t:
                try:
                    p = geo.frame(v[t].tolist())
                except core.ValidationError:
                    continue
                groups[(p['key'], p['side'])].append(p)
            if not groups:
                raise ValueError('未找到可投影的源窗正面')
            fronts = []
            for planes in groups.values():
                plane = planes[0]
                union = unary_union([p['poly'] for p in planes])
                fronts.append((union.area, plane, union))
            area, plane, outline = max(fronts, key=lambda x: x[0])
            projected = []
            for t in source_t:
                poly = Polygon([(float(p @ plane['axis']), float(p @ plane['second'])) for p in v[t]])
                if poly.area > 1e-10:
                    projected.append(poly)
            outline = unary_union(projected)
            area = outline.area
            original_area = area
            if tolerance:
                simplified = outline.simplify(tolerance, preserve_topology=True)
                if (outline.hausdorff_distance(simplified) > tolerance+1e-7 or
                        abs(simplified.area-area) > area*.01):
                    raise ValueError('窗几何简化超过位移或1%面积预算，未采用')
                outline, area = simplified, simplified.area
            if area < 1e-6:
                raise ValueError('源窗面积过小')
            matches = []
            band = None
            external = get_psets(window).get('Pset_WindowCommon', {}).get('IsExternal')
            if len(parents) == 1:
                parent = parents[0]
                if parent.id() not in parent_vertices:
                    wall_shape = ifcopenshell.geom.create_shape(parent_settings, parent)
                    parent_vertices[parent.id()] = np.asarray(wall_shape.geometry.verts).reshape(-1, 3).copy()
                distances = (parent_vertices[parent.id()]-origin) @ plane['normal']
                band = (float(distances.min()), float(distances.max()))
                if external is None:
                    external = get_psets(parent).get('Pset_WallCommon', {}).get('IsExternal')
            for room, wall in candidates.get(tuple(np.round(plane['normal'], 5)), []):
                offset = abs(plane['distance']-wall['distance'])
                if offset > 1.5 or (not band and offset > .05) or (band and not band[0]-.05 <= wall['distance'] <= band[1]+.05):
                    continue
                common = outline.intersection(wall['poly'])
                if common.area > 1e-6:
                    matches.append((offset, room, wall, common))
            matches.sort(key=lambda x: (x[0], x[1]['id']))
            used, total = Polygon(), 0.
            for offset, room, wall, common in matches:
                fragment = common.difference(used)
                if fragment.area < 1e-6:
                    continue
                for piece in geo.simple_pieces(fragment):
                    projected = geo.face_points(piece, wall)
                    room.setdefault('source_openings', []).append({'source_id': window.GlobalId,
                        'points': projected, 'source_area_m2': piece.area, 'source_is_external': external,
                        'projection_offset_m': float(offset), 'geometry_scope': 'IFC_OPENING_PROJECTION' if source_opening_id else 'IFC_WINDOW_ASSEMBLY_PROJECTION',
                        'source_opening_id': source_opening_id, 'original_area_m2': original_area,
                        'approximation_tolerance_m': tolerance, 'area_error_percent': (area/original_area-1)*100})
                    if external is not False:
                        # A fenestration must be contained by a larger parent
                        # wall. Unknown window-bearing wall classification is an
                        # explicit scenario, never inferred as source evidence.
                        room.setdefault('boundary_hints', []).append({'points': geo.face_points(wall['poly'], wall), 'source_id': window.GlobalId,
                            'classification': 'EXTERNAL', 'basis': 'source_window' if external else 'inferred_window'})
                used = used.union(fragment)
                total += fragment.area
            if abs(total-area) > max(.0001, area*.001):
                raise ValueError(f'源窗投影面积未完整映射：{total:.6f}/{area:.6f} m²')
            mapped += 1
        except Exception as exc:
            issues.append(window.GlobalId+': '+str(exc)[:350])
    if issues:
        rooms[0]['source_opening_issues'] = issues[:499]+([f'另有{len(issues)-499}项；查看原始来源诊断'] if len(issues)>499 else [])
    return {'eligible_source_windows': eligible, 'mapped_source_windows': mapped,
            'excluded_by_scope': outside, 'issues': issues, 'geometry_scope': 'Window assembly geometry; frame/glass optical properties require review'}


def apply(model, room, face, assigned):
    from honeybee.aperture import Aperture
    from ladybug_geometry.geometry3d import Face3D, Point3D
    plane = geo.frame([list(p) for p in face.geometry.vertices])
    groups = defaultdict(list)
    for n, opening in enumerate(room.get('source_openings', [])):
        p = geo.frame(opening['points'])
        if np.linalg.norm(p['normal']-plane['normal']) > 1e-6 or abs(p['distance']-plane['distance']) > .00002:
            continue
        overlap = plane['poly'].intersection(p['poly'])
        if overlap.area < 1e-7:
            continue
        if face.boundary_condition.name != 'Outdoors':
            raise core.ValidationError('源窗映射至内部/未知热边界，尚不能当作外窗：'+opening['source_id']+'; '+room['id']+'; '+face.identifier+'; '+face.boundary_condition.name)
        groups[opening['source_id']].append((opening, overlap))
        assigned[(room['id'], n)] += overlap.area
    for n, parts in enumerate(groups.values()):
        opening = parts[0][0]
        combined = unary_union([p for _, p in parts])
        for i, poly in enumerate(fenestration_pieces(combined)):
            aperture = Aperture(face.identifier+f'_Src{n}_{i}', Face3D(tuple(Point3D(*p) for p in geo.face_points(poly, plane))))
            aperture.user_data = {**opening, 'mapped_area_m2': poly.area}
            face.add_aperture(aperture)


def fenestration_pieces(shape):
    for poly in geo.polygons(shape):
        poly = poly.simplify(1e-8, preserve_topology=True)
        ring = list(poly.exterior.coords)[:-1]
        if not poly.interiors and len(ring) > 4 and poly.convex_hull.area-poly.area < 1e-8:
            center = poly.centroid.coords[0]
            for a, b in zip(ring, ring[1:]+ring[:1]):
                yield Polygon([a, b, center])
        else:
            yield from geo.simple_pieces(poly)


def partition_parents(model, surfaces):
    """Computational convex wall patches enclosing windows; same exterior area.

    Window bounding rectangles partition an existing plane only. They never
    replace a room or add envelope area. Opaque remainder is triangulated.
    """
    groups, retained = defaultdict(list), []
    for s in surfaces:
        if s['kind'] == 'Wall' and s['boundary'] == 'Outdoors':
            p = geo.frame(s['points'])
            groups[(s['zone'], s['construction'], p['key'], p['side'])].append((s, p))
        else:
            retained.append(s)
    lookup = {r['id']: r for r in model['rooms']}
    for (zone, _, _, _), values in groups.items():
        source, plane = values[0]
        shape = unary_union([p['poly'] for _, p in values])
        patches = []
        for opening in lookup[zone].get('source_openings', []):
            p = geo.frame(opening['points'])
            if np.linalg.norm(p['normal']-plane['normal']) > 1e-6 or abs(p['distance']-plane['distance']) > .00002:
                continue
            if shape.intersection(p['poly']).area > 1e-7:
                patches.append(p['poly'].envelope.buffer(.02, join_style='mitre'))
        if not patches:
            retained.extend(s for s, _ in values)
            continue
        patches = geo.polygons(unary_union(patches))
        used = Polygon()
        for n, patch in enumerate(patches):
            patch = patch.envelope.intersection(shape).difference(used)
            for i, poly in enumerate(geo.polygons(patch)):
                if poly.interiors or poly.convex_hull.area-poly.area > 1e-8:
                    # Refuse a bad source parent instead of casting a nonconvex
                    # facade or moving/shrinking its window.
                    raise core.ValidationError('源窗父墙不能形成凸面计算分区：'+zone)
                retained.append({**source, 'name': source['name']+f'_WP{n}_{i}',
                    'points': geo.face_points(poly, plane), 'aperture_parent': True,
                    'boundary_basis': source['boundary_basis']+'; convex source-window parent partition'})
            used = used.union(patch)
        for n, poly in enumerate(geo.simple_pieces(shape.difference(used))):
            retained.append({**source, 'name': source['name']+f'_OP{n}', 'points': geo.face_points(poly, plane)})
        if abs(used.area+shape.difference(used).area-shape.area) > max(1e-7, shape.area*1e-8):
            raise core.ValidationError('源窗父墙分区面积不守恒：'+zone)
    return retained


def engine_compatible_apertures(face):
    """EnergyPlus 9 silently rectangularizes trapezoids; split without area loss."""
    from honeybee.aperture import Aperture
    output, changed = [], False
    for aperture in face.apertures:
        p = [np.array(list(v)) for v in aperture.geometry.vertices]
        if len(p) == 4:
            edges = [b-a for a, b in zip(p, p[1:]+p[:1])]
            rectangular = all(abs(float(a @ b)) <= 1e-7*max(float(np.linalg.norm(a)*np.linalg.norm(b)), 1e-12)
                              for a, b in zip(edges, edges[1:]+edges[:1]))
            if not rectangular:
                changed = True
                for n, triangle in enumerate(aperture.geometry.triangulated_mesh3d.face_vertices):
                    from ladybug_geometry.geometry3d import Face3D
                    sub = Aperture(aperture.identifier+'_E9T'+str(n), Face3D(triangle))
                    sub.user_data = {**(aperture.user_data or {}), 'engine_partition': 'nonrectangular quad split without area loss'}
                    output.append(sub)
                continue
        output.append(aperture)
    if changed:
        face.remove_apertures()
        for aperture in output:
            face.add_aperture(aperture)
