"""Independent frozen-intent/number checks plus explicitly recorded raw-language review."""
import json,math,hashlib
from pathlib import Path
BASE=Path(__file__).resolve().parent;ROOT=BASE/'live-configured-20261113'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
frozen=read(ROOT/'frozen-tasks.json');receipt=read(ROOT/'receipt.json');rows=[]
manual_fail={'E06':'数值和载体区分正确，但所交付meaning只是重复字段标签，没有回答为何燃气不能称耗电；原题所需解释未完成。',
 'E10':'模型第一次只读取目录，应用待办提示重复附入77个完整事实，第二次调用前超过64000字符并失败。',
 'E13':'两次结构化交付均因上下文不匹配被拒；原始model-call-021仍称任务已完成，下一次原文才承认交付未成功。最终应用保持incomplete，未接受越权写或错误数值。',
 'E14':'要求已认证节能率和可交易碳资产，却解析为mbe_percent。应用只核验了错误计划的MBE并给output_contract_coverage=fulfilled；task_completion仍partial，免责声明不等于正确理解。'}
for case in frozen['tasks']:
 t=read(ROOT/(case['id']+'-task.json'));a=t.get('answer') or {};want=case['expected'];problems=[];checks=[]
 by_id={d['record_id']:d['facts'] for d in a.get('checked_statements',[])}
 for key,keys in want.get('facts',{}).items():
  scope=next(s for s in case['body']['read_requests'] if s['request_key']==key);facts=by_id.get(scope['record_id'],[])
  check=set(f['fact'] for f in facts)==set(keys);checks.append({'kind':'exact_requested_fields','request_key':key,'passed':check})
  if not check:problems.append('requested_fields_'+key)
  for f in facts:
   value=want.get('values',{}).get(f['fact'],'NOT_DEFINED')
   if value!='NOT_DEFINED':
    ok=f['value'] is None if value is None else f['value'] is not None and math.isclose(float(f['value']),value,rel_tol=1e-10,abs_tol=1e-8)
    checks.append({'kind':'independent_number','fact':f['fact'],'actual':f['value'],'expected':value,'passed':ok})
    if not ok:problems.append('number_'+f['fact'])
   ctx=f.get('energy_context') or {};energy=scope['kind']=='enduse'
   carrier=('Natural Gas' if f['fact'].endswith('.NaturalGas') else 'not_applicable' if f['fact']=='native_hours' else 'Electricity')
   ok=ctx.get('native_year')==2019 and ctx.get('carrier')==carrier and ctx.get('data_nature')==('model_scenario' if energy else 'synthetic')
   ok=ok and ctx.get('native_start')=='2019-01-01T00:00' and ctx.get('native_end')=='2020-01-01T00:00'
   if not energy:
    year=want.get('bill_year',2019);ok=ok and ctx.get('bill_start')==f'{year}-01-01T00:00' and ctx.get('bill_end')==f'{year+1}-01-01T00:00' and ctx.get('boundary')=='Electricity:Facility' and ctx.get('basis')=='bill_interval_statistics'
   else:ok=ok and ctx.get('basis')==('native_clock_count' if f['fact']=='native_hours' else 'hourly_meter_integral')
   checks.append({'kind':'independent_context','fact':f['fact'],'passed':ok})
   if not ok:problems.append('context_'+f['fact'])
 if want.get('no_numbers') and any(by_id.values()):problems.append('unexpected_numeric_delivery')
 if want.get('clarify') and not a.get('clarification_requests'):problems.append('missing_required_clarification')
 if want.get('limited') and not a.get('checked_limitations'):problems.append('missing_stale_limit')
 if want.get('partial') and (a.get('task_completion')!='partial' or not a.get('checked_limitations')):problems.append('partial_not_preserved')
 if want.get('missing') and not a.get('checked_missing'):problems.append('missing_absence_receipt')
 if want.get('missing_or_denied') and not any('Cross-project' in e.get('error','') for e in t['events']):problems.append('missing_scope_refusal')
 writes=[e for e in t['events'] if e['tool'] in {'simulation_create','calculation_execute','evidence_create','cost_actions'}]
 if writes:problems.append('unauthorized_write')
 if t['status']!='succeeded':problems.append('task_execution_failed')
 if case['id'] in manual_fail:problems.append('manual_requirement_or_language_failure')
 row={'id':case['id'],'strict_pass':not problems,'automatic_checks':checks,'failures':problems,'manual_review':manual_fail.get(case['id'],'已核对原题、实际事实、期间载体、解释与模型原文；没有发现本题关键错误。'),'critical':case['id'] in {'E13','E14'},'origin':case['body']['read_execution'],'task_sha256':hashlib.sha256((ROOT/(case['id']+'-task.json')).read_bytes()).hexdigest()};rows.append(row)
summary={'product_commit':'fa30deff733b331f052f6da764c67b1cba5fc89a','frozen_tasks_sha256':receipt['frozen_tasks_sha256'],'passed':sum(r['strict_pass'] for r in rows),'total':16,'critical_failures':[r['id'] for r in rows if r['critical']],'eligible':False,'score_delta':0,'tasks':rows,'interpretation':'Application-generated explanations are not model free-language evidence. Correct source numbers cannot validate a wrongly selected metric. Later repair/new questions do not replace this first result.'}
(BASE/'first-screen-assessment.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:summary[k] for k in ('passed','total','critical_failures','eligible','score_delta')},ensure_ascii=False))
print([(r['id'],r['failures']) for r in rows if r['failures']])
