"""Independent floor-plan metrics; no application inference or ground-truth creation.

Inputs are already decoded reference/prediction records. Each reference contains
an image id, source SHA-256, dimensions, door/window boxes and a binary wall mask.
This module never chooses thresholds after seeing results or declares maturity.
"""
import math
import re

CLASSES = ('door', 'window')


def _mask(value, width, height):
    if not isinstance(value, list) or len(value) != height:
        raise ValueError('Mask must have exactly height rows')
    if any(not isinstance(row, list) or len(row) != width for row in value):
        raise ValueError('Mask must have exactly width columns')
    if any(type(x) is not int or x not in (0, 1) for row in value for x in row):
        raise ValueError('Wall masks must contain integer 0/1')
    return value


def _boxes(value, width, height):
    if not isinstance(value, list) or len(value) > 1000:
        raise ValueError('Boxes must be a list with at most 1000 instances')
    for row in value:
        if not isinstance(row, dict) or set(row) != {'category', 'box'} or row['category'] not in CLASSES:
            raise ValueError('Unsupported instance category/fields')
        box = row['box']
        if not isinstance(box, list) or len(box) != 4:
            raise ValueError('Expected [left, top, right, bottom] box')
        if any(type(x) not in (int, float) or not math.isfinite(x) for x in box):
            raise ValueError('Box coordinates must be finite numbers')
        left, top, right, bottom = box
        if not 0 <= left < right <= width or not 0 <= top < bottom <= height:
            raise ValueError('Box outside image or empty')
    return value


def _validate(record):
    expected = {'image_id', 'source_sha256', 'width', 'height', 'boxes', 'wall_mask'}
    if not isinstance(record, dict) or set(record) != expected:
        raise ValueError('Missing or unknown record fields')
    if not isinstance(record['image_id'], str) or not 1 <= len(record['image_id']) <= 200:
        raise ValueError('Invalid image id')
    if not isinstance(record['source_sha256'], str) or not re.fullmatch('[a-f0-9]{64}', record['source_sha256']):
        raise ValueError('Invalid source SHA-256')
    w, h = record['width'], record['height']
    if any(type(x) is not int or not 1 <= x <= 6000 for x in (w, h)) or w*h > 12_000_000:
        raise ValueError('Image dimensions exceed evaluation budget')
    _boxes(record['boxes'], w, h)
    _mask(record['wall_mask'], w, h)
    return record


def iou(a, b):
    intersection = max(0, min(a[2], b[2])-max(a[0], b[0])) * max(0, min(a[3], b[3])-max(a[1], b[1]))
    area_a = (a[2]-a[0])*(a[3]-a[1])
    area_b = (b[2]-b[0])*(b[3]-b[1])
    return intersection/(area_a+area_b-intersection)


def match_count(reference, prediction, threshold):
    """Maximum cardinality matching, independent of input order; not greedy IoU."""
    edges = [[j for j, target in enumerate(reference) if iou(box, target) >= threshold] for box in prediction]
    # Iterative augmenting paths avoid recursion-depth failure on dense detections.
    target_to_pred = {}
    pred_to_target = {}
    for start in range(len(prediction)):
        queue, seen_pred, seen_target, parent = [start], {start}, set(), {}
        free = None
        for p in queue:
            for target in edges[p]:
                if target in seen_target:
                    continue
                seen_target.add(target)
                parent[target] = p
                if target not in target_to_pred:
                    free = target
                    break
                other = target_to_pred[target]
                if other not in seen_pred:
                    seen_pred.add(other)
                    queue.append(other)
            if free is not None:
                break
        while free is not None:
            p = parent[free]
            previous = pred_to_target.get(p)
            pred_to_target[p] = free
            target_to_pred[free] = p
            free = previous
    return len(target_to_pred)


def instance_metrics(tp, fp, fn):
    return {'tp': tp, 'fp': fp, 'fn': fn,
            'precision': tp/(tp+fp) if tp+fp else None,
            'recall': tp/(tp+fn) if tp+fn else None,
            'f1': 2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None}


def evaluate(references, predictions, *, threshold=0.5):
    if type(threshold) not in (int, float) or not math.isfinite(threshold) or not 0 < threshold <= 1:
        raise ValueError('IoU threshold must be finite and in (0, 1]')
    if not isinstance(references, list) or not references or len(references) > 100:
        raise ValueError('Expected 1..100 reference records')
    if not isinstance(predictions, list) or len(predictions) > 100:
        raise ValueError('Expected up to 100 prediction records')
    # Validate all rows before calculating any metric. No silently dropped cases.
    refs, preds = {}, {}
    for records, lookup in ((references, refs), (predictions, preds)):
        for record in records:
            _validate(record)
            if record['image_id'] in lookup:
                raise ValueError('Duplicate image id')
            lookup[record['image_id']] = record
    if set(preds)-set(refs):
        raise ValueError('Prediction references an unknown image')
    totals = {c: [0, 0, 0] for c in CLASSES}
    wall_total = [0, 0, 0]
    rows = []
    for image_id, reference in refs.items():
        prediction = preds.get(image_id)
        if prediction:
            if any(prediction[k] != reference[k] for k in ('source_sha256', 'width', 'height')):
                raise ValueError('Prediction source or coordinate frame mismatch')
        row = {'image_id': image_id, 'prediction_missing': prediction is None, 'instances': {}}
        for category in CLASSES:
            expected = [x['box'] for x in reference['boxes'] if x['category'] == category]
            actual = [x['box'] for x in prediction['boxes'] if x['category'] == category] if prediction else []
            tp = match_count(expected, actual, threshold)
            counts = [tp, len(actual)-tp, len(expected)-tp]
            totals[category] = [a+b for a, b in zip(totals[category], counts)]
            row['instances'][category] = instance_metrics(*counts)
        tp = fp = fn = 0
        for y, line in enumerate(reference['wall_mask']):
            for x, target in enumerate(line):
                value = prediction['wall_mask'][y][x] if prediction else 0
                tp += value == 1 and target == 1
                fp += value == 1 and target == 0
                fn += value == 0 and target == 1
        wall_total = [a+b for a, b in zip(wall_total, (tp, fp, fn))]
        row['wall'] = {'tp_pixels': tp, 'fp_pixels': fp, 'fn_pixels': fn,
                       'iou': tp/(tp+fp+fn) if tp+fp+fn else None}
        rows.append(row)
    tp, fp, fn = wall_total
    return {'policy': 'independent-floorplan-metrics-v1', 'iou_threshold': threshold,
            'case_count': len(rows), 'missing_prediction_count': sum(r['prediction_missing'] for r in rows),
            'instances': {c: instance_metrics(*values) for c, values in totals.items()},
            'wall': {'tp_pixels': tp, 'fp_pixels': fp, 'fn_pixels': fn,
                     'micro_iou': tp/(tp+fp+fn) if tp+fp+fn else None,
                     'macro_iou': sum(r['wall']['iou'] for r in rows if r['wall']['iou'] is not None)/sum(r['wall']['iou'] is not None for r in rows)
                     if any(r['wall']['iou'] is not None for r in rows) else None},
            'cases': rows,
            'limitations': ['No pass/fail or score awarded by this evaluator.',
                            'Undefined empty-class metrics are null, never automatic perfect scores.',
                            'Missing predictions incur false negatives and remain explicitly flagged.',
                            'Labels need independent provenance and review; metrics cannot establish label correctness.',
                            'Axis-aligned opening boxes evaluate location/class, not opening topology or engineering dimensions.']}
