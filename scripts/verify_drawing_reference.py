"""Actual API OCR vs source-authored synthetic labels and pre-transcribed public subset."""
import hashlib
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from fastapi.testclient import TestClient
from backend.api import create_app


def normalized(text):return re.sub(r'[^a-z0-9]', '', text.lower())


def main():
    public,output=map(Path,sys.argv[1:3]);output.mkdir(parents=True,exist_ok=False)
    golden=ROOT/'fixtures/drawing_gold';truth=json.loads((golden/'truth.json').read_text(encoding='utf-8'))
    public_truth=json.loads((golden/'public-kinnear-truth.json').read_text(encoding='utf-8'))
    assert hashlib.sha256(public.read_bytes()).hexdigest()==public_truth['sha256']
    results=[]
    with TestClient(create_app(output/'runtime',start_worker=False)) as client:
        auth=client.post('/api/auth/register',json={'username':'drawing_reference','display_name':'Isolated OCR verification','password':'Reference-local-ocr-2026!'}).json()
        client.headers['X-CSRF-Token']=auth['csrf_token']
        project=client.post('/api/projects',json={'name':'Synthetic and public OCR reference','data_nature':'engineering_reference',
                     'building':{'use':'reference','location':'Not a field project','region':'reference','area_m2':1}}).json()
        base='/api/projects/'+project['project_id']
        cases=[(golden/c['file'],c) for c in truth['cases']]+[(public,{'file':'kinnear.png','sha256':public_truth['sha256']})]
        for path,case in cases:
            data=path.read_bytes();assert hashlib.sha256(data).hexdigest()==case['sha256']
            fid=client.post(base+'/files',files={'file':(case['file'],data)}).json()['file_id']
            start=time.perf_counter();response=client.post(base+'/drawings',json={'file_id':fid});elapsed=time.perf_counter()-start
            name=Path(case['file']).stem
            (output/(name+'-api.json')).write_text(json.dumps({'status':response.status_code,'record':response.json()},ensure_ascii=False,indent=2),encoding='utf-8')
            assert response.status_code==201,response.text
            record=response.json();candidates=record['result']['candidates'];actual=[c['text'] for c in candidates]
            assert record['reviews']=={} and all(c['source_kind']=='AI_INFERRED' and c['review_required'] for c in candidates)
            if path==public:
                checks=[]
                for label in public_truth['labels']:
                    left,top,right,bottom=label['region']
                    selected=[c for c in candidates if left<=sum(p[0] for p in c['polygon_px'])/4<=right and top<=sum(p[1] for p in c['polygon_px'])/4<=bottom]
                    checks.append({'expected':label,'candidates':selected,'match':any(normalized(c['text'])==normalized(label['text']) for c in selected)})
                row={'case':name,'selected_label_checks':checks,'matched':sum(c['match'] for c in checks),'expected_count':len(checks),'total_candidates':len(candidates)}
            else:
                wanted=Counter(case['expected_labels']);got=Counter(actual);matched=sum((wanted&got).values())
                row={'case':name,'matched':matched,'expected_count':sum(wanted.values()),'actual':actual,
                     'scores':[c['recognition_score'] for c in candidates],'unexpected':list((got-wanted).elements()),
                     'missing_labels_invented':[s for s in case['missing_labels'] if s in actual]}
            row['seconds']=elapsed;results.append(row)
            print(json.dumps({k:v for k,v in row.items() if k not in {'selected_label_checks','actual','scores'}},ensure_ascii=False),flush=True)
    (output/'summary.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    # Functional gate is explicit. Degraded/public recognition failures remain measured failures, not silently skipped.
    clean=next(r for r in results if r['case']=='clean');assert clean['matched']==clean['expected_count']==5
    assert not next(r for r in results if r['case']=='missing_dimension')['missing_labels_invented']
    assert next(r for r in results if r['case']=='blank')['actual']==[]


if __name__=='__main__':main()
