import argparse
import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageEnhance
from shapely.geometry import Polygon

parser=argparse.ArgumentParser(description='Fixed-old versus enhanced analytic drawing controls; no field accuracy claim')
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--public-page',type=Path,required=True,help='Locally supplied authorized public construction preview image')
args=parser.parse_args()
root=args.output.resolve();root.mkdir(parents=True,exist_ok=False)
repo=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(repo))
from backend import core, floorplan
from backend.model_schema import ImportOptions

oldpath=root/'floorplan-before-bac83b7.py'
if not oldpath.exists():
    oldpath.write_bytes(subprocess.check_output(['git','show','bac83b7:backend/floorplan.py'],cwd=repo))
spec=importlib.util.spec_from_file_location('backend.floorplan_baseline',oldpath)
old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
records=[]
base=Image.new('RGB',(620,360),'white');draw=ImageDraw.Draw(base)
draw.rectangle((40,40,580,320),outline='#333333',width=12);draw.rectangle((300,40,312,320),fill='#333333')
known=[np.array(p,dtype=float) for p in [[(52,52),(299,52),(299,307),(52,307)],[(313,52),(568,52),(568,307),(313,307)]]]
for i,(angle,contrast,broken) in enumerate([(0,1.,False),(5,1.,False),(-7,1.,False),(10,1.,False),(0,.2,False),(5,.2,False),(-7,.2,False),(10,.2,False),(0,.2,True),(5,.2,True),(-7,1.,True),(10,1.,True)]):
    im=base.copy()
    if broken:ImageDraw.Draw(im).rectangle((296,150,316,160),fill='white')
    matrix=cv2.getRotationMatrix2D((310,180),angle,1)
    rgb=cv2.warpAffine(np.asarray(im),matrix,(620,360),borderValue=(255,255,255))
    im=ImageEnhance.Contrast(Image.fromarray(rgb)).enhance(contrast)
    path=root/f'control-{i:02}.png';im.save(path)
    truth=[Polygon(np.column_stack((p,np.ones(len(p))))@matrix.T) for p in known]
    result={'id':f'control-{i:02}','nature':'authored analytic image control, not a real building','angle':angle,'contrast':contrast,'small_break':broken,'sha256':core.sha(path)}
    for label,recognize,mode in [('baseline',old.recognize,'local_raster'),('enhanced',floorplan.recognize,'damaged_raster')]:
        options=ImportOptions(file_id='control',mode=mode,scale_to_m=.02,closure_m=.3,scale_basis='Analytic author control: 50 pixels per metre',ocr_labels=False)
        started=time.perf_counter()
        try:
            # The frozen baseline always runs OCR; disable only document text for equal geometry comparison.
            if label=='baseline':
                from unittest.mock import patch
                with patch('backend.document_worker.read',return_value={'document_pages':[{'lines':[]}],'ocr':{'enabled':False}}):
                    data=recognize(path,options)
            else:data=recognize(path,options)
            predicted=[Polygon(r['drawing']['polygon_px']) for r in data['rooms']]
            candidates=sorted([(a.intersection(b).area/a.union(b).area,ai,bi) for ai,a in enumerate(truth) for bi,b in enumerate(predicted)],reverse=True)
            matched_truth,matched_pred,ious=set(),set(),[]
            for score,ai,bi in candidates:
                if ai not in matched_truth and bi not in matched_pred:
                    matched_truth.add(ai);matched_pred.add(bi);ious.append(score)
            result[label]={'rooms':len(predicted),'matched_at_iou_0_9':sum(v>=.9 for v in ious),'mean_best_matched_iou':sum(ious)/len(truth),'seconds':time.perf_counter()-started}
        except Exception as exc:
            result[label]={'rooms':0,'matched_at_iou_0_9':0,'mean_best_matched_iou':0.,'seconds':time.perf_counter()-started,'error':str(exc)}
    records.append(result)

public=args.public_page.resolve()
cache_options=ImportOptions(file_id='actual_public_source',mode='damaged_raster',scale_to_m=8.8/510.,crop_px=(820,280,1365,780),closure_m=1.3,scale_basis='Public construction page 6, 8.80 m exterior dimension over 510 preview pixels',ocr_labels=True)
calls=[]
for _ in range(2):
    started=time.perf_counter();data=floorplan.extract(public,cache_options)
    calls.append({'seconds':time.perf_counter()-started,**data['metadata']['recognition_cache'],'rooms':len(data['rooms'])})
core.write_json(root/'public-enhanced-recognition.json',data)
report={'baseline_commit':'bac83b7652247ed84463f24f9557a65f35b56fe5','baseline_sha256':core.sha(oldpath),
    'enhanced_source_sha256':core.sha(Path(floorplan.__file__)),'controls':records,
    'public_source_sha256':core.sha(public),'public_cold_warm':calls,
    'limits':['Author control perturbations, not an independent commercial test set','No held-out old-building accuracy claim','Identical geometry repair budget, OCR disabled equally for control geometry comparison','Cache timing is same-source/options/rules/OCR repeat recognition; not initial recognition or competitor speed','Public geometry count is not completeness or semantic recognition accuracy']}
core.write_json(root/'drawing-benchmark.json',report)
print(json.dumps({'controls':len(records),'baseline_matches':sum(r['baseline']['matched_at_iou_0_9'] for r in records),'enhanced_matches':sum(r['enhanced']['matched_at_iou_0_9'] for r in records),'public_calls':calls},ensure_ascii=False),flush=True)
