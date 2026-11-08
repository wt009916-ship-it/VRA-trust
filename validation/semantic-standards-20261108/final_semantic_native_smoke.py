from pathlib import Path
import hashlib,json,os,secrets,sys,time
root=Path('C:/Users/18483/AppData/Local/Temp/vra-semantic-reference-20261108')
repo=Path('C:/Users/18483/AppData/Local/Temp/vra-semantic-standards-20261108')
out=root/'final-native-smoke';assert not out.exists();out.mkdir()
sys.path[:0]=[str(root/'deps'),str(repo),str(repo/'tests')]
os.environ.update(VRA_DATA_DIR=str(out/'private'),VRA_SEMANTIC_MODEL_DIR=str(root/'model'))
from backend.api import create_app
from fastapi.testclient import TestClient
from test_standards import setup,save
app=create_app(out/'private',start_worker=False)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
result={'scope':'One final-source real API/native smoke after schema-only and strict response validation edits; not a fresh semantic accuracy benchmark.',
        'source_hashes':{p.name:sha(p) for p in (repo/'backend').glob('*.py')}}
with TestClient(app) as client:
    auth=client.post('/api/auth/register',json={'username':'final_semantic_smoke','display_name':'Isolated validation','password':secrets.token_urlsafe(32)});assert auth.status_code==200
    client.headers['X-CSRF-Token']=auth.json()['csrf_token'];pid,base,b=setup(client);record=save(client,base,b)
    started=time.monotonic();response=client.post(base+'/standard-queries',json={'text':'Which source documentation is required for thermal insulation?','retrieval':'semantic','as_of':'2025-01-01'});assert response.status_code==201,response.text
    item=response.json();result['query']=item;result['seconds']=time.monotonic()-started
    answer=item['result'];result['checks']={'candidate_status':answer['status']=='RELEVANCE_REVIEW_REQUIRED',
       'real_native_worker':answer['retrieval']['resource_limits']['execution_receipt']['filesystem_network_sandbox'] is True,
       'all_sources':answer['retrieval']['documents']==2,'quote_origin':all(c['text'] in {x['text'] for x in b['clauses']} for c in answer['citations']),
       'current_read':client.get(base+'/standard-queries/'+item['normquery_id']).json()['status']=='current'}
    path=app.state.domain.file_record(pid,b['file_id'])[1];original=path.read_bytes();path.write_bytes(b'corrupted isolated test PDF')
    stale=client.get(base+'/standard-queries/'+item['normquery_id']).json();result['source_corruption']=stale
    result['checks']['corruption_withdraws']=stale['status']=='stale' and stale['result'] is None
    path.write_bytes(original)
result['final_source_hashes']={p.name:sha(p) for p in (repo/'backend').glob('*.py')}
result['checks']['source_unchanged']=result['source_hashes']==result['final_source_hashes']
(out/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'checks':result['checks'],'seconds':result['seconds']},ensure_ascii=False))
assert all(result['checks'].values())
