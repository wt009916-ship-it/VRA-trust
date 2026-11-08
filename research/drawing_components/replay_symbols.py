"""Verify stored symbol-screen evidence and independently recompute metrics."""
import argparse
import json
from pathlib import Path
from hashlib import sha256
from evaluate import evaluate, match_count
from replay import binary_mask


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def replay_symbols(bundle):
    index = json.loads((bundle / 'bundle.json').read_text(encoding='utf-8'))
    for name, expected in index['files'].items():
        path = (bundle / name).resolve()
        if not path.is_relative_to(bundle.resolve()) or digest(path) != expected:
            raise ValueError('Evidence hash mismatch: ' + name)
    manifest = json.loads((bundle / 'frozen-reference/manifest.json').read_text(encoding='utf-8'))
    stored = json.loads((bundle / 'results/summary.json').read_text(encoding='utf-8'))
    if digest(bundle / 'frozen-reference/manifest.json') != stored['manifest_sha256']:
        raise ValueError('Reference manifest changed')
    if digest(Path(__file__).with_name('evaluate.py')) != manifest['evaluator_sha256']:
        raise ValueError('Evaluator differs from frozen version')
    if digest(bundle / 'symbol_detector-frozen.py') != manifest['method_sha256']:
        raise ValueError('Detector differs from frozen version')
    refs, preds = [], []
    for case in manifest['cases']:
        name = case['image_id']
        source = bundle / 'frozen-reference' / (name + '.png')
        target = bundle / 'frozen-reference' / case['wall_mask_file']
        if digest(source) != case['source_sha256'] or digest(target) != case['wall_mask_sha256']:
            raise ValueError('Reference binding mismatch')
        base = {k: case[k] for k in ('image_id', 'source_sha256', 'width', 'height')}
        refs.append({**base, 'boxes': case['boxes'], 'wall_mask': binary_mask(target)})
        run = json.loads((bundle / 'results' / (name + '.json')).read_text(encoding='utf-8'))
        if run['image_id'] != name:
            raise ValueError('Prediction binding mismatch')
        if run['error'] is None:
            boxes = [{'category': r['category'], 'box': r['box']} for r in run['result']['candidates']]
            preds.append({**base, 'boxes': boxes,
                          'wall_mask': binary_mask(bundle / 'results' / (name + '-wall.png'))})
    for group, label in (('clean', 'rendered_clean'), ('degraded', 'rendered_degraded'), ('negative', 'negative')):
        ids = {c['image_id'] for c in manifest['cases'] if c['group'] == label}
        actual = evaluate([r for r in refs if r['image_id'] in ids], [p for p in preds if p['image_id'] in ids],
                          threshold=manifest['iou_threshold'])
        if actual != stored['groups'][group]:
            raise ValueError('Recomputed metrics differ: ' + group)
    labels = json.loads((bundle / 'public-positive-regions.json').read_text(encoding='utf-8'))
    if digest(bundle / 'public-positive-regions.json') != stored['partial_public_labels_sha256']:
        raise ValueError('Provisional labels changed')
    if digest(bundle / labels['image']) != labels['source_sha256']:
        raise ValueError('Public source mismatch')
    public = json.loads((bundle / 'results/public-plan-new.json').read_text(encoding='utf-8'))
    for category in ('door', 'window'):
        predicted = [r['box'] for r in public['result']['candidates'] if r['category'] == category]
        expected = labels[category + '_boxes']
        actual = stored['public_positive_matches'][category]
        if actual != public['partial_positive_matches'][category] or actual['matched'] != match_count(expected, predicted, .5):
            raise ValueError('Partial positive matches differ')
        if actual['total_predictions'] != len(predicted) or actual['annotated_positive_regions'] != len(expected):
            raise ValueError('Partial positive counts differ')
    return {'verified_files': len(index['files']), 'metrics_match': True, 'inference_rerun': False,
            'original_gate_passed': stored['gate_passed'], 'partial_labels_are_not_expert_ground_truth': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle', type=Path)
    print(json.dumps(replay_symbols(parser.parse_args().bundle), indent=2))
