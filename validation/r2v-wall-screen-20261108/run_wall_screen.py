from pathlib import Path
import os,sys,json,hashlib,time,datetime
os.environ['CUDA_VISIBLE_DEVICES']=''
root=Path(__file__).parent
sys.path.insert(0,str(root/'adapted'))
import numpy as np
import torch
from PIL import Image
from types import SimpleNamespace
from models.model import Model
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
manifest_path=root/'frozen-reference/manifest.json'
assert sha(manifest_path)=='435c52c86c79b4bc253f04e0fe572cb003a0140621469cf9a1a4db41ff5b8400'
manifest=json.loads(manifest_path.read_text())
assert sha(root/'checkpoint.pth')==manifest['checkpoint_sha256']
out=root/'wall-screen';out.mkdir(exist_ok=False)
receipt={'started_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'script_sha256':sha(Path(__file__)),'manifest_sha256':sha(manifest_path),'checkpoint_sha256':manifest['checkpoint_sha256'],'torch':torch.__version__,'training':False,'cases':[],'errors':[]}
(out/'frozen-execution.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
torch.set_num_threads(2);torch.manual_seed(20261108)
state=torch.load(root/'checkpoint.pth',map_location='cpu',weights_only=True)
model=Model(SimpleNamespace(width=256,height=256));model.load_state_dict(state,strict=True);model.eval()
start=time.monotonic()
for case in manifest['cases']:
 key=case['image_id'];source=root/'frozen-reference'/(key+'.png');truth=root/'frozen-reference'/case['wall_mask_file']
 assert sha(source)==case['source_sha256'] and sha(truth)==case['wall_mask_sha256']
 try:
  t=time.monotonic()
  with Image.open(source) as im:
   rgb=np.asarray(im.convert('RGB').resize((256,256),Image.Resampling.BILINEAR))
  bgr=rgb[:,:,::-1].copy().astype(np.float32)/255.0-0.5
  inp=torch.from_numpy(bgr.transpose(2,0,1)[None])
  with torch.inference_mode(): corners,icons,rooms=model(inp)
  assert rooms.shape==(1,256,256,12)
  assert all(torch.isfinite(x).all().item() for x in (corners,icons,rooms))
  logits=rooms[0].numpy();np.savez_compressed(out/(key+'-room-logits.npz'),room_logits=logits)
  native=(logits.argmax(axis=-1)==11).astype(np.uint8)*255
  mask=Image.fromarray(native).resize((case['width'],case['height']),Image.Resampling.NEAREST)
  mask.save(out/(key+'-wall.png'))
  with Image.open(truth) as im: ref=np.asarray(im)!=0
  pred=np.asarray(mask)!=0
  inter=int(np.count_nonzero(ref&pred));union=int(np.count_nonzero(ref|pred));actual=int(np.count_nonzero(pred))
  row={'image_id':key,'group':case['group'],'source_sha256':sha(source),'predicted_mask_sha256':sha(out/(key+'-wall.png')),'raw_logits_sha256':sha(out/(key+'-room-logits.npz')),'intersection':inter,'union':union,'truth_pixels':int(np.count_nonzero(ref)),'predicted_pixels':actual,'wall_iou':inter/union if union else None,'predicted_fraction':actual/ref.size,'seconds':time.monotonic()-t}
  receipt['cases'].append(row)
  print(json.dumps(row),flush=True)
 except Exception as exc:
  receipt['errors'].append({'image_id':key,'error':type(exc).__name__+': '+str(exc)})
  print(json.dumps(receipt['errors'][-1]),flush=True)
summary={}
for group in ('rendered_clean','rendered_degraded','negative'):
 rows=[x for x in receipt['cases'] if x['group']==group];u=sum(x['union'] for x in rows);vals=[x['wall_iou'] for x in rows if x['wall_iou'] is not None]
 summary[group]={'count':len(rows),'intersection':sum(x['intersection'] for x in rows),'union':u,'micro_iou':sum(x['intersection'] for x in rows)/u if u else None,'macro_iou':sum(vals)/len(vals) if vals else None,'max_predicted_fraction':max((x['predicted_fraction'] for x in rows),default=None)}
g=manifest['gate'];clean=summary['rendered_clean'];deg=summary['rendered_degraded'];neg=summary['negative']
gates={'clean_micro':clean['micro_iou'] is not None and clean['micro_iou']>=g['clean_micro_iou_min'],'clean_macro':clean['macro_iou'] is not None and clean['macro_iou']>=g['clean_macro_iou_min'],'degraded_micro':deg['micro_iou'] is not None and deg['micro_iou']>=g['degraded_micro_iou_min'],'negative':neg['count']==3 and neg['max_predicted_fraction']<=g['negative_each_wall_fraction_max'],'no_errors':len(receipt['errors'])==0 and len(receipt['cases'])==len(manifest['cases'])}
receipt.update(summary=summary,gates=gates,wall_screen_passed=all(gates.values()),seconds=time.monotonic()-start,finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),D08_passed=False,scope=manifest['scope'])
(out/'result.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
print(json.dumps({'summary':summary,'gates':gates,'wall_screen_passed':receipt['wall_screen_passed'],'seconds':receipt['seconds']}),flush=True)
