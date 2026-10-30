"""Independent Honeybee geometry audit and genuine energy schedule compilation."""
from importlib.metadata import version
from math import dist

from . import core


def library_versions():
    return {name: version(name) for name in ('honeybee-core', 'honeybee-energy', 'ladybug-geometry')}


def geometry_model(model, surfaces):
    from honeybee.model import Model
    from honeybee.room import Room
    from honeybee.face import Face
    from honeybee.boundarycondition import Surface, boundary_conditions
    from honeybee.facetype import face_types
    from ladybug_geometry.geometry3d import Point3D, Face3D
    lookup = {s['name']: s for s in surfaces}
    from collections import defaultdict
    by_zone = defaultdict(list)
    for surface in surfaces:
        by_zone[surface['zone']].append(surface)
    rooms = []
    source_mode = (model.get('thermal') or {}).get('window_geometry') == 'source'
    facade_ratio = (model.get('thermal') or {}).get('ratio_glazing_policy') == 'coplanar_budget'
    assigned = defaultdict(float)
    if source_mode:
        issues = [issue for r in model['rooms'] for issue in r.get('source_opening_issues', [])]
        if issues:
            raise core.ValidationError('源窗尚未完整映射：'+'; '.join(issues[:10]))
        if not any(r.get('source_openings') for r in model['rooms']):
            raise core.ValidationError('没有可用的源窗几何；未将缺窗资料解释成零窗建筑')
    for r in model['rooms']:
        faces = []
        for s in by_zone[r['id']]:
            bc = Surface((s['other'], lookup[s['other']]['zone'])) if s['boundary'] == 'Surface' else {
                'Outdoors': boundary_conditions.outdoors, 'Ground': boundary_conditions.ground,
                'Adiabatic': boundary_conditions.adiabatic}[s['boundary']]
            kind = {'Wall': face_types.wall, 'Roof': face_types.roof_ceiling, 'Floor': face_types.floor}[s['kind']]
            face = Face(s['name'], Face3D(tuple(Point3D(*p) for p in s['points'])), kind, bc)
            ratio = (model.get('thermal') or {}).get('window_wall_ratio', 0)
            if source_mode:
                from .source_windows import apply
                apply(model, r, face, assigned)
            elif s['boundary'] == 'Outdoors' and s['kind'] == 'Wall' and ratio and not facade_ratio:
                face.apertures_by_ratio(ratio, tolerance=.001)
                actual = sum(a.area for a in face.apertures)
                if abs(actual-face.area*ratio) > max(.0001, face.area*.0001):
                    raise core.ValidationError('Honeybee 开窗面积不满足指定窗墙比：' + s['name'])
            face.user_data = {'boundary_basis': s['boundary_basis'], 'construction_name': s['construction']}
            from .source_windows import engine_compatible_apertures
            engine_compatible_apertures(face)
            faces.append(face)
        room = Room(r['id'], faces, tolerance=0)
        room.display_name = r['name']
        room.exclude_floor_area = r.get('include_floor_area') is False
        room.user_data = {'source_locator': r['source_locator'], 'conditioned': r.get('conditioned')}
        rooms.append(room)
    if source_mode:
        for r in model['rooms']:
            for n, opening in enumerate(r.get('source_openings', [])):
                area = opening['source_area_m2']
                if abs(assigned[(r['id'], n)]-area) > max(.0001, area*.001):
                    raise core.ValidationError('源窗面积未在最终热面完整保留：'+opening['source_id'])
    ratio_report = []
    if facade_ratio and (model.get('thermal') or {}).get('window_wall_ratio'):
        from .ratio_glazing import assign
        ratio_report = assign({r.identifier: r.faces for r in rooms}, model['thermal']['window_wall_ratio'])
        from .source_windows import engine_compatible_apertures
        for room in rooms:
            for face in room.faces:
                engine_compatible_apertures(face)
    result = Model('VRA_Building', rooms, units='Meters', tolerance=.001)
    result.display_name = model['name']
    result.user_data = {'scope': 'Geometry exchange only; energy inputs remain in VRA reviewed model and IDF',
                        'model_revision': model.get('revision'), 'libraries': library_versions(), 'ratio_glazing': ratio_report}
    return result


def engine_preflight(hb):
    """Check emitted geometry against three proven EnergyPlus 9.0.1 fatal rules.

    Source: v9.0.1 SurfaceGeometry.cc GetSurfaceData area < 1e-6 and
    GetVertices triangle edge < 0.01 m, CheckConvexity projected determinant
    <= 1e-4 on all three coordinate planes. Diagnose, never drop or move faces.
    Honeybee accepts some shapes that this older engine cannot consume.
    """
    from .thermal_mesh import measures
    import numpy as np
    issues, checked = [], 0
    for face in hb.faces:
        for item in (face, *face.apertures):
            checked += 1
            points = [[round(float(v), 6) for v in p] for p in item.geometry.vertices]
            area, _ = measures(points)
            xyz = np.asarray(points)
            vector = sum((np.cross(xyz[i]-xyz[0], xyz[i+1]-xyz[0]) for i in range(1, len(xyz)-1)), np.zeros(3))
            projected = float(np.max(np.abs(vector))/2)
            edge = min(dist(a, b) for a, b in zip(points, points[1:]+points[:1]))
            code = 'AREA_BELOW_ENGINE_MINIMUM' if area < 1e-6 else (
                'TRIANGLE_EDGE_BELOW_ENGINE_MINIMUM' if len(points) == 3 and edge < .01 else
                'PROJECTED_AREA_BELOW_ENGINE_MINIMUM' if projected <= .00005 else None)
            if code:
                issues.append({'face': item.identifier, 'parent_face': face.identifier,
                               'code': code, 'serialized_area_m2': area, 'minimum_edge_m': edge,
                               'maximum_projected_area_m2': projected})
    return {'engine': 'EnergyPlus 9.0.1', 'passed': not issues, 'checked_faces_and_windows': checked,
            'issue_count': len(issues), 'issues': issues[:100], 'issues_truncated': len(issues) > 100,
            'minimum_area_m2': 1e-6, 'minimum_triangle_edge_m': .01,
            'minimum_maximum_projected_area_m2_exclusive': .00005,
            'coordinate_decimals': 6, 'scope': 'Three known fatal rules; not a complete engine or physical validation'}


def audit(model, surfaces):
    try:
        hb = geometry_model(model, surfaces)
        checks = ('check_planar', 'check_self_intersecting', 'check_degenerate_rooms', 'check_rooms_solid',
                  'check_missing_adjacencies', 'check_matching_adjacent_areas', 'check_upside_down_faces',
                  'check_sub_faces_valid', 'check_sub_faces_overlapping')
        issues, containment_resolutions = [], []
        for check in checks:
            kwargs = {"tolerance": 1e-7} if check == "check_degenerate_rooms" else {}
            message = getattr(hb, check)(raise_exception=False, **kwargs)
            if message and check == 'check_sub_faces_valid' and (model.get('thermal') or {}).get('window_geometry') == 'source':
                # Ladybug's 2D boundary point test uses no distance tolerance and
                # can reject exactly clipped source windows on triangle edges.
                # Retain its result; accept only a stricter planar + GEOS area
                # containment proof. No aperture is shifted or shrunk.
                from .model_geometry import frame
                from shapely.geometry import Polygon
                import numpy as np
                valid = True
                for face in hb.faces:
                    parent = frame([list(p) for p in face.geometry.vertices])
                    for sub in (*face.apertures, *face.doors):
                        vertices = np.array([list(p) for p in sub.geometry.vertices])
                        poly = Polygon([(float(p @ parent['axis']), float(p @ parent['second'])) for p in vertices])
                        if (np.max(np.abs(vertices @ parent['normal']-parent['distance'])) > 1e-7 or
                                not poly.is_valid or poly.area <= 1e-10 or poly.difference(parent['poly']).area > 1e-10):
                            valid = False
                if valid:
                    containment_resolutions.append({'original_check': check, 'original_message': message[:4000],
                        'method': 'coplanarity <= 1e-7 m; exterior area <= 1e-10 m2; original aperture geometry unchanged'})
                    message = ''
            if message and check == 'check_sub_faces_overlapping' and (model.get('thermal') or {}).get('window_geometry') == 'source':
                from .model_geometry import frame
                from shapely.geometry import Polygon
                import numpy as np
                valid = True
                for face in hb.faces:
                    parent = frame([list(p) for p in face.geometry.vertices])
                    polys = [Polygon([(float(np.dot(p, parent['axis'])), float(np.dot(p, parent['second'])))
                                      for p in sub.geometry.vertices]) for sub in (*face.apertures, *face.doors)]
                    if any(a.intersection(b).area > 1e-10 for i, a in enumerate(polys) for b in polys[i+1:]):
                        valid = False
                if valid:
                    containment_resolutions.append({'original_check': check, 'original_message': message[:4000],
                        'method': 'pairwise projected intersection area <= 1e-10 m2; touching tessellation edges are not overlapping glass'})
                    message = ''
            if message:
                issues.append({'check': check, 'message': message[:4000]})
        from .thermal_mesh import frame
        import numpy as np
        by_name = {s['name']: s for s in surfaces}
        normal_mismatches = []
        for surface in surfaces:
            if surface['boundary'] != 'Surface' or surface['name'] > surface['other']:
                continue
            a, b = frame(surface['points']), frame(by_name[surface['other']]['points'])
            dot = float(np.dot(a['normal']*a['side'], b['normal']*b['side']))
            if dot > -1+1e-6:
                normal_mismatches.append({'face': surface['name'], 'other': surface['other'], 'normal_dot': dot})
        if normal_mismatches:
            issues.append({'check': 'vra_opposing_interzone_normals',
                           'message': '相邻空间热面未反向配对：'+', '.join(x['face']+' ↔ '+x['other'] for x in normal_mismatches[:10])})
        compatibility = engine_preflight(hb)
        if not compatibility['passed']:
            ids = ', '.join(i['face'] for i in compatibility['issues'][:20])
            issues.append({'check': 'vra_energyplus_9_preflight',
                           'message': f"EnergyPlus 9.0.1 不可接受的细小热面/窗共{compatibility['issue_count']}处：{ids}。请修复几何分段；未删除热面或修改边界。"})
        return {'engine': 'Honeybee', 'versions': library_versions(), 'passed': not issues,
                'checks': list(checks), 'issues': issues,
                'engine_compatibility': compatibility,
                'source_containment_resolutions': containment_resolutions,
                'ratio_glazing': hb.user_data.get('ratio_glazing', []),
                'interzone_normal_check': {'passed': not normal_mismatches, 'issues': normal_mismatches},
                'rooms': [{'room_id': r.identifier, 'volume_m3': r.volume, 'floor_area_m2': r.floor_area} for r in hb.rooms]}
    except (ValueError, AssertionError, KeyError) as exc:
        raise core.ValidationError('Honeybee 几何校验无法建立闭合模型：' + str(exc)[:500]) from exc


def schedules(thermal):
    """Honeybee compiles hourly weekday/weekend fractions and thermostat setback."""
    from honeybee_energy.schedule.ruleset import ScheduleRuleset
    from honeybee_energy.schedule.rule import ScheduleRule
    from honeybee_energy.schedule.day import ScheduleDay
    from honeybee_energy.lib.scheduletypelimits import fractional, temperature
    from ladybug.dt import Time
    op = thermal['operation']
    objects = [fractional.to_idf(), temperature.to_idf()]
    for name, limit, transform in (
        ('Occupied', fractional, lambda v: v),
        ('Heat', temperature, lambda v: thermal['heating_c'] if v > 0 else op['heating_setback_c']),
        ('Cool', temperature, lambda v: thermal['cooling_c'] if v > 0 else op['cooling_setback_c']),
    ):
        days = [ScheduleDay(name+suffix, [transform(v) for v in op[key]], [Time(h) for h in range(24)])
                for suffix, key in (('_Weekday', 'weekday'), ('_Weekend', 'weekend'))]
        rule = ScheduleRule(days[1], apply_saturday=True, apply_sunday=True)
        schedule = ScheduleRuleset(name, days[0], [rule], limit, holiday_schedule=days[1])
        year, weeks = schedule.to_idf()
        objects += [year, *weeks, *(day.to_idf(limit) for day in days)]
    return objects


def outdoor_air(thermal, room_id):
    from honeybee_energy.load.ventilation import Ventilation
    op = thermal['operation']
    specification = Ventilation(room_id+'_OA', flow_per_person=op['outdoor_air_l_s_person']/1000,
                                flow_per_area=op['outdoor_air_l_s_m2']/1000)
    return specification.to_idf(room_id), specification.identifier+'..'+room_id
