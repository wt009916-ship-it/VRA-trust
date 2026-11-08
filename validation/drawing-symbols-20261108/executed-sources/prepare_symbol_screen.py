from pathlib import Path
from hashlib import sha256
from urllib.request import Request,urlopen
import json,zipfile,io,shutil,subprocess,sys

HELPERS=Path(__file__).parent
OLD=Path('C:/Users/18483/AppData/Local/Temp/vra-floorplan-feasibility-20261108')
ROOT=Path('C:/Users/18483/AppData/Local/Temp/vra-symbol-detector-20261108')
ROOT.mkdir(exist_ok=False)
source=HELPERS/'drawing-components/symbol_detector.py'
shutil.copyfile(source,ROOT/'symbol_detector-frozen.py')
old_selection=json.loads((OLD/'selection-frozen.json').read_text())
splits=json.loads((OLD/'resplan-split.json').read_text())
ids=sorted(set(splits['test'])-set(old_selection['ids']),key=lambda x:sha256(('VRA-D08-symbol-v1:'+str(x)).encode()).hexdigest())[:8]
selection={'source_commit':old_selection['source_commit'],'split':'test','ids':ids,'excluded_prior_ids':old_selection['ids'],
           'selection':'first 8 after SHA256(VRA-D08-symbol-v1:<id>) ordering, prior 8 excluded, before decoding or recognition',
           'nature':'geometry-rendered references, not surveyed building truth; no training'}
(ROOT/'selection-frozen.json').write_text(json.dumps(selection,indent=2),encoding='utf-8')
# Reuse only previously inspected local decoding definitions, never upstream code.
code=(HELPERS/'decode_resplan_reference.py').read_text(encoding='utf-8').split('\narchive=ROOT')[0]
scope={};exec(compile(code,'previously-reviewed-local-decoder','exec'),scope)
with zipfile.ZipFile(OLD/'ResPlan.zip') as archive:
    raw=archive.read('ResPlan.pkl')
assert sha256(raw).hexdigest()==json.loads((OLD/'resplan-download.json').read_text())['pickle_sha256']
data=scope['GeometryOnlyUnpickler'](io.BytesIO(raw)).load();lookup={row['id']:row for row in data}
(ROOT/'selected-geometries.json').write_text(json.dumps({'selection':selection,'plans':[lookup[i] for i in ids]},indent=2,allow_nan=False),encoding='utf-8')
# Preserve the independent renderer and its explicit synthetic symbol convention.
render=(HELPERS/'render_floorplan_reference.py').read_text(encoding='utf-8').split('\nmanifest={')[0]
render=render.replace(str(OLD).replace('\\','/'),str(ROOT).replace('\\','/'))
render+='''\nmanifest={'cases':cases,'selection':data['selection'],'iou_threshold':0.5,
 'gate':{'clean_door_precision_min':0.85,'clean_door_recall_min':0.85,'clean_window_precision_min':0.85,'clean_window_recall_min':0.85,
         'clean_wall_micro_iou_min':0.8,'clean_wall_macro_iou_min':0.75,'degraded_each_class_f1_min':0.7,'degraded_wall_micro_iou_min':0.65,
         'negative_opening_predictions_max':0,'negative_wall_pixels_fraction_max':0.01,'inference_failures_max':0},
 'method_sha256':sha(ROOT/'symbol_detector-frozen.py'),'renderer_sha256':sha(Path(__file__)),
 'evaluator_sha256':sha(Path(__file__).parent/'drawing-components/evaluate.py'),
 'training':False,'application_integrated':False,'frozen_before_recognition':True}
(OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'ids':data['selection']['ids'],'cases':len(cases),'manifest_sha256':sha(OUT/'manifest.json')}),flush=True)
'''
render_path=HELPERS/'render_symbol_reference.py';assert not render_path.exists();render_path.write_text(render,encoding='utf-8')
subprocess.run([sys.executable,'-B','-X','utf8',str(render_path)],check=True)
shutil.copyfile(OLD/'public-floor-plan-1.jpg',ROOT/'public-plan-prior.jpg')
url='https://upload.wikimedia.org/wikipedia/commons/d/d7/Floor_plan1.jpg'
with urlopen(Request(url,headers={'User-Agent':'VRA-Trust-public-reference-evaluation/1.0'}),timeout=60) as response:payload=response.read()
assert len(payload)==26670
(ROOT/'public-plan-new.jpg').write_bytes(payload)
(ROOT/'public-inputs.json').write_text(json.dumps({'author':'Ashlynn Schindler','license':'public-domain dedication per Commons file pages',
    'prior':{'file':'public-plan-prior.jpg','source':'https://commons.wikimedia.org/wiki/File:Floor_plan_1.jpg','sha256':sha256((ROOT/'public-plan-prior.jpg').read_bytes()).hexdigest(),'nature':'previously viewed development reference, not holdout'},
    'new':{'file':'public-plan-new.jpg','source':'https://commons.wikimedia.org/wiki/File:Floor_plan1.jpg','sha256':sha256(payload).hexdigest(),'nature':'new public original image, labels to be frozen before any recognition'},
    'limitations':'Original public raster illustrations, not verified as-built building measurements; common author, independence limited'},indent=2),encoding='utf-8')
print('New references prepared, no recognizer run',flush=True)
