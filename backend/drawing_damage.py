"""Bounded scan enhancement and visible-line gap proposals in source coordinates.

OpenCV operations produce review candidates, never recovered original walls.
Large erased regions, unseen rooms and symbols are deliberately not synthesised.
"""
import time
import cv2
import numpy as np

from . import core


def map_points(points, inverse, offset=(0, 0)):
    values = np.asarray(points, dtype=float).reshape(-1, 2)
    mapped = np.column_stack((values, np.ones(len(values)))) @ np.asarray(inverse).T
    return [[float(x+offset[0]), float(y+offset[1])] for x, y in mapped]


def weighted_median(values, weights):
    order = np.argsort(values)
    return float(np.asarray(values)[order][np.searchsorted(np.cumsum(np.asarray(weights)[order]), sum(weights)/2)])


def line_kernel(length, angle):
    size = max(3, int(length) | 1)
    kernel = np.zeros((size, size), dtype=np.uint8)
    radians = np.deg2rad(angle)
    delta = np.array([np.cos(radians), np.sin(radians)])*(size-1)/2
    mid = np.array([size//2, size//2])
    cv2.line(kernel, tuple(np.rint(mid-delta).astype(int)), tuple(np.rint(mid+delta).astype(int)), 1, 1)
    return kernel


def prepare(rgb, options, offset=(0, 0)):
    start = time.perf_counter()
    factor = options.scale_to_m
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    saturation = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)[:, :, 1]
    background = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, np.ones((41, 41), np.uint8))
    normal = cv2.divide(gray, np.maximum(background, 1), scale=255)
    threshold, ink = cv2.threshold(normal, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    ink[saturation > 60] = 0
    run = max(8, min(100, round(.5/factor)))
    lines = cv2.HoughLinesP(ink, 1, np.pi/720, threshold=max(25, run),
                           minLineLength=max(40, run*2), maxLineGap=2)
    angles, lengths = [], []
    for x, y, a, b in ([] if lines is None else lines.reshape(-1, 4)):
        angle = np.rad2deg(np.arctan2(b-y, a-x))
        angle = (angle+45) % 90-45
        if abs(angle) <= 12:
            angles.append(angle)
            lengths.append(float(np.hypot(a-x, b-y)))
    skew = weighted_median(angles, lengths) if angles else 0.
    spread = weighted_median([abs(a-skew) for a in angles], lengths) if angles else None
    supported = len(angles) >= 4 and spread < 1.5
    applied = skew if options.deskew and supported and abs(skew) > .15 else 0.
    h, w = ink.shape
    if applied:
        # Refine Hough quantisation by alignment of observed strokes, never by room count.
        small = cv2.resize(ink, (max(1, round(w*min(1, 800/max(h, w)))),
                                 max(1, round(h*min(1, 800/max(h, w))))), interpolation=cv2.INTER_AREA)
        def alignment(angle):
            sh, sw = small.shape
            m = cv2.getRotationMatrix2D((sw/2, sh/2), angle, 1)
            mask = cv2.warpAffine(small, m, (sw, sh), flags=cv2.INTER_NEAREST)
            return float(sum(np.square(mask.sum(axis=axis, dtype=float)).sum() for axis in (0, 1)))
        applied = float(max(np.arange(max(-12, skew-1.5), min(12, skew+1.5)+.001, .1), key=alignment))
    matrix = cv2.getRotationMatrix2D((w/2, h/2), applied, 1)
    inverse = cv2.invertAffineTransform(matrix)
    rectified = cv2.warpAffine(ink, matrix, (w, h), flags=cv2.INTER_NEAREST, borderValue=0)
    # Opening retains observed, sufficiently long strokes. No neural completion.
    directions = {0., 90.}
    tilted = cv2.HoughLinesP(rectified, 1, np.pi/360, threshold=max(20, run), minLineLength=max(30, run), maxLineGap=1)
    histogram = {}
    for x, y, a, b in ([] if tilted is None else tilted.reshape(-1, 4)):
        angle = round((np.rad2deg(np.arctan2(b-y, a-x)) % 180)/5)*5 % 180
        histogram[angle] = histogram.get(angle, 0)+float(np.hypot(a-x, b-y))
    directions.update(a for a, length in sorted(histogram.items(), key=lambda r: -r[1])[:8]
                      if min(a, abs(90-a), 180-a) >= 10 and length >= run*3)
    observed = np.zeros_like(rectified)
    masks = []
    for angle in sorted(directions):
        mask = cv2.morphologyEx(rectified, cv2.MORPH_OPEN, line_kernel(run, angle))
        observed |= mask
        masks.append((angle, mask))
    gap_m = max(options.closure_m, options.damage_gap_m)
    gap_px = max(1, round(gap_m/factor))
    if gap_px > 300:
        raise core.ValidationError('破损补接超过300像素，请核对比例或减小补接距离')
    walls = observed.copy()
    for angle, mask in masks:
        if gap_px > 1:
            walls |= cv2.morphologyEx(mask, cv2.MORPH_CLOSE, line_kernel(gap_px, angle))
    automatic_walls = walls.copy()
    manual = []
    for x1, y1, x2, y2 in options.manual_bridges_px:
        local = np.array([[x1-offset[0], y1-offset[1]], [x2-offset[0], y2-offset[1]]], dtype=float)
        if not ((local[:, 0] >= 0).all() and (local[:, 0] < w).all() and
                (local[:, 1] >= 0).all() and (local[:, 1] < h).all()):
            raise core.ValidationError('人工补接端点超出所选平面裁剪范围')
        distance = float(np.linalg.norm(local[1]-local[0]))
        if distance < 2 or distance*factor > 5 or distance > 400:
            raise core.ValidationError('每条人工补接须为2–400像素且不超过5米，不能凭空补全大面积缺页')
        aligned = np.column_stack((local, np.ones(2))) @ matrix.T
        start_px, end_px = [tuple(np.rint(p).astype(int)) for p in aligned]
        cv2.line(walls, start_px, end_px, 255, 3)
        manual.append({'kind': 'engineer_drawn_bridge', 'source_endpoints_px': [[x1,y1],[x2,y2]],
            'length_m': distance*factor, 'basis': options.manual_bridge_basis,
            'status': 'ASSUMED_REQUIRES_REVIEW', 'does_not_prove_wall_or_opening_type': True})
    added = ((automatic_walls > 0) & (observed == 0)).astype('uint8')
    count, _, stats, _ = cv2.connectedComponentsWithStats(added, connectivity=8)
    proposals = []
    for index in range(1, count):
        x, y, sw, sh, pixels = map(int, stats[index])
        if pixels < 2:
            continue
        ring = map_points([(x, y), (x+sw, y), (x+sw, y+sh), (x, y+sh)], inverse, offset)
        proposals.append({'id': 'repair_'+core.hash_json([ring, gap_m])[:16],
            'kind': 'line_gap_proposal', 'status': 'INFERRED_REQUIRES_REVIEW',
            'polygon_px': ring, 'added_pixel_count': pixels, 'added_ink_area_m2': pixels*factor**2,
            'maximum_requested_gap_m': gap_m, 'basis': 'Collinear visible strokes; may be a door, damage or annotation, not a proven wall'})
    if len(proposals) > 500:
        raise core.ValidationError('断线补接提议超过500处，请裁切并减小补接距离；未静默丢弃明细')
    return walls, inverse, {
        'engine': 'OpenCV local illumination normalization, Hough deskew and directional morphology',
        'opencv_version': cv2.__version__, 'rules_sha256': core.sha(__file__),
        'quality': {'source_gray_p10_p90': [float(v) for v in np.percentile(gray, [10, 90])],
                    'otsu_threshold': float(threshold), 'laplacian_variance': float(cv2.Laplacian(gray, cv2.CV_64F).var())},
        'coordinate_transform': {'source_to_analysis': matrix.tolist(), 'analysis_to_source': inverse.tolist(),
                                 'source_crop_offset_px': list(offset), 'scale_changed': False},
        'deskew': {'estimated_degrees': skew, 'angular_mad_degrees': spread,
                   'supporting_lines': len(angles), 'applied_degrees': applied, 'sufficient_support': supported,
                   'refinement': 'Observed ink projection alignment within 1.5 degrees of robust Hough estimate'},
        'visible_ink_pixels': int(np.count_nonzero(observed)), 'proposed_ink_pixels': int(np.count_nonzero(added)),
        'directions_degrees': sorted(directions), 'repairs': proposals,
        'manual_bridges': manual,
        'geometry_seconds': time.perf_counter()-start,
        'scope': 'Visible-line candidates only; erasures, torn-off pages, missing storeys, hidden rooms and symbol classes remain unknown',
        'coverage_complete': False,
    }
