from pathlib import Path
from hashlib import sha256
from datetime import datetime,timezone
import json,os,sys,time,math,socket

ROOT=Path('C:/Users/18483/AppData/Local/Temp/vra-floorplan-feasibility-20261108')
OUT=ROOT/'florence-screen'
OUT.mkdir(exist_ok=False)
os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1',TOKENIZERS_PARALLELISM='false')
def offline(*args,**kwargs):raise RuntimeError('Networking disabled during local evaluation')
socket.create_connection=offline;socket.socket.connect=offline;socket.socket.connect_ex=offline
import torch
import transformers
from transformers import AutoProcessor,Florence2ForConditionalGeneration
from PIL import Image,ImageDraw
sys.path.insert(0,str(Path(__file__).parent/'drawing-components'))
from evaluate import evaluate

def sha(path):return sha256(path.read_bytes()).hexdigest()
def write(name,value):(OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')

manifest_path=ROOT/'frozen-reference/manifest.json'
manifest=json.loads(manifest_path.read_text())
downloads=json.loads((ROOT/'model-download-complete.json').read_text())
expected_files=set(json.loads((ROOT/'acquisition-metadata.json').read_text())['model_files'])-{'.gitattributes'}
assert {r['file'] for r in downloads['files']}==expected_files
assert manifest['model_revision']==downloads['revision']
assert transformers.__version__=='4.57.3' and torch.__version__=='2.10.0+cu128'
assert torch.cuda.is_available()
assert sha(Path(__file__).parent/'drawing-components/evaluate.py')==manifest['hashes']['evaluator']
for row in downloads['files']:assert sha(ROOT/'florence-model'/row['file'])==row['sha256']
for case in manifest['cases']:
    assert sha(ROOT/'frozen-reference'/(case['image_id']+'.png'))==case['source_sha256']
    assert sha(ROOT/'frozen-reference'/case['wall_mask_file'])==case['wall_mask_sha256']
torch.set_num_threads(4);torch.manual_seed(20261108)
torch.backends.cudnn.benchmark=False
write('inference-frozen.json',{'at':datetime.now(timezone.utc).isoformat(),'manifest_sha256':sha(manifest_path),
      'runner_sha256':sha(Path(__file__)),'model':downloads,'torch':torch.__version__,'transformers':transformers.__version__,
      'device':torch.cuda.get_device_name(0),'generation':manifest['generation'],'tasks':manifest['tasks'],
      'network':'disabled via local_files_only plus Python socket guards','training':False,
      'polygon_rule':'positive filled union of returned polygons; no inferred missing rings or smoothing',
      'box_rule':'one request per class; all returned boxes/polygon bounds retained, unexpected labels additionally fail the screen'})
model,loading=Florence2ForConditionalGeneration.from_pretrained(ROOT/'florence-model',local_files_only=True,trust_remote_code=False,
                  use_safetensors=True,torch_dtype=torch.float16,attn_implementation='eager',output_loading_info=True)
write('loading.json',loading)
assert not any(loading.get(k) for k in ('missing_keys','unexpected_keys','mismatched_keys','error_msgs'))
model=model.to('cuda').eval()
processor=AutoProcessor.from_pretrained(ROOT/'florence-model',local_files_only=True,trust_remote_code=False)
print('Pinned model loaded locally on GPU',flush=True)

def polygon_groups(value,width,height):
    if not isinstance(value,list) or len(value)>500:raise ValueError('Invalid polygon groups')
    groups=[]
    for group in value:
        if not isinstance(group,list) or len(group)>500:raise ValueError('Invalid polygon instance')
        paths=[]
        for coords in group:
            if not isinstance(coords,list) or not 6<=len(coords)<=4096 or len(coords)%2:raise ValueError('Invalid polygon coordinate count')
            points=list(zip(coords[::2],coords[1::2]))
            if not all(type(x) in (int,float) and type(y) in (int,float) and math.isfinite(x) and math.isfinite(y) and 0<=x<=width and 0<=y<=height for x,y in points):
                raise ValueError('Nonfinite/outside polygon')
            paths.append(points)
        groups.append(paths)
    return groups

predictions=[];references=[];errors=[];timings=[]
for case in manifest['cases']:
    name=case['image_id'];image=Image.open(ROOT/'frozen-reference'/(name+'.png')).convert('RGB');w,h=image.size
    boxes=[];mask=Image.new('L',(w,h));draw=ImageDraw.Draw(mask)
    base={k:case[k] for k in ('image_id','source_sha256','width','height')}
    ref_mask=Image.open(ROOT/'frozen-reference'/case['wall_mask_file']).convert('L')
    reference={**base,'boxes':case['boxes'],'wall_mask':[[1 if ref_mask.getpixel((x,y)) else 0 for x in range(w)] for y in range(h)]}
    references.append(reference)
    for category,prompt in manifest['tasks'].items():
        task=prompt[:prompt.index('>')+1];started=time.perf_counter()
        raw={'image_id':name,'category':category,'prompt':prompt,'task':task,'input_sha256':case['source_sha256']}
        try:
            inputs=processor(text=prompt,images=image,return_tensors='pt').to('cuda',torch.float16)
            with torch.inference_mode():generated=model.generate(**inputs,**manifest['generation'])
            torch.cuda.synchronize()
            raw.update(token_ids=generated[0].tolist(),text=processor.batch_decode(generated,skip_special_tokens=False)[0])
            if len(raw['token_ids'])>=manifest['generation']['max_new_tokens']+1:raise ValueError('Output reached generation cap; not accepted as complete')
            parsed=processor.post_process_generation(raw['text'],task=task,image_size=(w,h))[task]
            raw['parsed']=parsed
            groups=polygon_groups(parsed.get('polygons',[]),w,h)
            if category=='wall':
                for group in groups:
                    for points in group:draw.polygon(points,fill=255)
            else:
                values=parsed.get('bboxes',[])
                labels=parsed.get('bboxes_labels',[])+parsed.get('polygons_labels',[])
                if any(str(x).lower().strip().rstrip('.') not in (category,category+'s',prompt[len(task):]) for x in labels):
                    errors.append({'image_id':name,'category':category,'reason':'Unexpected output class label','labels':labels})
                if not isinstance(values,list) or len(values)>1000:raise ValueError('Invalid boxes')
                for group in groups:
                    points=[p for path in group for p in path]
                    if points:values.append([min(p[0] for p in points),min(p[1] for p in points),max(p[0] for p in points),max(p[1] for p in points)])
                for b in values:
                    if len(b)!=4 or any(type(v) not in (int,float) or not math.isfinite(v) for v in b) or not 0<=b[0]<b[2]<=w or not 0<=b[1]<b[3]<=h:
                        raise ValueError('Invalid/outside prediction box')
                    boxes.append({'category':category,'box':b})
            raw['status']='parsed'
        except Exception as exc:
            raw.update(status='failed',error_type=type(exc).__name__,error=str(exc))
            errors.append({'image_id':name,'category':category,'reason':str(exc)})
        raw['seconds']=time.perf_counter()-started;timings.append(raw['seconds'])
        write(name+'-'+category+'-raw.json',raw)
    prediction={**base,'boxes':boxes,'wall_mask':[[1 if mask.getpixel((x,y)) else 0 for x in range(w)] for y in range(h)]}
    predictions.append(prediction)
    mask.save(OUT/(name+'-wall-predicted.png'))
    write(name+'-boxes.json',{'image_id':name,'source_sha256':case['source_sha256'],'boxes':boxes,'data_nature':'AI_INFERRED_NOT_ENGINEERING_FACT'})
    print('Completed '+name,flush=True)

summaries={}
for group in ('rendered_clean','rendered_degraded','negative'):
    ids={c['image_id'] for c in manifest['cases'] if c['group']==group}
    summaries[group]=evaluate([r for r in references if r['image_id'] in ids],[p for p in predictions if p['image_id'] in ids],threshold=manifest['iou_threshold'])
clean=summaries['rendered_clean'];degraded=summaries['rendered_degraded'];negative=summaries['negative'];gate=manifest['screen_gate']
checks={}
for category in ('door','window'):
    for metric in ('precision','recall'):
        value=clean['instances'][category][metric];key=f'clean_{category}_{metric}_min'
        checks[key]=value is not None and value>=gate[key]
    value=degraded['instances'][category]['f1'];checks['degraded_'+category+'_f1']=value is not None and value>=gate['degraded_each_class_f1_min']
for scope,metric,key in ((clean,'micro_iou','clean_wall_micro_iou_min'),(clean,'macro_iou','clean_wall_macro_iou_min'),(degraded,'micro_iou','degraded_wall_micro_iou_min')):
    value=scope['wall'][metric];checks[key]=value is not None and value>=gate[key]
checks['negative_openings']=sum(x['fp'] for x in negative['instances'].values())<=gate['negative_opening_predictions_max']
negative_cases=[c for c in manifest['cases'] if c['group']=='negative']
checks['negative_walls']=all(row['wall']['fp_pixels']/(next(c for c in negative_cases if c['image_id']==row['image_id'])['width']*next(c for c in negative_cases if c['image_id']==row['image_id'])['height'])<=gate['negative_wall_pixels_fraction_max'] for row in negative['cases'])
checks['no_inference_errors']=len(errors)<=gate['inference_failures_max']
result={'model':manifest['model_id'],'manifest_sha256':sha(manifest_path),'summaries':summaries,'checks':checks,'screen_passed':all(checks.values()),
        'errors':errors,'inference_calls':len(timings),'seconds_total':sum(timings),'training':False,'application_integrated':False,
        'score_increment':0,'limitations':manifest['gate_meaning']}
write('result.json',result)
print(json.dumps({'screen_passed':result['screen_passed'],'checks':checks,'errors':len(errors),'inference_calls':len(timings)}),flush=True)
