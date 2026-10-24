"""Explicit reconstruction from IFC footprint AND consistent source quantities.

A bounding box or import-default height is never sufficient. The reconstruction
preserves all source locators and remains an inferred, reviewable extrusion.
"""
import numpy as np
from shapely.geometry import Polygon


def reconstruct(document, space):
    from ifcopenshell.util.placement import get_local_placement
    from ifcopenshell.util.unit import calculate_unit_scale, get_unit_scale
    factor = calculate_unit_scale(document)
    representations = space.Representation.Representations
    curves = []
    for rep in representations:
        if rep.RepresentationIdentifier != 'FootPrint':
            continue
        for item in rep.Items:
            curves.extend(item.Elements if item.is_a('IfcGeometricCurveSet') else [item])
    if len(curves) != 1 or not curves[0].is_a('IfcPolyline'):
        raise ValueError('重建需要唯一闭合直线 FootPrint；多环/曲线不可用包围盒替代')
    curve = curves[0]
    pts = [list(p.Coordinates) for p in curve.Points]
    if len(pts) < 4 or pts[0] != pts[-1]:
        raise ValueError('FootPrint 不是闭合轮廓')
    placement = get_local_placement(space.ObjectPlacement)
    if np.linalg.norm(placement[:3, 2]-[0, 0, 1]) > 1e-6:
        raise ValueError('FootPrint 带倾斜放置，不能用垂直拉伸重建')
    xyz = [(placement @ np.array([*p, *([0.]*(3-len(p))), 1.]))[:3]*factor for p in pts[:-1]]
    z = float(xyz[0][2])
    if any(abs(p[2]-z) > 1e-5 for p in xyz):
        raise ValueError('FootPrint 不在水平面')
    polygon = Polygon([(float(p[0]), float(p[1])) for p in xyz])
    if not polygon.is_valid or polygon.interiors or polygon.area < .05:
        raise ValueError('FootPrint 自交/带孔/过小')
    quantities = {}
    kinds = {'Height': ('IfcQuantityLength', 'LengthValue', 'LENGTHUNIT'),
             'NetFloorArea': ('IfcQuantityArea', 'AreaValue', 'AREAUNIT'),
             'NetVolume': ('IfcQuantityVolume', 'VolumeValue', 'VOLUMEUNIT')}
    for relation in space.IsDefinedBy:
        definition = getattr(relation, 'RelatingPropertyDefinition', None)
        if not definition or not definition.is_a('IfcElementQuantity'):
            continue
        for quantity in definition.Quantities:
            if quantity.Name not in kinds:
                continue
            kind, attr, unit = kinds[quantity.Name]
            if not quantity.is_a(kind):
                continue
            value = float(getattr(quantity, attr)) * (get_unit_scale(quantity.Unit) if quantity.Unit else calculate_unit_scale(document, unit))
            previous = quantities.get(quantity.Name)
            if previous and abs(previous['value']-value) > .00001:
                raise ValueError('同名 IFC 工程量互相冲突：'+quantity.Name)
            quantities[quantity.Name] = {'value': value, 'entity_id': quantity.id(), 'set': definition.Name}
    if set(quantities) != set(kinds):
        raise ValueError('重建缺少明确 Height、NetFloorArea 或 NetVolume 工程量；不使用默认层高')
    height, area, volume = [quantities[key]['value'] for key in ('Height', 'NetFloorArea', 'NetVolume')]
    if not .5 < height <= 30 or area <= 0 or volume <= 0:
        raise ValueError('IFC 工程量超出有效范围')
    area_error = 100*(polygon.area-area)/area
    volume_error = 100*(polygon.area*height-volume)/volume
    if max(abs(area_error), abs(volume_error)) > 1:
        raise ValueError(f'FootPrint × Height 与源工程量不一致：面积 {area_error:.3f}%，体积 {volume_error:.3f}%')
    section = {'polygon': list(polygon.exterior.coords)[:-1], 'elevation_m': z, 'height_m': height}
    provenance = {'method': 'IFC_FOOTPRINT_QUANTITY_EXTRUSION', 'footprint_entity_id': curve.id(),
                  'quantities': quantities, 'area_error_percent': area_error, 'volume_error_percent': volume_error,
                  'assumption': 'Constant vertical extrusion inferred from consistent footprint/height/area/volume; missing original Body.'}
    return [section], provenance
