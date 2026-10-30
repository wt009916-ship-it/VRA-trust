"""Vectorize observed white pixel cells without losing self-touching contours.

Pixel centres are not polygon vertices: a one-pixel throat can be valid even
when OpenCV's centre contour doubles back on itself. Union horizontal cell runs
instead. Every interior island is retained, without deciding if it is ink or void.
"""
import numpy as np
from shapely.geometry import box
from shapely.ops import unary_union


def polygon(mask, factor):
    runs = []
    for y, row in enumerate(mask):
        changes = np.flatnonzero(np.diff(np.pad(row.astype(np.int8), (1, 1))))
        runs.extend(box(float(a)-.5, y-.5, float(b)-.5, y+.5)
                    for a, b in zip(changes[::2], changes[1::2]))
    original = unary_union(runs)
    if original.geom_type != 'Polygon' or not original.is_valid:
        raise ValueError('像素单元未形成单一有效区域，须人工拆分；未保留最大块并丢弃其他块')
    budget = min(.01, original.area*factor**2*.001)
    for tolerance in (.75, .375, .125, 0.):
        candidate = original.simplify(tolerance, preserve_topology=True)
        rings = [candidate.exterior, *candidate.interiors]
        delta = candidate.symmetric_difference(original).area*factor**2
        if (all(len(r.coords)-1 <= 256 for r in rings) and
                len(candidate.interiors) == len(original.interiors) and delta <= budget+1e-10):
            return candidate, {'method': 'union_of_observed_pixel_cells',
                'source_pixel_area_m2': original.area*factor**2,
                'symmetric_difference_m2': delta, 'area_budget_m2': budget,
                'maximum_boundary_displacement_px': candidate.hausdorff_distance(original),
                'simplification_tolerance_px': tolerance,
                'interior_islands': len(candidate.interiors)}
    raise ValueError('像素轮廓在面积守恒范围内仍超过256顶点，须拆分或人工修订')
