from pathlib import Path
import sys,json,hashlib,secrets,time,uuid
R=Path('C:/Users/18483/AppData/Local/Temp/vra-drawing-components-20261108')
S=Path('C:/Users/18483/AppData/Local/Temp/vra-official-standards-20261108')
O=Path('C:/Users/18483/AppData/Local/Temp/vra-standard-ocr-20261108');O.mkdir(exist_ok=True)
sys.path[:0]=[str(R),str(R/'tests')]
from backend.api import create_app
from fastapi.testclient import TestClient
from backend.private_storage import private_mkdir
from test_api import create_project
from test_standards import body
gold=[{'code':'GB55015-2021','clause':'1.0.2','page':5,'printed_page':'1',
       'text':'新建、扩建和改建建筑以及既有建筑节能改造工程的建筑节能与可再生能源建筑应用系统的设计、施工、验收及运行管理必须执行本规范。'},
      {'code':'GB55016-2021','clause':'1.1.3','page':5,'printed_page':'1',
       'text':'建筑环境应满足人体健康对声光热环境和空气质量的基本要求。'}]
gold_path=O/'frozen-visual-gold.json'
if not gold_path.exists():gold_path.write_text(json.dumps({'basis':'Independently transcribed from original rendered page before running OCR; dates historical only','targets':gold},ensure_ascii=False,indent=2),encoding='utf-8')
assert json.loads(gold_path.read_text(encoding='utf-8'))['targets']==gold
if '--freeze-only' in sys.argv:print('Frozen original-page visual targets.');raise SystemExit
source_info={x['code']:x for x in json.loads((S/'intake.json').read_text(encoding='utf-8'))}
runtime=private_mkdir(O/('private-'+uuid.uuid4().hex));app=create_app(runtime,start_worker=False)
evidence={'gold_sha256':hashlib.sha256(gold_path.read_bytes()).hexdigest(),'targets':[]}
with TestClient(app) as c:
 auth=c.post('/api/auth/register',json={'username':'normocr_reference','display_name':'Isolated reference acceptance','password':secrets.token_urlsafe(32)});assert auth.status_code==200
 c.headers['X-CSRF-Token']=auth.json()['csrf_token'];pid=create_project(c)['project_id'];base='/api/projects/'+pid
 for g in gold:
  raw=(S/(g['code']+'.pdf')).read_bytes();assert hashlib.sha256(raw).hexdigest()==source_info[g['code']]['sha256']
  fid=c.post(base+'/files',files={'file':(g['code']+'.pdf',raw)}).json()['file_id']
  start=time.monotonic();response=c.post(base+'/standard-ocr',json={'file_id':fid,'page':5})
  (O/(g['code']+'-actual-response.json')).write_text(json.dumps(response.json(),ensure_ascii=False,indent=2),encoding='utf-8')
  assert response.status_code==201,response.text
  r=response.json();candidates=r['result']['candidates']
  # Select by original-page pixel region established after visually comparing
  # saved preview, not by silently substituting OCR text with the golden answer.
  item={'code':g['code'],'seconds':time.monotonic()-start,'source_hash':r['source']['hash'],'normocr_id':r['normocr_id'],
        'candidate_count':len(candidates),'raw_lines':[{'id':x['candidate_id'],'text':x['text'],'score':x['recognition_score'],'polygon':x['polygon_px']} for x in candidates]}
  evidence['targets'].append(item)
  for name in ['preview.png','selected.pdf']:
   download=c.get(base+'/standard-ocr/'+r['normocr_id']+'/'+name);assert download.status_code==200
   (O/(g['code']+'-'+name)).write_bytes(download.content)
  assert hashlib.sha256((S/(g['code']+'.pdf')).read_bytes()).hexdigest()==source_info[g['code']]['sha256']
  print(json.dumps({'code':g['code'],'candidates':item['candidate_count'],'seconds':round(item['seconds'],2),'lines':[(x['candidate_id'],x['text']) for x in candidates]},ensure_ascii=False),flush=True)
 evidence['runtime']=str(runtime);evidence['project_id']=pid
 (O/'official-ocr-probe.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
print('Original files unchanged; OCR output retained without automatic correction or confirmation.')
