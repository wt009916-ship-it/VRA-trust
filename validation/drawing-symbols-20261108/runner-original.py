"""Single frozen screening run; no tuning and no application writes."""
from pathlib import Path
from hashlib import sha256
import importlib.util,json,time,sys,platform
from PIL import Image
import numpy as np
import cv2

ROOT=Path('C:/Users/18483/AppData/Local/Temp/vra-symbol-detector-20261108')
HELP=Path(__file__).parent/'drawing-components'
sys.path.insert(0,str(HELP))
from evaluate import evaluate,match_count

def digest(p):return sha256(p.read_bytes()).hexdigest()
def save(p,data):p.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')

if sys.argv[1:] == ['freeze-labels']:
    p=ROOT/'public-positive-regions.json';assert not p.exists()
    save(p,{'image':'public-plan-new.jpg','source_sha256':digest(ROOT/'public-plan-new.jpg'),
       'annotation_nature':'Provisional AI visual annotations made before detector execution; not professional ground truth.',
       'coverage':'Partial positive regions only. Unlisted openings and ambiguous symbols are NOT negatives. No precision or wall IoU can be claimed.',
       'door_boxes':[[60,8,96,41],[329,8,369,44],[112,99,147,127],[302,293,336,326],[369,125,404,154]],
       'window_boxes':[[129,6,157,22],[205,6,239,23],[398,6,431,23],[29,47,46,75],[29,168,46,204],[80,303,141,323],[212,303,269,323],[493,102,513,142],[493,201,513,230],[493,293,513,332],[409,407,457,428]],
       'matching_iou':0.5,'frozen_before_recognition':True})
    print('Provisional partial labels frozen; no inference run.');sys.exit()

OUT=ROOT/'results';OUT.mkdir(exist_ok=False)
manifest=json.loads((ROOT/'frozen-reference/manifest.json').read_text())
assert digest(ROOT/'symbol_detector-frozen.py')==manifest['method_sha256']
assert digest(HELP/'evaluate.py')==manifest['evaluator_sha256']
labels=json.loads((ROOT/'public-positive-regions.json').read_text())
assert digest(ROOT/labels['image'])==labels['source_sha256']
spec=importlib.util.spec_from_file_location('frozen_detector',ROOT/'symbol_detector-frozen.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
references=[];predictions=[];runs=[]
start=time.perf_counter()
for row in manifest['cases']:
    name=row['image_id'];source=ROOT/'frozen-reference'/f'{name}.png'
    assert digest(source)==row['source_sha256']
    maskfile=ROOT/'frozen-reference'/row['wall_mask_file'];assert digest(maskfile)==row['wall_mask_sha256']
    base={k:row[k] for k in ('image_id','source_sha256','width','height')}
    references.append({**base,'boxes':row['boxes'],'wall_mask':(np.asarray(Image.open(maskfile))>0).astype(int).tolist()})
    tick=time.perf_counter()
    try:
        with Image.open(source) as im:result,mask=module.detect(im)
        mask.save(OUT/f'{name}-wall.png')
        predictions.append({**base,'boxes':[{'category':x['category'],'box':x['box']} for x in result['candidates']],
                            'wall_mask':(np.asarray(mask)>0).astype(int).tolist()})
        error=None
    except Exception as exc:result=None;error=f'{type(exc).__name__}: {exc}'
    run={'image_id':name,'seconds':time.perf_counter()-tick,'error':error,'result':result}
    save(OUT/f'{name}.json',run);runs.append(run)
    print(json.dumps({k:run[k] for k in ('image_id','seconds','error')}),flush=True)
groups={}
for group in ('clean','degraded','negative'):
    ids={r['image_id'] for r in manifest['cases'] if r['group']==group}
    groups[group]=evaluate([r for r in references if r['image_id'] in ids],[p for p in predictions if p['image_id'] in ids])
public=[]
for kind in ('new','prior'):
    name=f'public-plan-{kind}';source=ROOT/f'{name}.jpg';tick=time.perf_counter()
    with Image.open(source) as im:result,mask=module.detect(im)
    mask.save(OUT/f'{name}-wall.png')
    row={'image_id':name,'source_sha256':digest(source),'seconds':time.perf_counter()-tick,'result':result}
    if kind=='new':
        row['partial_positive_matches']={}
        for c in ('door','window'):
            expected=labels[c+'_boxes'];actual=[x['box'] for x in result['candidates'] if x['category']==c]
            row['partial_positive_matches'][c]={'matched':match_count(expected,actual,.5),'annotated_positive_regions':len(expected),'total_predictions':len(actual),
                                                'precision':None,'full_image_recall':None,'reason':'partial provisional labels, no exhaustive professional reference'}
    save(OUT/f'{name}.json',row);public.append(row)
clean=groups['clean'];bad=groups['degraded'];neg=groups['negative']
gates={}
for c in ('door','window'):
    for metric in ('precision','recall'):gates[f'clean_{c}_{metric}']=(clean['instances'][c][metric] or 0)>=.85
    gates[f'degraded_{c}_f1']=(bad['instances'][c]['f1'] or 0)>=.7
gates.update(clean_wall_micro=(clean['wall']['micro_iou'] or 0)>=.8,clean_wall_macro=(clean['wall']['macro_iou'] or 0)>=.75,
             degraded_wall_micro=(bad['wall']['micro_iou'] or 0)>=.65,
             negatives_opening=sum(neg['instances'][c]['fp'] for c in ('door','window'))==0,
             negatives_wall=all(r['wall']['fp_pixels']/(768*768)<=.01 for r in neg['cases']),
             no_errors=not any(r['error'] for r in runs))
summary={'manifest_sha256':digest(ROOT/'frozen-reference/manifest.json'),'method_sha256':manifest['method_sha256'],
         'partial_public_labels_sha256':digest(ROOT/'public-positive-regions.json'),'groups':groups,'gates':gates,'gate_passed':all(gates.values()),
         'public_positive_matches':public[0]['partial_positive_matches'],'total_seconds':time.perf_counter()-start,
         'runtime':{'python':platform.python_version(),'opencv':cv2.__version__,'numpy':np.__version__},
         'application_integrated':False,'training':False,'score_change':0}
save(OUT/'summary.json',summary)
print(json.dumps({**{k:v for k,v in summary.items() if k!='groups'},'metrics':{g:{'instances':v['instances'],'wall':v['wall']} for g,v in groups.items()}},indent=2),flush=True)
