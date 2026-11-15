"""Bounded raster line observations and explicitly hypothetical short gaps.

No pixels are repaired here. Neither a detected segment nor a collinear gap
identifies a wall, opening, dimension, structural member or safe modification.
"""
import math

POLICY = 'raster-linework-hypotheses-v1'
MAX_SIDE = 1600
MAX_RAW = 4096
MAX_LINES = 256
MAX_GAPS = 100
PARAMETERS = {'threshold_gray': 128, 'min_line_px': 40, 'hough_votes': 40,
              'hough_gap_px': 0, 'angle_tolerance_degrees': 1.0,
              'offset_tolerance_px': 1.25, 'min_gap_px': 2.0, 'max_gap_px': 8.0,
              'min_observed_support': 0.85, 'max_gap_dark_fraction': 0.25,
              'max_observed_endpoint_extension_px': 40}


def segment(row):
    a, b = list(map(float, row[:2])), list(map(float, row[2:]))
    if a > b:
        a, b = b, a
    length = math.dist(a, b)
    if not length:
        raise ValueError('Zero-length detected segment')
    return {'a': a, 'b': b, 'length': length,
            'direction': [(b[0]-a[0])/length, (b[1]-a[1])/length]}


def project(point, origin, direction):
    return sum((v-o)*d for v, o, d in zip(point, origin, direction))


def collinear(a, b):
    dx, dy = a['direction']
    ex, ey = b['direction']
    if abs(dx*ey-dy*ex) > math.sin(math.radians(PARAMETERS['angle_tolerance_degrees'])):
        return False
    return max(abs((p[0]-a['a'][0])*dy-(p[1]-a['a'][1])*dx) for p in (b['a'], b['b'])) <= PARAMETERS['offset_tolerance_px']


def interval_gap(a, b):
    if not collinear(a, b):
        return None
    first, second = sorted((project(b[p], a['a'], a['direction']), b[p]) for p in ('a', 'b'))
    if first[0] > a['length']:
        start, end = a['b'], first[1]
    elif second[0] < 0:
        start, end = second[1], a['a']
    else:
        return None
    distance = math.dist(start, end)
    return (start, end, distance) if PARAMETERS['min_gap_px'] <= distance <= PARAMETERS['max_gap_px'] else None


def samples(mask, start, end, *, interior=False):
    import numpy as np
    count = max(3, math.ceil(math.dist(start, end))+1)
    points = np.linspace(start, end, count)
    if interior:
        points = points[1:-1]
    xy = np.rint(points).astype(int)
    xy[:, 0] = np.clip(xy[:, 0], 0, mask.shape[1]-1)
    xy[:, 1] = np.clip(xy[:, 1], 0, mask.shape[0]-1)
    return float(mask[xy[:, 1], xy[:, 0]].mean())


def observed_endpoints(row, mask):
    """Recover adjacent ink discarded by Hough; never step across white pixels."""
    ends = []
    for name, sign in (('a', -1), ('b', 1)):
        start = row[name]
        last = list(start)
        for step in range(1, 2*PARAMETERS['max_observed_endpoint_extension_px']+1):
            x, y = [round(p+sign*d*step/2) for p, d in zip(start, row['direction'])]
            if not (0 <= x < mask.shape[1] and 0 <= y < mask.shape[0]) or not mask[y, x]:
                break
            last = [x, y]
        ends.extend(last)
    return segment(ends)


def analyse(image, text_polygons=(), *, preview_path=None):
    import cv2
    import numpy as np
    from PIL import Image

    if min(image.size) < 1 or max(image.size) > 6000 or image.width*image.height > 12_000_000:
        raise ValueError('Source raster outside linework budget')
    reduced = image.copy()
    reduced.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.BILINEAR)
    sx, sy = image.width/reduced.width, image.height/reduced.height
    dark = np.asarray(reduced.convert('L')) < PARAMETERS['threshold_gray']
    excluded = np.zeros(dark.shape, dtype='uint8')
    for polygon in text_polygons:
        if len(polygon) != 4 or not all(len(p) == 2 and all(type(v) in (int, float) and math.isfinite(v) for v in p)
                                      and 0 <= p[0] <= image.width and 0 <= p[1] <= image.height for p in polygon):
            raise ValueError('Invalid text exclusion polygon')
        points = np.rint([[p[0]/sx, p[1]/sy] for p in polygon]).astype('int32')
        cv2.fillPoly(excluded, [points], 1)
    excluded = cv2.dilate(excluded, np.ones((3, 3), dtype='uint8'))
    ink = (dark & ~excluded.astype(bool)).astype('uint8')*255
    cv2.setNumThreads(1)
    cv2.setRNGSeed(0)
    detected = cv2.HoughLinesP(ink, 1, math.pi/1800, PARAMETERS['hough_votes'],
                             minLineLength=PARAMETERS['min_line_px'], maxLineGap=PARAMETERS['hough_gap_px'])
    base = {'policy': POLICY, 'status': 'observations_and_hypotheses_require_review',
            'source_size': list(image.size), 'analysis_size': list(reduced.size),
            'analysis_to_source': [sx, 0, 0, 0, sy, 0],
            'coordinate_basis': 'normalized source raster pixel-edge coordinates; detected pixel centres add 0.5 before scaling',
            'parameters': dict(PARAMETERS), 'lines': [], 'gaps': [], 'truncated': False,
            'original_pixels_modified': False, 'automatic_gap_fill': False,
            'probability_of_correctness': None,
            'limitations': ['直线像素候选不等于墙、门窗、结构构件或尺寸识别。',
                            '短间隔共线只能形成几何假设；真实开口、符号及扫描缺损可能外观相同，不能自动补线。',
                            '支持率是阈值后线上暗像素比例，不是正确概率；没有检出不表示原图不存在。',
                            '分析可能缩放，文字候选区域被排除；细线、弧线、重叠和低对比度可能遗漏。']}
    if preview_path is not None:
        import hashlib
        reduced.save(preview_path, format='PNG')
        if preview_path.stat().st_size > 8*1024*1024:
            raise ValueError('Linework preview exceeds export budget')
        base['preview_sha256'] = hashlib.sha256(preview_path.read_bytes()).hexdigest()
        base['preview_basis'] = 'Analysis-sized source thumbnail; no gap pixels added; original normalized raster retained separately'
    if detected is None:
        return {**base, 'status': 'no_lines_detected_not_proof_of_absence', 'raw_line_count': 0}
    if not (detected.ndim == 2 and detected.shape[1] == 4 or detected.ndim == 3 and detected.shape[1:] == (1, 4)):
        raise ValueError('Unexpected native line shape')
    raw = detected.reshape(-1, 4)
    base['raw_line_count'] = len(raw)
    if len(raw) > MAX_RAW:
        return {**base, 'status': 'line_budget_exceeded', 'truncated': True}
    if not np.isfinite(raw).all() or not ((raw[:, [0, 2]] >= 0).all() and (raw[:, [0, 2]] < reduced.width).all()
                                          and (raw[:, [1, 3]] >= 0).all() and (raw[:, [1, 3]] < reduced.height).all()):
        raise ValueError('Detected line outside analysis raster')
    candidates = [observed_endpoints(segment(row), ink) for row in raw
                  if math.dist(row[:2], row[2:]) >= PARAMETERS['min_line_px']]
    candidates.sort(key=lambda r: (-r['length'], r['a'], r['b']))
    kept = []
    for row in candidates:
        support = samples(dark, row['a'], row['b'])
        if support < PARAMETERS['min_observed_support']:
            continue
        duplicate = False
        for old in kept:
            if collinear(old, row):
                low, high = sorted(project(row[p], old['a'], old['direction']) for p in ('a', 'b'))
                if max(0, min(high, old['length'])-max(0, low)) >= 0.9*row['length']:
                    duplicate = True
                    break
        if duplicate:
            continue
        if len(kept) == MAX_LINES:
            base['truncated'] = True
            break
        kept.append({**row, 'support': support})
    def source(point):
        return [(point[0]+0.5)*sx, (point[1]+0.5)*sy]
    for index, row in enumerate(kept, 1):
        row['candidate_id'] = f'line_{index}'
        base['lines'].append({'candidate_id': row['candidate_id'], 'points_source_px': [source(row['a']), source(row['b'])],
                              'observed_dark_support': row['support'], 'source_kind': 'RASTER_LINE_CANDIDATE',
                              'building_component': None, 'review_required': True})
    seen = set()
    for index, a in enumerate(kept):
        for b in kept[index+1:]:
            gap = interval_gap(a, b)
            if gap is None:
                continue
            start, end, distance = gap
            if samples(excluded, start, end, interior=True) > 0:
                continue
            darkness = samples(dark, start, end, interior=True)
            if darkness > PARAMETERS['max_gap_dark_fraction']:
                continue
            key = tuple(round(v, 1) for p in sorted((start, end)) for v in p)
            if key in seen:
                continue
            seen.add(key)
            if len(base['gaps']) == MAX_GAPS:
                base['truncated'] = True
                return base
            base['gaps'].append({'candidate_id': f'gap_{len(base["gaps"])+1}',
                                 'points_source_px': [source(start), source(end)],
                                 'supporting_line_ids': [a['candidate_id'], b['candidate_id']],
                                 'gap_analysis_px': distance, 'observed_dark_fraction': darkness,
                                 'source_kind': 'INFERRED_GEOMETRY_NOT_ENGINEERING', 'review_required': True,
                                 'interpretation': '短共线空隙；可能是缺损，也可能是设计开口或符号间隔，含义未知。'})
    return base
