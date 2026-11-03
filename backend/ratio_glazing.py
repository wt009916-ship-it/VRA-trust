"""Explicit facade-area WWR allocation across representable coplanar fragments.

Numerical thermal fragments are not individual design windows. Preserve each
facade's aggregate target area; report excluded tiny fragments and redistribution.
This applies only to hypothetical ratio geometry, never to source apertures.
"""
from collections import defaultdict
from math import sqrt

from . import core
from .model_geometry import frame


def _ratio_apertures(face, ratio):
    """Keep narrow numerical rectangles: they are fragments, not design windows.

    Honeybee's inset operation can fail on narrow but engine-representable
    convex faces. Homothety is exact for convex polygons and preserves the
    target ratio without a fixed minimum architectural width.
    """
    face.remove_apertures()
    try:
        face.apertures_by_ratio(ratio, tolerance=.001)
    except (ValueError, AssertionError):
        face.remove_apertures()
    actual = sum(a.area for a in face.apertures)
    if abs(actual-face.area*ratio) <= max(1e-8, face.area*1e-7):
        return
    face.remove_apertures()
    plane = frame([list(p) for p in face.geometry.vertices])
    if plane['poly'].convex_hull.symmetric_difference(plane['poly']).area > 1e-10:
        raise ValueError('Nonconvex fragment requires topology-preserving decomposition')
    from honeybee.aperture import Aperture
    face.add_aperture(Aperture(face.identifier+'_ratio',
        face.geometry.scale(sqrt(ratio), face.geometry.centroid)))


def assign(faces_by_zone, ratio):
    groups = defaultdict(list)
    for zone, faces in faces_by_zone.items():
        for face in faces:
            if face.type.name != 'Wall' or face.boundary_condition.name != 'Outdoors':
                continue
            plane = frame([list(p) for p in face.geometry.vertices])
            groups[(zone, plane['key'], plane['side'])].append((face, plane))
    reports = []
    for key, entries in groups.items():
        target = sum(face.area for face, _ in entries)*ratio
        candidates, rejected = [], []
        for face, plane in entries:
            # Projected triangle area, not arbitrary 5 cm facade-fragment width.
            projected = face.area*max(abs(v) for v in plane['normal'])
            if projected*.6 <= .00005:
                rejected.append({'face': face.identifier, 'reason': 'Even maximum scenario ratio is below EnergyPlus projected area minimum'})
            else:
                candidates.append(face)
        while True:
            area = sum(face.area for face in candidates)
            local_ratio = target/area if area else float('inf')
            if local_ratio > .6+1e-9:
                raise core.ValidationError(f'可表达外墙不足以保留总开窗面积，未删窗或改变窗墙比：{key[0]}；'
                    f'本平面目标玻璃{target:.9g}m²，可用外墙{area:.9g}m²，排除{len(rejected)}片；'
                    f'首个片段：{rejected[0]["face"] if rejected else "无"}')
            failures = []
            for face in candidates:
                face.remove_apertures()
                try:
                    _ratio_apertures(face, local_ratio)
                    actual = sum(a.area for a in face.apertures)
                    if abs(actual-face.area*local_ratio) > max(.0001, face.area*.0001):
                        failures.append(face)
                except (ValueError, AssertionError):
                    failures.append(face)
            if not failures:
                break
            for face in failures:
                face.remove_apertures()
                candidates.remove(face)
                rejected.append({'face': face.identifier, 'reason': 'Native ratio operation could not preserve aperture area; reallocated within same facade'})
        actual = sum(a.area for face in candidates for a in face.apertures)
        if abs(actual-target) > max(.0001, target*.0001):
            raise core.ValidationError('外立面总开窗面积守恒失败，未采纳候选：'+key[0])
        reports.append({'zone_id': key[0], 'target_glazing_m2': target, 'actual_glazing_m2': actual,
                        'assigned_fragment_ratio': local_ratio, 'eligible_faces': len(candidates),
                        'excluded_fragments': rejected, 'source_geometry': False,
                        'basis': 'Explicit coplanar-facade WWR scenario; window placement redistributed, not recovered source windows'})
    return reports
