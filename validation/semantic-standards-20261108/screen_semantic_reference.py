from pathlib import Path
import hashlib,json,os,sys,time
root=Path('C:/Users/18483/AppData/Local/Temp/vra-semantic-reference-20261108')
repo=Path('C:/Users/18483/AppData/Local/Temp/vra-semantic-standards-20261108')
os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TOKENIZERS_PARALLELISM='false',PYTHONDONTWRITEBYTECODE='1')
sys.path[:0]=[str(root/'deps'),str(repo)]
import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer
from backend.standards import tokens
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(root/'frozen-retrieval.json')=='d997763cd2426a801b7cdbdf1cc6d23a2bd1e85a7e711030a8df78b2239cf7b5'
frozen=json.loads((root/'frozen-retrieval.json').read_text(encoding='utf-8'))
manifest=json.loads((root/'model-manifest.json').read_text())
assert len(manifest['files'])==5
for row in manifest['files']:assert sha(root/'model'/row['path'])==row['sha256']
output=root/'ranking-screen.json';assert not output.exists()
tokenizer=Tokenizer.from_file(str(root/'model/tokenizer.json'))
tokenizer.no_truncation();tokenizer.enable_padding(pad_id=0,pad_token='[PAD]')
options=ort.SessionOptions();options.intra_op_num_threads=2;options.inter_op_num_threads=1
started=time.monotonic();session=ort.InferenceSession(str(root/'model/onnx/model.onnx'),sess_options=options,providers=['CPUExecutionProvider'])
input_names={i.name for i in session.get_inputs()}
assert input_names=={'input_ids','attention_mask','token_type_ids'},input_names
def embed(texts):
    vectors=[];lengths=[]
    for start in range(0,len(texts),8):
        encoded=tokenizer.encode_batch(texts[start:start+8])
        lengths.extend(sum(e.attention_mask) for e in encoded)
        assert all(len(e.ids)<=512 for e in encoded),'Never silently truncate source evidence'
        batch={'input_ids':np.array([e.ids for e in encoded],dtype=np.int64),
               'attention_mask':np.array([e.attention_mask for e in encoded],dtype=np.int64),
               'token_type_ids':np.array([e.type_ids for e in encoded],dtype=np.int64)}
        value=session.run(None,batch)[0]
        assert value.shape[0]==len(encoded) and value.shape[2]==512 and np.isfinite(value).all(),value.shape
        cls=value[:,0,:];norm=np.linalg.norm(cls,axis=1,keepdims=True);assert (norm>0).all()
        vectors.append(cls/norm)
    return np.concatenate(vectors),lengths
documents=frozen['corpus'];queries=frozen['queries'];prefix=frozen['method']['query_prefix']
dv,dl=embed([r['text'] for r in documents]);qv,ql=embed([prefix+r['question'] for r in queries])
scores=qv@dv.T;rows=[]
for i,q in enumerate(queries):
    terms=tokens(q['question'])
    baseline=sorted([(len(terms&tokens(d['text']))/max(1,len(terms)),d['key']) for d in documents],key=lambda t:(-t[0],t[1]))
    baseline=[v for v in baseline if v[0]>0]
    dense=sorted([(float(scores[i,j]),d['key']) for j,d in enumerate(documents)],key=lambda t:(-t[0],t[1]))
    def assess(ranked):
        keys=[k for s,k in ranked];relevant=set(q['relevant'])
        return {'top1':bool(keys and keys[0] in relevant),'recall_at_3':bool(relevant & set(keys[:3])),
                'reciprocal_rank':next((1/(index+1) for index,key in enumerate(keys) if key in relevant),0),
                'ranking':[{'key':key,'score':score} for score,key in ranked]}
    rows.append({'id':q['id'],'query':q['question'],'gold':q['relevant'],'lexical':assess(baseline),'semantic':assess(dense)})
summary={arm:{metric:sum(row[arm][metric] for row in rows) for metric in ['top1','recall_at_3','reciprocal_rank']} for arm in ['lexical','semantic']}
regressions=[r['id'] for r in rows if r['lexical']['recall_at_3'] and not r['semantic']['recall_at_3']]
gate=frozen['gates'];checks={'top1':summary['semantic']['top1']>=gate['top1_min'],
 'recall_at_3':summary['semantic']['recall_at_3']>=gate['recall_at_3_min'],
 'net_gain':summary['semantic']['top1']-summary['lexical']['top1']>=gate['top1_net_gain_min'],
 'no_recall_regression':len(regressions)<=gate['baseline_recall_at_3_regressions_max']}
result={'fixture_sha256':sha(root/'frozen-retrieval.json'),'model':manifest,'rows':rows,'summary':summary,'gates':checks,
        'screen_pass':all(checks.values()),'recall_regressions':regressions,'seconds':round(time.monotonic()-started,3),
        'token_lengths':{'documents':dl,'queries':ql},'runtime':{'onnxruntime':ort.__version__,'numpy':np.__version__},
        'scope':'Actual pretrained ONNX inference and production lexical scoring formula on fixed corpus; not yet application/API/UI acceptance or calibrated relevance confidence',
        'source_code_sha256':sha(Path(__file__)),'training':False}
output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:result[k] for k in ['summary','gates','screen_pass','recall_regressions','seconds']},ensure_ascii=False))
