"""Confirm the pre-existing full-void discrepancy through isolated authenticated API."""
import hashlib,json,secrets,sys,tempfile
from pathlib import Path
repo=Path.cwd();out=Path(__file__).resolve().parent
sys.path[:0]=[str(repo),str(repo/'tests')]
from fastapi.testclient import TestClient
from backend.api import create_app
from test_api import create_project
data=Path(tempfile.mkdtemp(prefix='vra-ifc-net-api-'))
rows=[]
with TestClient(create_app(data,start_worker=False)) as client:
    response=client.post('/api/auth/register',json={'username':'ifc_net_probe','display_name':'Isolated IFC probe','password':secrets.token_urlsafe(36)})
    assert response.status_code==200;client.headers['X-CSRF-Token']=response.json()['csrf_token']
    pid=create_project(client)['project_id']
    for name in ['single_through','host_fully_removed']:
        path=out/(name+'.ifc');raw=path.read_bytes();digest=hashlib.sha256(raw).hexdigest()
        response=client.post(f'/api/projects/{pid}/files',files={'file':(path.name,raw,'application/octet-stream')});assert response.status_code==201
        fid=response.json()['file_id']
        response=client.post(f'/api/projects/{pid}/cad-inspections',json={'file_id':fid});assert response.status_code==201,response.text
        record=response.json();objects=record['result']['ifc_geometry']['objects'];wall=next(r for r in objects if r['type']=='IfcWall')
        reloaded=client.get(f"/api/projects/{pid}/cad-inspections/{record['cad_id']}").json()
        original=client.get(f'/api/projects/{pid}/files/{fid}').content
        rows.append({'case':name,'cad_id':record['cad_id'],'source_sha256':digest,'wall':wall,'persisted_result_identical':reloaded['result']==record['result'],
          'source_preserved':hashlib.sha256(original).hexdigest()==digest,'independent_expected_m3':22 if name=='single_through' else 0,
          'unavailable_or_correct':wall['volume_m3'] is None or abs(wall['volume_m3']-(22 if name=='single_through' else 0))<=1e-9})
with (out/'api-probe-windows-v1.json').open('x',encoding='utf-8') as f:json.dump({'source_commit':'bf237af3b8d0ef9f0077b4a0614ffe2f397a83b1','data':str(data),'cases':rows,'credentials_saved':False},f,ensure_ascii=False,indent=2)
print(json.dumps([{'case':r['case'],'volume':r['wall']['volume_m3'],'expected':r['independent_expected_m3'],'unavailable_or_correct':r['unavailable_or_correct']} for r in rows]))
