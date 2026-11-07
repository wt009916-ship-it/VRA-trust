import hashlib,json,secrets,sys,tempfile,time
from decimal import Decimal
from pathlib import Path
root,source,gold_path,out=map(Path,sys.argv[1:]);sys.path.insert(0,str(root));sys.path.insert(0,str(root/'tests'))
from fastapi.testclient import TestClient
from backend.api import create_app
from test_api import create_project
from test_cad import upload
raw=source.read_bytes();gold=json.loads(gold_path.read_text(encoding='utf-8'))
assert hashlib.sha256(raw).hexdigest()==gold['source_sha256']
out.mkdir(exist_ok=True,parents=True)
app=create_app(Path(tempfile.mkdtemp(prefix='vra-material-api-')),start_worker=False)
start=time.monotonic()
with TestClient(app) as client:
    session=client.post('/api/auth/register',json={'username':'material_reference_test','display_name':'Isolated source validation','password':secrets.token_urlsafe(32)}).json()
    client.headers['X-CSRF-Token']=session['csrf_token']
    pid=create_project(client)['project_id'];fid=upload(client,pid,'Duplex_A_20110907.ifc',raw)
    response=client.post(f'/api/projects/{pid}/cad-inspections',json={'file_id':fid})
    if response.status_code!=201:raise RuntimeError(str(response.status_code)+': '+response.text[:300])
    actual=response.json()
    (out/'public-api.json').write_text(json.dumps(actual,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    products={r['id']:r for r in actual['result']['objects']}
    checks=[]
    for expected in gold['relations']:
        for owner in expected['owner_ids']:
            item=products[owner]['material_assignment']
            rows=[r for r in item['associations'] if r['relation_id']==expected['relation_id']]
            assert len(rows)==1
            r=rows[0];m=r['material'];assert m['id']==expected['material_id']
            assert r['scope']=='instance' and r['selection']=='effective_declaration'
            if expected['layers']:
                assert m['layer_set']['id']==expected['layer_set_id']
                assert (m['direction'],m['sense'])==(expected['direction'],expected['sense'])
                assert abs(Decimal(str(m['offset_raw']))-Decimal(expected['offset']))<Decimal('1e-14')
                layers=m['layer_set']['layers'];assert len(layers)==len(expected['layers'])
                for layer,want in zip(layers,expected['layers']):
                    assert layer['id']==want['layer_id'] and layer['material']['id']==want['material_id']
                    assert layer['material']['name']==want['name']
                    assert abs(Decimal(str(layer['thickness']['value_m']))-Decimal(want['thickness_m']))<Decimal('1e-14')
            else:assert m['name']==expected['name']
            assert item['quantity_status']=='not_measured'
            checks.append({'relation_id':expected['relation_id'],'owner_id':owner,'matched':True})
    assert actual['source']['hash']==gold['source_sha256']
    public=client.get(f'/api/projects/{pid}/files/{fid}');assert public.content==raw
    receipt={'source_sha256':gold['source_sha256'],'seconds':time.monotonic()-start,'api_status':response.status_code,
      'products':len(products),'relation_owner_pairs':len(checks),'checks':checks,'original_download_identical':True,
      'gold_sha256':hashlib.sha256(gold_path.read_bytes()).hexdigest(),'source_kind':'public_reference','quantity_validation_passed':False}
    (out/'result.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in receipt.items() if k!='checks'}))
