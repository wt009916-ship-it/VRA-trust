"""Real authenticated API, isolated OCR and independently frozen geometry/label checks."""
import hashlib,io,json,math,re,secrets,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from fastapi.testclient import TestClient
from backend.api import create_app
from PIL import Image


def normalize(text):return re.sub('[^a-z0-9]','',text.lower())


def main():
    gold,public,output=map(Path,sys.argv[1:4]);output.mkdir(parents=True,exist_ok=False)
    truth=json.loads((gold/'truth.json').read_text(encoding='utf-8'));results=[]
    cases=[(gold/c['file'],c) for c in truth['cases']]
    cases += [(public,{**truth['public'],'name':'public_original','processing':{'deskew_mode':'auto','angle_degrees':0.,'median_filter':False}}),
              (public,{**truth['public'],'name':'public_manual4','processing':{'deskew_mode':'manual','angle_degrees':4.,'median_filter':False}})]
    def save(name,obj):
        with (output/name).open('x',encoding='utf-8') as f:json.dump(obj,f,ensure_ascii=False,indent=2)
    with TestClient(create_app(output/'runtime',start_worker=False)) as client:
        login=client.post('/api/auth/register',json={'username':'drawing_geometry_reference','display_name':'Isolated drawing geometry','password':secrets.token_urlsafe(32)})
        assert login.status_code==200,'Isolated registration rejected: '+str(login.status_code)
        auth=login.json()
        client.headers['X-CSRF-Token']=auth['csrf_token']
        response=client.post('/api/projects',json={'name':'Synthetic and public image geometry; not a field project','data_nature':'engineering_reference',
                       'building':{'use':'reference','location':'No field project','region':'reference','area_m2':1}})
        assert response.status_code==201,response.text
        pid=response.json()['project_id'];base='/api/projects/'+pid
        for path,case in cases:
            name=case.get('name',path.stem);raw=path.read_bytes();assert hashlib.sha256(raw).hexdigest()==case['sha256']
            uploaded=client.post(base+'/files',files={'file':(path.name,raw)});assert uploaded.status_code==201,uploaded.text
            fid=uploaded.json()['file_id']
            processing=case.get('processing',{'deskew_mode':'auto','angle_degrees':0.,'median_filter':case.get('median_filter',False)})
            started=time.perf_counter();response=client.post(base+'/drawings',json={'file_id':fid,'processing':processing});elapsed=time.perf_counter()-started
            save(name+'-api.json',{'status_code':response.status_code,'record':response.json(),'seconds':elapsed})
            row={'case':name,'api_status':response.status_code,'seconds':elapsed,'checks':{}}
            results.append(row)
            if response.status_code!=201:continue
            record=response.json();result=record['result'];p=result['processing'];t=p['transform'];did=record['drawing_id']
            row['drawing_id']=did;row['source_hash']=case['sha256'];row['processing']=p
            row['checks']['isolated_native']=result['resource_limits']['enforced'] is True
            original=client.get(base+'/files/'+fid);row['checks']['original_unchanged']=hashlib.sha256(original.content).hexdigest()==case['sha256']
            for artifact in ['source-preview.png']+(['filter-difference.png'] if p['filter_difference'] else []):
                returned=client.get(base+'/drawings/'+did+'/derivatives/'+artifact)
                expected=p['source_preview_sha256'] if artifact=='source-preview.png' else p['filter_difference']['mask_sha256']
                row['checks'][artifact+'_digest']=returned.status_code==200 and hashlib.sha256(returned.content).hexdigest()==expected
            # Matrix roundtrip is computed here explicitly, not through the application point helper.
            errors=[]
            for xy in [(0,0),tuple(t['source_size']),(t['source_size'][0]/2,t['source_size'][1]/2),(5,5)]:
                a=t['source_to_preview'];b=t['preview_to_source'];x=a[0]*xy[0]+a[1]*xy[1]+a[2];y=a[3]*xy[0]+a[4]*xy[1]+a[5]
                errors.append(math.hypot(b[0]*x+b[1]*y+b[2]-xy[0],b[3]*x+b[4]*y+b[5]-xy[1]))
            row['max_roundtrip_px']=max(errors);row['checks']['roundtrip']=max(errors)<=truth['roundtrip_tolerance_px']
            if case.get('expected_correction_degrees') is not None:
                row['checks']['independent_angle']=abs(t['angle_degrees_clockwise']-case['expected_correction_degrees'])<=truth['angle_tolerance_degrees']
            if case.get('auto_should_decline'):row['checks']['ambiguity_declined']=p['state']=='auto_not_applied'
            if case.get('expected_removed_dark_pixels') is not None:
                row['checks']['filter_damage_disclosed']=p['filter_difference']['dark_pixels_removed']==case['expected_removed_dark_pixels']
            if case.get('expected_white_source_point'):
                x,y=case['expected_white_source_point'];a=t['source_to_preview'];px,py=round(a[0]*x+a[1]*y+a[2]),round(a[3]*x+a[4]*y+a[5])
                preview=client.get(base+'/drawings/'+did+'/preview.png');image=Image.open(io.BytesIO(preview.content)).convert('RGB')
                row['checks']['missing_wall_not_filled']=all(min(image.getpixel((px+dx,py+dy)))>245 for dx in (-2,0,2) for dy in (-2,0,2))
            texts=[c['text'] for c in result['candidates']];row['ocr_texts']=texts
            row['checks']['missing_label_not_invented']=not any(normalize(s) in [normalize(text) for text in texts] for s in case.get('missing_labels',[]))
            if 'labels' in case:
                checks=[]
                for label in case['labels']:
                    l,top,r,bottom=label['region']
                    selected=[c for c in result['candidates'] if l<=sum(p[0] for p in c['polygon_source_px'])/4<=r and top<=sum(p[1] for p in c['polygon_source_px'])/4<=bottom]
                    selected.sort(key=lambda c:(sum(p[1] for p in c['polygon_source_px'])/4,sum(p[0] for p in c['polygon_source_px'])/4))
                    texts_in_region=[c['text'] for c in selected]
                    checks.append({'expected':label,'actual':texts_in_region,'match':normalize(label['text']) in [normalize(text) for text in texts_in_region]+[normalize(' '.join(texts_in_region))]})
                row['selected_label_checks']=checks;row['selected_labels_matched']=sum(c['match'] for c in checks)
                row['selected_labels_total']=len(checks)
            row['functional_pass']=all(row['checks'].values())
            print(json.dumps({'case':name,'pass':row['functional_pass'],'checks':row['checks'],'selected_labels':row.get('selected_labels_matched'),'seconds':round(elapsed,3)}),flush=True)
        summary={'truth_sha256':hashlib.sha256((gold/'truth.json').read_bytes()).hexdigest(),'source_versions':{n:hashlib.sha256((ROOT/'backend'/n).read_bytes()).hexdigest() for n in ['drawings.py','drawing_processing.py','drawing_scale.py','drawing_worker.py','parser_runtime.py']},
                 'cases':results,'scope':'Bounded raster/coordinate pipeline. Public label subset accuracy separate; no public engineering scale or original skew truth.',
                 'functional_pass':all(r.get('functional_pass',False) for r in results)}
        save('summary.json',summary)
    if not summary['functional_pass']:raise SystemExit(1)


if __name__=='__main__':main()
