from pathlib import Path
import copy,hashlib,json,os,secrets,sys,time,traceback
root=Path('C:/Users/18483/AppData/Local/Temp/vra-semantic-reference-20261108')
repo=Path('C:/Users/18483/AppData/Local/Temp/vra-semantic-standards-20261108')
out=root/'application-holdout';assert not out.exists();out.mkdir()
sys.path[:0]=[str(root/'deps'),str(repo)]
os.environ.update(VRA_DATA_DIR=str(out/'private'),VRA_SEMANTIC_MODEL_DIR=str(root/'model'),PYTHONDONTWRITEBYTECODE='1')
from backend.api import create_app
from backend.standards import Query
from fastapi.testclient import TestClient
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(name,data):(out/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
assert sha(root/'frozen-holdout.json')=='7461bb07576f63b2cbed4f9f3e36c4b46530a4387ed3d088ac3194d766d63828'
definition=json.loads((root/'frozen-retrieval.json').read_text(encoding='utf-8'))
holdout=json.loads((root/'frozen-holdout.json').read_text(encoding='utf-8'))
source_hashes={p.name:sha(p) for p in sorted((repo/'backend').glob('*.py'))}
receipt={'source_hashes':source_hashes,'fixture_sha256':sha(root/'frozen-retrieval.json'),'holdout_sha256':sha(root/'frozen-holdout.json'),'cases':[],'checks':{},'records':[]}
app=create_app(out/'private',start_worker=False)
try:
 with TestClient(app) as client:
    auth=client.post('/api/auth/register',json={'username':'semantic_holdout','display_name':'Isolated reference','password':secrets.token_urlsafe(32)});assert auth.status_code==200
    client.headers['X-CSRF-Token']=auth.json()['csrf_token']
    project=client.post('/api/projects',json={'name':'Frozen semantic reference','building':{'use':'office','location':'Public reference only','region':'US-CO','area_m2':500}}).json()
    pid=project['project_id'];base='/api/projects/'+pid
    for doc in definition['sources']:
        pdf=Path('C:/Users/18483/AppData/Local/Temp/vra-official-standards-20261108')/(doc['code']+'.pdf');assert sha(pdf)==doc['sha256']
        upload=client.post(base+'/files',files={'file':(pdf.name,pdf.read_bytes())});assert upload.status_code==201
        fid=upload.json()['file_id'];clauses=[d for d in definition['corpus'] if d['code']==doc['code']];ocr={}
        for page in sorted({c['page'] for c in clauses}):
            r=client.post(base+'/standard-ocr',json={'file_id':fid,'page':page});save(doc['code']+'-ocr-'+str(page)+'.json',r.json());assert r.status_code==201,r.text
            ocr[page]=r.json();print(json.dumps({'prepared':doc['code'],'page':page}),flush=True)
        body={'file_id':fid,'standard_code':doc['code'].split('-')[0],'edition':'2021','title':doc['title'],'publisher':'中华人民共和国住房和城乡建设部',
              'source_url':doc['official_announcement'],'permission':'Official publicly accessible reference used locally for software evaluation; not redistributed or trained on.',
              'jurisdiction':'中国，历史参考','scope':'仅核对2021版指定页摘录的检索；非完整规范库，不判定当前项目适用性或2026现行状态。',
              'effective_from':'2022-04-01','retired_on':None,'status_checked_on':'2022-04-01',
              'status_basis':'Historical effective date from official announcement; later validity is not established by this evaluation.','clauses':[]}
        for c in clauses:
            o=ocr[c['page']]
            body['clauses'].append({'clause_id':c['clause_id'],'pdf_page':c['page'],'printed_page':c['printed_page'],
                'text':c['text'],'coverage':c['coverage'],'transcription':'ocr_assisted','topic':'公开摘录',
                'ocr_id':o['normocr_id'],'candidate_ids':[x['candidate_id'] for x in o['result']['candidates']],
                'transcription_basis':'Developer manually compared the original rendered page before retrieval; page candidates retained as broad provenance, text manually corrected. No external engineer certification.'})
        r=client.post(base+'/standards',json=body);save(doc['code']+'-registration.json',r.json());assert r.status_code==201,r.text
        record=r.json();r=client.post(base+'/standards/'+record['standard_id']+'/review',json={'expected_revision':record['revision'],'state':'confirmed','basis':'Original rendered pages visually checked; excerpts and omitted tables explicit. Historical retrieval reference only, not current compliance.'});assert r.status_code==200,r.text
        receipt['records'].append(r.json())
    saved=[]
    for case in holdout['cases']:
        row={'id':case['id'],'query':case['question'],'gold':case['relevant']}
        for method in ['lexical','semantic']:
            start=time.monotonic();r=client.post(base+'/standard-queries',json={'text':case['question'],'as_of':'2022-04-01','retrieval':method,'limit':3});save(case['id']+'-'+method+'.json',r.json())
            assert r.status_code==201,r.text
            obj=r.json();result=obj['result'];saved.append(obj);keys=[c['standard_code']+'-'+c['edition']+':'+c['clause_id'] for c in result['citations']]
            row[method]={'keys':keys,'top1':bool(keys and keys[0] in case['relevant']),'recall_at_3':bool(set(keys)&set(case['relevant'])),'seconds':round(time.monotonic()-start,3)}
            if method=='semantic':
                assert result['status']=='RELEVANCE_REVIEW_REQUIRED' and result['retrieval']['confidence'] is None
                assert result['retrieval']['documents']==32 and result['retrieval']['truncated'] is False
                assert all(c['relevance_verified'] is False and c['confidence'] is None for c in result['citations'])
                current=client.get(base+'/standard-queries/'+obj['normquery_id']);assert current.json()['status']=='current'
        receipt['cases'].append(row);save('results.json',receipt);print(json.dumps(row,ensure_ascii=False),flush=True)
    for index,q in enumerate(holdout['boundary_queries']):
        r=client.post(base+'/standard-queries',json={'text':q,'as_of':'2022-04-01','retrieval':'semantic','limit':3});save('boundary-'+str(index)+'.json',r.json());assert r.status_code==201
        result=r.json()['result'];receipt['checks']['unverified_boundary_'+str(index)]=result['status']=='RELEVANCE_REVIEW_REQUIRED' and result['retrieval']['confidence'] is None
    r=client.post(base+'/standard-queries',json={'text':'GB 99999-2021 9.9.9 请给这条法规','as_of':'2022-04-01','retrieval':'semantic'});save('missing-exact.json',r.json())
    receipt['checks']['no_exact_substitution']=r.status_code==201 and not r.json()['result']['citations']
    r=client.post(base+'/standard-queries',json={'text':'管道隔声','as_of':'2026-11-08','retrieval':'semantic'});save('unverified-current-date.json',r.json())
    receipt['checks']['historical_index_not_current']=r.status_code==201 and not r.json()['result']['citations'] and all(x['reason']=='VALIDITY_RECHECK_REQUIRED' for x in r.json()['result']['excluded'])
    semantic=next(s for s in saved if s['result']['retrieval']['method']=='semantic');lexical=next(s for s in saved if s['result']['retrieval']['method']=='lexical')
    os.environ.pop('VRA_SEMANTIC_MODEL_DIR')
    stale=client.get(base+'/standard-queries/'+semantic['normquery_id']).json();save('model-withdrawal.json',stale)
    receipt['checks']['model_withdraws_semantic_only']=stale['status']=='stale' and stale['result'] is None and client.get(base+'/standard-queries/'+lexical['normquery_id']).json()['status']=='current'
    r=client.post(base+'/standard-queries',json={'text':'保温管道','as_of':'2022-04-01','retrieval':'semantic'});save('missing-runtime.json',r.json())
    receipt['checks']['no_model_fallback']=r.status_code==409
    os.environ['VRA_SEMANTIC_MODEL_DIR']=str(root/'model')
    record=receipt['records'][0];r=client.post(base+'/standards/'+record['standard_id']+'/review',json={'expected_revision':record['revision'],'state':'rejected','basis':'Withdrawal in isolated acceptance; existing results must become unavailable.'});assert r.status_code==200
    stale=client.get(base+'/standard-queries/'+semantic['normquery_id']).json();save('source-withdrawal.json',stale);receipt['checks']['source_withdraws_old_result']=stale['status']=='stale' and stale['result'] is None
    client.headers.pop('X-CSRF-Token');receipt['checks']['csrf']=client.post(base+'/standard-queries',json={'text':'noise','as_of':'2022-04-01'}).status_code==403
    client.cookies.clear();receipt['checks']['anonymous']=client.get(base+'/standard-queries/'+semantic['normquery_id']).status_code==401
    receipt['summary']={m:{k:sum(c[m][k] for c in receipt['cases']) for k in ['top1','recall_at_3']} for m in ['lexical','semantic']}
    regress=[c['id'] for c in receipt['cases'] if c['lexical']['recall_at_3'] and not c['semantic']['recall_at_3']]
    g=holdout['gate'];receipt['ranking_gate']=receipt['summary']['semantic']['top1']>=g['top1_min'] and receipt['summary']['semantic']['recall_at_3']>=g['recall_at_3_min'] and len(regress)<=g['baseline_recall_regressions_max']
    receipt['recall_regressions']=regress;receipt['completed']=True
except Exception:
    receipt['error']=traceback.format_exc();raise
finally:
    receipt['final_source_hashes']={p.name:sha(p) for p in sorted((repo/'backend').glob('*.py'))}
    receipt['source_unchanged']=source_hashes==receipt['final_source_hashes'];save('results.json',receipt)
print(json.dumps({k:receipt[k] for k in ['summary','ranking_gate','checks','source_unchanged']},ensure_ascii=False),flush=True)
