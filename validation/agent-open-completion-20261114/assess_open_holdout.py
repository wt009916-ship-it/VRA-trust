import json,hashlib,math
from pathlib import Path
root=Path.cwd();out=root/'validation/agent-open-completion-20261114';live=out/'live-holdout-e'
frozen=json.loads((live/'frozen-tasks.json').read_text(encoding='utf-8'))
records=json.loads((live/'records-before.json').read_text(encoding='utf-8'))
oracle=json.loads((live/'independent-oracle.json').read_text(encoding='utf-8'))
receipt=json.loads((live/'receipt.json').read_text(encoding='utf-8'))
assert receipt['completed'] and receipt['processes_stopped']
results=[]
for case in frozen['tasks']:
 task=json.loads((live/(case['id']+'-task.json')).read_text(encoding='utf-8'))
 expected={next(v for k,v in records[name].items() if k in ('thermal_id','utility_id','enduse_id')):set(keys) for name,keys in case['expected']['record_facts'].items()}
 observed={row['record_id']:{f['fact'] for f in row['facts']} for row in (task.get('answer') or {}).get('checked_statements',[])}
 passed=task['status']=='succeeded' and expected==observed
 forbidden=case['expected'].get('forbidden_read_record')
 if forbidden:
  assert not any(forbidden in json.dumps(e.get('arguments',{})) for e in task['events'] if e['tool'] in {'utility_comparison_read','professional_read_many'})
 if case['id']=='N02':
  values={f['fact']:float(f['value']) for row in task['answer']['checked_statements'] for f in row['facts']}
  assert math.isclose(values['mbe_percent'],float(oracle['variants']['bias']['mbe_pct']),rel_tol=1e-10)
  assert math.isclose(values['rmse_kwh'],float(oracle['variants']['cancellation']['rmse_kwh']),rel_tol=1e-10)
 if case['id']=='N04':assert float(task['answer']['checked_statements'][0]['facts'][0]['value'])==8784
 results.append({'id':case['id'],'passed':passed,'status':task['status'],'error':task.get('error'),'expected':{k:sorted(v) for k,v in expected.items()},'observed':{k:sorted(v) for k,v in observed.items()}})
for name,digest in receipt['product_sha256'].items():
 data=(out/'source-snapshot'/name).read_bytes()
 assert hashlib.sha256(data).hexdigest()==digest,name
assessment={'passed':sum(r['passed'] for r in results),'total':len(results),'cases':results,
 'source_snapshot':'source-snapshot','score_delta':0,'scope':'Fresh four-case fixed local-model screen before calculation-plan compatibility and delivery-deduplication patches.'}
(out/'holdout-assessment.json').write_text(json.dumps(assessment,indent=2)+'\n',encoding='utf-8')
p=root/'docs/AGENT_OPEN_COMPLETION_PROGRESS.md'
with p.open('a',encoding='utf-8') as f:f.write("""
## 新题及兼容性增量

新的四题一次验收严格2/4。N02分别交付MBE与RMSE，N04遵守排除记录且只交付比较小时数。N01多报墙体指标后超预算，N03多报总R及材料层R。原问题指标选择仍有缺口，评分增量0。全组回归发现计算计划与新增完成追踪重复，已限制冻结计算计划使用既有执行阶段。另补同一答复连续相同交付的合并，保留finish与不同字段及原始响应。两个后续补丁正在回归验证，新题分数不回填。
""")
print(json.dumps({'passed':assessment['passed'],'total':assessment['total']}))

