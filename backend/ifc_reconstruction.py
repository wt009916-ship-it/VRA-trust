"""Auditable floor/slab and wall-solid sections, never element bounding-box rooms.

Missing facade/ceiling information stays explicit. Output is an INFERRED candidate
requiring occupancy, area and envelope review, not a recovered original IfcSpace.
"""
from collections import defaultdict
import time
import numpy as np
from shapely import set_precision
from shapely.geometry import LineString, Polygon
from shapely.ops import polygonize, unary_union

from . import core, model_geometry as geo


def section(vertices, triangles, z):
    """Even/odd section of the actual triangle shell at a non-tangent plane."""
    v, f = np.asarray(vertices).reshape(-1, 3), np.asarray(triangles).reshape(-1, 3)
    lines = []
    for t in f:
        pts = v[t]
        if pts[:, 2].min() >= z or pts[:, 2].max() <= z:
            continue
        hits = set()
        for a, b in zip(pts, np.roll(pts, -1, axis=0)):
            if (a[2]-z)*(b[2]-z) < 0:
                p = a+(b-a)*(z-a[2])/(b[2]-a[2])
                hits.add(tuple(np.round(p[:2], 7)))
        if len(hits) == 2:
            lines.append(LineString(list(hits)))
    if not lines:
        return Polygon()
    rings = list(polygonize(unary_union(lines)))
    result = []
    for p in rings:
        x, y = p.representative_point().coords[0]
        crossings = 0
        for line in lines:
            (ax, ay), (bx, by) = line.coords
            if (ay > y) != (by > y) and x < ax+(y-ay)*(bx-ax)/(by-ay):
                crossings += 1
        if crossings % 2:
            result.append(p)
    return set_precision(unary_union(result), 1e-7)


def elements(document):
    import ifcopenshell.geom
    from .model_import import spatial_ancestor
    settings = ifcopenshell.geom.settings()
    settings.set('use-world-coords', True)
    settings.set('disable-opening-subtractions', True)
    source = [e for kind in ('IfcWall', 'IfcSlab', 'IfcCurtainWall', 'IfcColumn', 'IfcRoof') for e in document.by_type(kind)]
    if len(source) > 30000:
        raise core.ValidationError('构件重建超过30000构件预算，请按建筑范围导出')
    iterator = ifcopenshell.geom.iterator(settings, document, 2, include=source)
    output = []
    if iterator.initialize():
        while True:
            shape = iterator.get()
            e = document.by_id(shape.id)
            building = spatial_ancestor(e, 'IfcBuilding')
            storey = spatial_ancestor(e, 'IfcBuildingStorey')
            v = np.asarray(shape.geometry.verts).reshape(-1, 3)
            output.append({'id': e.GlobalId, 'type': e.is_a(), 'vertices': v,
                           'building_id': building.GlobalId if building else None,
                           'storey_id': storey.GlobalId if storey else None,
                           'triangles': np.asarray(shape.geometry.faces).reshape(-1, 3),
                           'low': v.min(axis=0), 'high': v.max(axis=0)})
            if not iterator.next():
                break
    missing = sorted({e.GlobalId for e in source}-{e['id'] for e in output})
    if missing:
        raise core.ValidationError('构件实体提取失败，未忽略失败构件：'+', '.join(missing[:20]))
    return output


def horizontal_faces(items, upwards):
    groups = defaultdict(list)
    for e in items:
        v = e['vertices']
        for t in e['triangles']:
            p = v[t]
            n = np.cross(p[1]-p[0], p[2]-p[0])
            if (n[2] if upwards else -n[2]) <= 1e-9 or np.ptp(p[:, 2]) > 1e-6:
                continue
            groups[(round(float(p[0, 2]), 5), e.get('building_id'), e.get('storey_id'))].append((e['id'], Polygon(p[:, :2])))
    return [{'z': key[0], 'building_id': key[1], 'storey_id': key[2],
             'shape': set_precision(unary_union([p for _, p in data]), 1e-7), 'ids': sorted({i for i, _ in data})}
            for key, data in sorted(groups.items(), key=lambda item: (item[0][0], str(item[0][1:])))]


def bounded_simplify(shape, tolerance, ledger, locator):
    if not tolerance or shape.is_empty:
        return shape
    for factor in (1, .5, .25, .125):
        value = tolerance*factor
        candidate = shape.simplify(value, preserve_topology=True)
        error = candidate.area-shape.area
        distance = shape.boundary.hausdorff_distance(candidate.boundary)
        if candidate.is_valid and abs(error) <= min(.01, shape.area*.01) and distance <= value+1e-7:
            if not shape.equals_exact(candidate, 1e-10):
                ledger.append({'source_locator': locator, 'requested_tolerance_m': tolerance,
                    'applied_tolerance_m': value, 'hausdorff_m': distance,
                    'original_area_m2': shape.area, 'candidate_area_m2': candidate.area})
            return candidate
    return shape  # Preserve details when no candidate satisfies the budget.


def reconstruct(document, options, inventory):
    from .model_schema import Room
    started = time.monotonic()
    items = elements(document)
    slabs = [e for e in items if e['type'] in ('IfcSlab', 'IfcRoof')]
    barriers = [e for e in items if e['type'] not in ('IfcSlab', 'IfcRoof')]
    tops, bottoms = horizontal_faces(slabs, True), horizontal_faces(slabs, False)
    adjustments = []
    for kind, faces in [('slab_top', tops), ('slab_bottom', bottoms)]:
        for face in faces:
            face['shape'] = bounded_simplify(face['shape'], options.reconstruction_tolerance_m,
                                             adjustments, kind+'@'+str(face['z']))
    origin = options.ifc_origin_m or (0., 0., 0.)
    selected = set(options.ifc_storey_ids)
    floors = [s for s in inventory['storeys'] if not selected or s['id'] in selected]
    rooms, floor_reports = [], []
    for storey in floors:
        if time.monotonic()-started > 180:
            raise core.ValidationError('构件重建超过180秒预算，未发布部分建筑')
        nominal = storey['elevation_m']
        if nominal is None:
            floor_reports.append({'storey': storey['id'], 'status': 'missing_elevation', 'rooms': 0})
            continue
        same_building = [s for s in inventory['storeys'] if s.get('building_id') == storey.get('building_id')]
        nearby = [t for t in tops if t.get('building_id') == storey.get('building_id') and abs(t['z']-nominal) <= .75]
        candidates = [t for t in nearby if t.get('storey_id') == storey['id']]
        floor_basis = 'source_storey_ownership'
        if not candidates and nearby:
            peer_levels = [s for s in same_building if s['elevation_m'] is not None and abs(s['elevation_m']-nominal) <= .75]
            if len(peer_levels) > 1:
                floor_reports.append({'storey': storey['id'], 'name': storey['name'],
                    'building_id': storey.get('building_id'), 'building_name': storey.get('building_name'),
                    'status': 'ambiguous_floor_ownership', 'rooms': 0})
                continue
            candidates, floor_basis = nearby, 'unique_level_geometry_fallback'
        if not candidates:
            floor_reports.append({'storey': storey['id'], 'status': 'no_source_floor_surface', 'rooms': 0})
            continue
        floor = max(candidates, key=lambda t: t['shape'].area)
        z = floor['z']
        above = [b for b in bottoms if b.get('building_id') == storey.get('building_id') and z+.6 < b['z'] <= z+30]
        next_nominal = min((s['elevation_m'] for s in same_building if s['elevation_m'] is not None and s['elevation_m'] > nominal+.5), default=z+30)
        cut = z+min(.9, (next_nominal-z)/2)
        slices = []
        for e in barriers:
            if e.get('building_id') not in (None, storey.get('building_id')):
                continue
            if e['low'][2] < cut < e['high'][2]:
                shape = section(e['vertices'], e['triangles'], cut)
                shape = bounded_simplify(shape, options.reconstruction_tolerance_m, adjustments, e['id']+'@'+str(cut))
                if not shape.is_empty and shape.intersects(floor['shape']):
                    slices.append((e, shape))
        solid = unary_union([p for _, p in slices])
        air = set_precision(floor['shape'].difference(solid), 1e-7)
        cells = sorted(geo.polygons(air), key=lambda p: (round(p.centroid.x, 5), round(p.centroid.y, 5)))
        excluded = sum(p.area for p in cells if p.area < options.min_room_area_m2)
        count = 0
        for cell in cells:
            if cell.area < options.min_room_area_m2:
                continue
            close = [(e, s) for e, s in slices if cell.boundary.distance(s) < 1e-5]
            coverage = cell.boundary.intersection(solid.buffer(1e-5)).length/cell.length if cell.length else 0
            remaining, segments, ceiling_ids = cell, [], set()
            for ceiling in above:
                if ceiling['z'] > next_nominal+1:
                    break
                match = set_precision(remaining.intersection(ceiling['shape']), 1e-7)
                if match.area > 1e-6:
                    for part in geo.polygons(match):
                        segments.append({'polygon': [(x-origin[0], y-origin[1]) for x, y in list(part.exterior.coords)[:-1]],
                                         'holes': [[(x-origin[0], y-origin[1]) for x, y in list(r.coords)[:-1]] for r in part.interiors],
                                         'elevation_m': z-origin[2], 'height_m': ceiling['z']-z})
                    ceiling_ids.update(ceiling['ids'])
                    remaining = set_precision(remaining.difference(match), 1e-7)
            ceiling_basis = 'slab_surfaces'
            if remaining.area > 1e-5:
                heights = [float(e['high'][2]) for e, _ in close if z+.6 < e['high'][2] <= min(z+30, next_nominal+1)]
                if not heights:
                    floor_reports.append({'storey': storey['id'], 'status': 'unbounded_ceiling_cell', 'area_m2': cell.area, 'rooms': 0})
                    continue
                ceiling_basis = 'wall_top_assumption'
                for part in geo.polygons(remaining):
                    segments.append({'polygon': [(x-origin[0], y-origin[1]) for x, y in list(part.exterior.coords)[:-1]],
                                     'holes': [[(x-origin[0], y-origin[1]) for x, y in list(r.coords)[:-1]] for r in part.interiors],
                                     'elevation_m': z-origin[2], 'height_m': min(heights)-z})
            high = max(s['elevation_m']+s['height_m'] for s in segments)
            # Only slab-outline edges are candidate facades; other unpaired walls
            # stay unknown/internal until source or explicit scenario review.
            hints = []
            facade = cell.boundary.intersection(floor['shape'].boundary.buffer(1e-5))
            for line in getattr(facade, 'geoms', [facade]):
                if line.geom_type != 'LineString':
                    continue
                coords = list(line.coords)
                for a, b in zip(coords, coords[1:]):
                    if LineString([a, b]).length < 1e-5:
                        continue
                    hints.append({'points': [[a[0]-origin[0], a[1]-origin[1], z-origin[2]], [b[0]-origin[0], b[1]-origin[1], z-origin[2]],
                                             [b[0]-origin[0], b[1]-origin[1], high], [a[0]-origin[0], a[1]-origin[1], high]],
                                  'source_id': storey['id'], 'classification': 'EXTERNAL', 'basis': 'inferred_outline'})
            ids = sorted(set(floor['ids']) | ceiling_ids | {e['id'] for e, _ in close})
            columns = [(e, s) for e, s in slices if e['type'] in ('IfcColumn', 'IfcColumnStandardCase')]
            column_union = unary_union([s for _, s in columns])
            voids = []
            for ring in cell.interiors:
                hole = Polygon(ring)
                if hole.difference(column_union).area < 1e-6:
                    owners = [e['id'] for e, s in columns if s.intersection(hole).area > 1e-7]
                    if owners:
                        voids.append({'polygon': [(x-origin[0], y-origin[1]) for x, y in list(ring.coords)[:-1]], 'source_elements': owners})
            room = Room(id='R'+str(len(rooms)+1), name=(storey['name']+' · 推导空间 '+str(count+1))[:120],
                polygon=[(x-origin[0], y-origin[1]) for x, y in list(cell.exterior.coords)[:-1]],
                holes=[[(x-origin[0], y-origin[1]) for x, y in list(r.coords)[:-1]] for r in cell.interiors],
                elevation_m=z-origin[2], height_m=high-z+origin[2], segments=segments,
                storey_id=storey['id'], storey_name=storey['name'], ifc_source=storey['id'], boundary_hints=hints,
                building_id=storey.get('building_id'), building_name=storey.get('building_name'), geometry_inferred=True,
                conditioned=None, include_floor_area=None, source_locator='INFERRED IFC element section; storey='+storey['id'],
                reconstruction={'method': 'IFC_ELEMENT_SECTION', 'storey_id': storey['id'], 'source_elements': ids,
                    'column_voids': voids,
                    'slice_height_m': cut-origin[2], 'closed_wall_fraction': min(1., coverage), 'ceiling_basis': ceiling_basis,
                    'assumption': '由实际墙/柱截面从实际楼板表面扣除；门窗洞先封闭以识别分隔。楼板外缘不是幕墙证据；未闭合外立面与墙顶代替吊顶均为待复核假设。非原始IfcSpace，未推断用途、玻璃或设备。'})
            rooms.append(room.model_dump())
            count += 1
            if len(rooms) > 2000:
                raise core.ValidationError('推导空间超过2000预算，未截断或发布部分建筑')
        floor_reports.append({'storey': storey['id'], 'name': storey['name'], 'status': 'candidate', 'rooms': count,
            'building_id': storey.get('building_id'), 'building_name': storey.get('building_name'),
            'floor_selection_basis': floor_basis, 'floor_owner_storey_id': floor.get('storey_id'),
            'source_floor_z_m': z, 'section_z_m': cut, 'source_floor_area_m2': floor['shape'].area,
            'obstacle_area_m2': floor['shape'].intersection(solid).area, 'air_area_m2': air.area,
            'excluded_subminimum_area_m2': excluded, 'floor_level_candidates': [t['z'] for t in candidates]})
    if not rooms:
        raise core.ValidationError('未找到有源楼板和可确定上界的空间；未用包围盒或默认层高补出房间')
    return {'rooms': rooms, 'warnings': ['INFERRED：墙板推导候选，外包络、吊顶、空间用途/面积及热边界须复核；不能当作源IfcSpace或竣工热模型。',
            '重建逐层保留未恢复区域、低于面积阈值的区域及源构件；不将空平台自动计为空调空间。'],
        'diagnostics': {'format': 'IFC', 'method': 'IFC_ELEMENT_SECTION', 'source_spaces': 0,
            'source_storeys': len(inventory['storeys']), 'attempted_storeys': len(floors), 'storeys': floor_reports,
            'elements': len(items), 'coordinate_grid_m': 1e-7, 'reconstruction_adjustments': adjustments,
            'requested_tolerance_m': options.reconstruction_tolerance_m,
            'seconds': round(time.monotonic()-started, 3)},
        'metadata': {'schema': document.schema, 'scope': 'selected_storeys' if selected else 'whole_file_reconstruction',
            'source_total': 0, 'selected_storey_ids': sorted(selected), 'inventory': inventory, 'coordinate_origin_m': list(origin)}}
