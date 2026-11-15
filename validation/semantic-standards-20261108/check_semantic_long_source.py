from pathlib import Path
import hashlib,json,os,sys,time
root=Path('C:/Users/18483/AppData/Local/Temp/vra-semantic-reference-20261108')
repo=Path('C:/Users/18483/AppData/Local/Temp/vra-semantic-standards-20261108')
sys.path[:0]=[str(root/'deps'),str(repo)];os.environ['VRA_SEMANTIC_MODEL_DIR']=str(root/'model')
from backend import semantic_runtime
source='以下段落是合成软件测试数据，不是建筑规范。'+'建筑应满足节能设计要求，冬季利用太阳辐射，夏季注意通风。'*200
needle='管线穿过隔声墙时必须对孔洞采取密封隔声措施，避免声音经孔洞传播。'
text=source+needle
assert len(source)>5000 and len(text)<=8000
body={'query':'管线穿过隔声墙如何防止孔洞传声？','documents':[{'key':'late_source','text':text},{'key':'distractor','text':'本合成条目介绍建筑节能设计的总体原则和冬季保温。'}]}
frozen=root/'long-source-input.json';assert not frozen.exists();frozen.write_text(json.dumps(body,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
started=time.monotonic();result=semantic_runtime.rank(**body)
late=next(r for r in result['rankings'] if r['key']=='late_source')
checks={'all_documents':result['documents']==2,'multiple_chunks':result['chunks']>2,'tail_covered':late['span'][1]==len(text),
        'tail_ranked_first':result['rankings'][0]['key']=='late_source','no_truncation':result['truncated'] is False,
        'network_isolated':result['resource_limits']['execution_receipt']['filesystem_network_sandbox'] is True}
receipt={'input_sha256':hashlib.sha256(frozen.read_bytes()).hexdigest(),'text_chars':len(text),'answer_begins':len(source),
         'checks':checks,'seconds':time.monotonic()-started,'result':result}
(root/'long-source-result.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:receipt[k] for k in ['text_chars','answer_begins','checks','seconds']}))
assert all(checks.values()),checks
