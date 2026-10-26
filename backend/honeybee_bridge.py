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
    rooms = []
    for r in model['rooms']:
        faces = []
        for s in surfaces:
            if s['zone'] != r['id']:
                continue
            bc = Surface((s['other'], lookup[s['other']]['zone'])) if s['boundary'] == 'Surface' else {
                'Outdoors': boundary_conditions.outdoors, 'Ground': boundary_conditions.ground,
                'Adiabatic': boundary_conditions.adiabatic}[s['boundary']]
            kind = {'Wall': face_types.wall, 'Roof': face_types.roof_ceiling, 'Floor': face_types.floor}[s['kind']]
            face = Face(s['name'], Face3D(tuple(Point3D(*p) for p in s['points'])), kind, bc)
            ratio = (model.get('thermal') or {}).get('window_wall_ratio', 0)
            if s['boundary'] == 'Outdoors' and s['kind'] == 'Wall' and ratio:
                face.apertures_by_ratio(ratio, tolerance=.001)
                actual = sum(a.area for a in face.apertures)
                if abs(actual-face.area*ratio) > max(.0001, face.area*.0001):
                    raise core.ValidationError('Honeybee 开窗面积不满足指定窗墙比：' + s['name'])
            face.user_data = {'boundary_basis': s['boundary_basis'], 'construction_name': s['construction']}
            faces.append(face)
        room = Room(r['id'], faces, tolerance=0)
        room.display_name = r['name']
        room.exclude_floor_area = r.get('include_floor_area') is False
        room.user_data = {'source_locator': r['source_locator'], 'conditioned': r.get('conditioned')}
        rooms.append(room)
    result = Model('VRA_Building', rooms, units='Meters', tolerance=.001)
    result.display_name = model['name']
    result.user_data = {'scope': 'Geometry exchange only; energy inputs remain in VRA reviewed model and IDF',
                        'model_revision': model.get('revision'), 'libraries': library_versions()}
    return result


def engine_preflight(hb):
    """Check emitted geometry against two proven EnergyPlus 9.0.1 fatal rules.

    Source: v9.0.1 SurfaceGeometry.cc GetSurfaceData area < 1e-6 and
    GetVertices triangle edge < 0.01 m. This diagnoses, never drops or moves faces.
    Honeybee accepts some shapes that this older engine cannot consume.
    """
    from .thermal_mesh import measures
    issues, checked = [], 0
    for face in hb.faces:
        for item in (face, *face.apertures):
            checked += 1
            points = [[round(float(v), 6) for v in p] for p in item.geometry.vertices]
            area, _ = measures(points)
            edge = min(dist(a, b) for a, b in zip(points, points[1:]+points[:1]))
            code = 'AREA_BELOW_ENGINE_MINIMUM' if area < 1e-6 else (
                'TRIANGLE_EDGE_BELOW_ENGINE_MINIMUM' if len(points) == 3 and edge < .01 else None)
            if code:
                issues.append({'face': item.identifier, 'parent_face': face.identifier,
                               'code': code, 'serialized_area_m2': area, 'minimum_edge_m': edge})
    return {'engine': 'EnergyPlus 9.0.1', 'passed': not issues, 'checked_faces_and_windows': checked,
            'issue_count': len(issues), 'issues': issues[:100], 'issues_truncated': len(issues) > 100,
            'minimum_area_m2': 1e-6, 'minimum_triangle_edge_m': .01,
            'coordinate_decimals': 6, 'scope': 'Two known fatal rules; not a complete engine or physical validation'}


def audit(model, surfaces):
    try:
        hb = geometry_model(model, surfaces)
        checks = ('check_planar', 'check_self_intersecting', 'check_degenerate_rooms', 'check_rooms_solid',
                  'check_missing_adjacencies', 'check_matching_adjacent_areas', 'check_upside_down_faces',
                  'check_sub_faces_valid', 'check_sub_faces_overlapping')
        issues = []
        for check in checks:
            kwargs = {"tolerance": 1e-7} if check == "check_degenerate_rooms" else {}
            message = getattr(hb, check)(raise_exception=False, **kwargs)
            if message:
                issues.append({'check': check, 'message': message[:4000]})
        compatibility = engine_preflight(hb)
        if not compatibility['passed']:
            ids = ', '.join(i['face'] for i in compatibility['issues'][:20])
            issues.append({'check': 'vra_energyplus_9_preflight',
                           'message': f"EnergyPlus 9.0.1 不可接受的细小热面/窗共{compatibility['issue_count']}处：{ids}。请修复几何分段；未删除热面或修改边界。"})
        return {'engine': 'Honeybee', 'versions': library_versions(), 'passed': not issues,
                'checks': list(checks), 'issues': issues,
                'engine_compatibility': compatibility,
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
