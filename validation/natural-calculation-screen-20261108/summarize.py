"""Audit the completed frozen run without requesting more inference."""
from pathlib import Path
import json,hashlib,statistics,collections
BASE=Path(__file__).resolve().parent
f=json.loads((BASE/'frozen.json').read_text(encoding='utf-8'))
r=json.loads((BASE/'first-run/receipt.json').read_text(encoding='utf-8'))
assert r['completed'] and all(a['server_stopped'] for a in r['arms'])
assert hashlib.sha256((BASE/'frozen.json').read_bytes()).hexdigest()==r['frozen_sha256']
for name,digest in f['source_sha256'].items():assert hashlib.sha256((BASE/name).read_bytes()).hexdigest()==digest
rows=[];all_rows=[]
for arm in f['arms']:
 for seed in arm['seeds']:
  data=[]
  for case in f['cases']:
   path=BASE/'first-run'/arm['name']/f'{seed}-{case["id"]}.json'
   row=json.loads(path.read_text(encoding='utf-8'));q=row['request']
   assert row['id']==case['id'] and row['seed']==seed
   assert q['messages']==[{'role':'system','content':f['system']},{'role':'user','content':case['message']}]
   assert q['response_format']['json_schema']['schema']==f['schema']
   assert q['seed']==seed and q['chat_template_kwargs']['enable_thinking']==arm['thinking']
   assert all(q[k]==arm[k] for k in ['max_tokens','temperature','top_p','top_k','min_p'] if k in arm)
   response=json.loads(row['raw_response']);assert response['model']=='vra-draft-screen'
   row['reasoning_present']=bool(response['choices'][0]['message'].get('reasoning_content'))
   row['response_finish']=response['choices'][0]['finish_reason'];data.append(row)
  rows.append({'arm':arm['name'],'seed':seed,'strict_passed':sum(x['strict'] for x in data),'total':len(data),
   'source_and_shape_valid':sum(x.get('input_verified',False) for x in data),
   'mean_seconds':round(statistics.mean(x['seconds'] for x in data),3),'maximum_seconds':max(x['seconds'] for x in data),
   'completion_tokens':sum(x.get('usage',{}).get('completion_tokens',0) for x in data),
   'thinking_responses':sum(x['reasoning_present'] for x in data),
   'finish_reasons':dict(collections.Counter(x['response_finish'] for x in data)),
   'failures':dict(collections.Counter(x.get('failure','passed') for x in data)),
   'outcomes':[{'id':x['id'],'strict':x['strict'],'failure':x.get('failure'),'draft_outcome':x.get('draft',{}).get('outcome'),'draft_issues':x.get('draft',{}).get('issues')} for x in data]})
  all_rows+=data
assert len(all_rows)==90
out={'frozen_sha256':r['frozen_sha256'],'requests_audited':90,'payloads_match_freeze':True,'gold_in_model_messages':False,
 'servers_stopped':True,'rows':rows,'decisions':r['decisions'],
 'adopted_configuration':None,'product_integrated':False,'score_before':78,'score_after':78,
 'test_design_limit':'N04 and N10 beam reference inputs have span/depth<10; correct numeric results are screened by existing product. Original strict failures remain, but not attributable to formula error.',
 'application_execution_verified':False,'browser':'user_deferred',
 'next_source_catalog':'Unintegrated deterministic position prototype with14 unit tests; no model or application acceptance yet.'}
assert not any(d['eligible'] for d in r['decisions']),'Eligible configuration requires an explicit review; do not auto-reject'
(BASE/'summary.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:out[k] for k in ['requests_audited','payloads_match_freeze','servers_stopped','decisions']},ensure_ascii=False))
