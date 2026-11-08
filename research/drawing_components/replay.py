"""Re-score saved predictions. This does NOT invoke the vision model."""
import argparse
import json
from pathlib import Path
from hashlib import sha256
from PIL import Image
from evaluate import evaluate


def sha(path):return sha256(path.read_bytes()).hexdigest()

def binary_mask(path):
    with Image.open(path) as image:
        if image.mode!='L':raise ValueError('Expected binary grayscale mask')
        if any(count and value not in (0,255) for value,count in enumerate(image.histogram())):raise ValueError('Nonbinary mask')
        w,h=image.size
        return [[1 if image.getpixel((x,y)) else 0 for x in range(w)] for y in range(h)]


def replay(bundle):
    index=json.loads((bundle/'bundle.json').read_text(encoding='utf-8'))
    for name,digest in index['files'].items():
        path=(bundle/name).resolve()
        if not path.is_relative_to(bundle.resolve()) or sha(path)!=digest:raise ValueError('Bundle hash mismatch: '+name)
    manifest=json.loads((bundle/'frozen-reference/manifest.json').read_text(encoding='utf-8'))
    original=json.loads((bundle/'florence-screen/result.json').read_text(encoding='utf-8'))
    if sha(bundle/'frozen-reference/manifest.json')!=original['manifest_sha256']:raise ValueError('Source manifest mismatch')
    if sha(Path(__file__).with_name('evaluate.py'))!=manifest['hashes']['evaluator']:raise ValueError('Evaluator differs from frozen baseline')
    refs=[];preds=[]
    for case in manifest['cases']:
        image=bundle/'frozen-reference'/(case['image_id']+'.png')
        mask=bundle/'frozen-reference'/case['wall_mask_file']
        if sha(image)!=case['source_sha256'] or sha(mask)!=case['wall_mask_sha256']:raise ValueError('Reference source mismatch')
        boxes=json.loads((bundle/'florence-screen'/(case['image_id']+'-boxes.json')).read_text(encoding='utf-8'))
        if boxes['image_id']!=case['image_id'] or boxes['source_sha256']!=case['source_sha256']:raise ValueError('Prediction binding mismatch')
        base={k:case[k] for k in ('image_id','source_sha256','width','height')}
        refs.append({**base,'boxes':case['boxes'],'wall_mask':binary_mask(mask)})
        preds.append({**base,'boxes':boxes['boxes'],'wall_mask':binary_mask(bundle/'florence-screen'/(case['image_id']+'-wall-predicted.png'))})
    rows={}
    for group in ('rendered_clean','rendered_degraded','negative'):
        ids={c['image_id'] for c in manifest['cases'] if c['group']==group}
        actual=evaluate([r for r in refs if r['image_id'] in ids],[p for p in preds if p['image_id'] in ids],threshold=manifest['iou_threshold'])
        if actual!=original['summaries'][group]:raise ValueError('Recomputed metrics disagree: '+group)
        rows[group]={'door':actual['instances']['door'],'window':actual['instances']['window'],'wall_micro_iou':actual['wall']['micro_iou']}
    return {'recomputed_metrics_match':True,'inference_rerun':False,'verified_files':len(index['files']),
            'original_screen_passed':original['screen_passed'],'groups':rows}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('bundle',type=Path)
    args=parser.parse_args()
    print(json.dumps(replay(args.bundle),ensure_ascii=False,indent=2))
