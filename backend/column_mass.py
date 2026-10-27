"""Explicit BEM simplification of proven internal IFC columns, never shafts.

Original review/3D geometry, net floor area and air volume remain unchanged.
Only a derived simulation envelope is filled. Column volume and exposed lateral
area produce homogeneous InternalMass of equivalent thickness V/A; conduction
paths/view factors are an approximation, not identical detailed physics.
"""
import copy
from shapely.geometry import Polygon
from shapely.ops import unary_union

from . import core, model_geometry as geo


def reduce(model):
    if (model.get('thermal') or {}).get('column_mass_policy') != 'lumped_scenario':
        return model, []
    derived, report = copy.deepcopy(model), []
    for original, room in zip(model['rooms'], derived['rooms']):
        voids = (room.get('reconstruction') or {}).get('column_voids', [])
        if not voids or room.get('shell'):
            continue
        levels = sorted({z for part in geo.parts(room) for z in (part['elevation_m'], part['elevation_m']+part['height_m'])})
        output, side_area, volume, owners = [], 0., 0., set()
        for low, high in zip(levels, levels[1:]):
            if high-low < 1e-6:
                continue
            active = [part for part in geo.parts(room) if part['elevation_m'] < (low+high)/2 < part['elevation_m']+part['height_m']]
            air = unary_union([Polygon(p['polygon'], p.get('holes', [])) for p in active])
            fill = []
            for poly in geo.polygons(air):
                for ring in poly.interiors:
                    hole = Polygon(ring)
                    matches = [v for v in voids if hole.difference(Polygon(v['polygon'])).area < 1e-6]
                    if not matches or hole.area/max(hole.length, 1e-12) < .001:
                        continue
                    fill.append(hole)
                    side_area += hole.length*(high-low)
                    volume += hole.area*(high-low)
                    owners.update(i for v in matches for i in v['source_elements'])
            shape = air.union(unary_union(fill)) if fill else air
            for poly in geo.polygons(shape):
                output.append({'polygon': list(poly.exterior.coords)[:-1], 'holes': [list(r.coords)[:-1] for r in poly.interiors],
                               'elevation_m': low, 'height_m': high-low})
        if not volume:
            continue
        source_volume = geo.room_volume(original)
        if volume/source_volume > .1:
            raise core.ValidationError('柱体占据超过10%空气体积，拒绝自动集总：'+room['id'])
        room['segments'] = output
        low = min(p['elevation_m'] for p in output)
        base = unary_union([Polygon(p['polygon'], p.get('holes', [])) for p in output if abs(p['elevation_m']-low) < 1e-7])
        if base.geom_type != 'Polygon':
            raise core.ValidationError('柱体简化后底面分离，拒绝自动处理：'+room['id'])
        room['polygon'] = list(base.exterior.coords)[:-1]
        room['holes'] = [list(r.coords)[:-1] for r in base.interiors]
        report.append({'room_id': room['id'], 'source_column_ids': sorted(owners),
            'column_volume_m3': volume, 'exposed_lateral_area_m2': side_area,
            'equivalent_thickness_m': volume/side_area, 'source_air_volume_m3': source_volume,
            'source_net_floor_area_m2': geo.floor_area(original),
            'scope': 'Homogeneous lumped InternalMass scenario; column-to-slab conduction and geometric view factors approximated'})
    return derived, report
