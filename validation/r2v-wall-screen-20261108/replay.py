"""Verify saved wall masks with PIL histogram arithmetic; does not run a model."""
from pathlib import Path
import hashlib,json,sys,math
from PIL import Image,ImageChops
root=Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
manifest=json.loads((root/'frozen-reference/manifest.json').read_text())
result=json.loads((root/'wall-screen/result.json').read_text())
assert sha(root/'frozen-reference/manifest.json')==result['manifest_sha256']
lookup={r['image_id']:r for r in result['cases']}
rows=[]
for case in manifest['cases']:
 key=case['image_id'];expected=lookup[key]
 pred=root/'wall-screen'/(key+'-wall.png');truth=root/'frozen-reference'/case['wall_mask_file'];source=root/'frozen-reference'/(key+'.png')
 assert sha(source)==case['source_sha256'] and sha(truth)==case['wall_mask_sha256'] and sha(pred)==expected['predicted_mask_sha256']
 with Image.open(pred) as p,Image.open(truth) as t:
  assert p.mode==t.mode=='L' and p.size==t.size
  assert sum(p.histogram()[1:255])==sum(t.histogram()[1:255])==0
  inter=ImageChops.darker(p,t).histogram()[255];union=ImageChops.lighter(p,t).histogram()[255]
  assert inter==expected['intersection'] and union==expected['union']
  assert p.histogram()[255]==expected['predicted_pixels'] and t.histogram()[255]==expected['truth_pixels']
  assert expected['wall_iou']==(inter/union if union else None)
  rows.append(expected)
for group,summary in result['summary'].items():
 records=[r for r in rows if r['group']==group];union=sum(r['union'] for r in records);inter=sum(r['intersection'] for r in records)
 vals=[r['wall_iou'] for r in records if r['wall_iou'] is not None]
 assert len(records)==summary['count'] and union==summary['union'] and inter==summary['intersection']
 assert summary['micro_iou']==(inter/union if union else None)
 assert summary['macro_iou']==(sum(vals)/len(vals) if vals else None)
 assert summary['max_predicted_fraction']==max(r['predicted_fraction'] for r in records)
print(json.dumps({'independent_mask_recount_matches':True,'cases':len(rows),'model_rerun':False,'wall_screen_passed':result['wall_screen_passed']}))
