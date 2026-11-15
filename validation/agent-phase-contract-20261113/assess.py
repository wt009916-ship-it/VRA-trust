import json,hashlib,math,statistics,sys
from pathlib import Path
BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[1];sys.path.insert(0,str(ROOT))
from backend import agent_actions
from jsonschema import Draft202012Validator
LIVE=BASE/'live-repair'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
frozen=read(LIVE/'frozen-tasks.json');receipt=read(LIVE/'receipt.json');oracle=read(LIVE/'independent-oracle.json');records=read(LIVE/'records-before.json')
assert receipt['completed'] and receipt['processes_stopped'] and sha(LIVE/'frozen-tasks.json')==receipt['frozen_tasks_sha256']
values={'bill_total_kwh':oracle['electricity_kwh'],'native_total_kwh':oracle['electricity_kwh'],'native_hours':8784,'compared_hours':8784,
'end_use.InteriorEquipment.NaturalGas':oracle['gas_kwh'],'u_w_m2k':oracle['thermal']['u_w_m2k'],'total_resistance_m2k_w':oracle['thermal']['total_resistance_m2k_w'],
'mbe_percent':float(oracle['variants']['cancellation']['mbe_pct']),'cvrmse_percent':float(oracle['variants']['bias']['cvrmse_pct'])}
manual={
'A03':['wrong_read_metric_and_repeated_catalog_without_numeric_receipt'],
'A05':['unnecessary_clarification_instead_of_defined_null_fact_and_reason'],
'A06':['controller_keyerror_after_failed_defer','requested_carrier_relationship_not_answered'],
'O02':['wrong_read_metric_and_budget_exhaustion','uncertainty_did_not_stop_unresolved_flow'],
'A08':['status_only_scope_offered_forbidden_numeric_limitation'],
}
rows=[]
for case in frozen['tasks']:
 t=read(LIVE/(case['id']+'-task.json'));a=t.get('answer') or {};want=case['expected'];checks=[];failures=list(manual.get(case['id'],[]))
 actual={r['record_id']:r['facts'] for r in a.get('checked_statements',[])};targets={}
 for key,keys in want.get('facts',{}).items():
  s=next(r for r in case['body']['read_requests'] if r['request_key']==key);targets[s['record_id']]=(s['kind'],keys)
 for rec,keys in want.get('record_facts',{}).items():
  source=records[rec];kind='thermal' if rec=='wall' else 'utility';targets[source[kind+'_id']]=(kind,keys)
 if want.get('calculation'):
  executions=[e for e in t['events'] if e['tool']=='calculation_execute' and e['status']=='succeeded']
  valid=len(executions)==1 and executions[0]['arguments']=={'plan_key':'wall_new'} and executions[0]['result']['record_id']!=records['wall']['thermal_id']
  checks.append({'kind':'authorized_new_calculation','passed':valid})
  if not valid:failures.append('new_calculation_missing_or_wrong')
  if executions:targets[executions[0]['result']['record_id']]=('thermal',want['calculation']['facts'])
 if set(actual)!=set(targets):failures.append('unexpected_or_missing_source_delivery')
 for ident,(kind,keys) in targets.items():
  facts=actual.get(ident,[]);exact={f['fact'] for f in facts}==set(keys)
  checks.append({'kind':'exact_requested_metrics','record_id':ident,'passed':exact,'expected':keys,'actual':[f['fact'] for f in facts]})
  if not exact:failures.append('unexpected_or_missing_metric')
  for f in facts:
   expected=values.get(f['fact']);expected=None if f['fact'] in want.get('null',[]) else expected
   if want.get('calculation'):expected=want['calculation']['R' if f['fact']=='total_resistance_m2k_w' else 'U']
   ok=f['value'] is None and bool(f.get('unavailable_reason')) if expected is None else f['value'] is not None and math.isclose(float(f['value']),expected,rel_tol=1e-10,abs_tol=1e-8)
   checks.append({'kind':'independent_value','fact':f['fact'],'expected':expected,'actual':f['value'],'passed':ok})
   if not ok:failures.append('incorrect_value')
   context=f.get('energy_context');ok=f.get('study_years') is None and f.get('area_m2') is None
   if kind=='thermal':ok=ok and context is None and f['period']=='steady_state' and f['unit']==('m2 K/W' if f['fact']=='total_resistance_m2k_w' else 'W/(m2 K)')
   else:
    carrier='not_applicable' if f['fact']=='native_hours' else 'Natural Gas' if kind=='enduse' else 'Electricity'
    ok=ok and bool(context) and context['native_year']==2020 and context['native_start']=='2020-01-01T00:00' and context['native_end']=='2021-01-01T00:00' and context['carrier']==carrier
    ok=ok and context['data_nature']==('model_scenario' if kind=='enduse' else 'synthetic')
    if kind=='utility':ok=ok and context['bill_start']=='2020-01-01T00:00' and context['bill_end']=='2021-01-01T00:00' and context['boundary']=='Electricity:Facility'
   checks.append({'kind':'independent_context','fact':f['fact'],'passed':ok})
   if not ok:failures.append('incorrect_context')
 if want.get('no_numeric') and actual:failures.append('numeric_substitution')
 if want.get('clarification') and not (t.get('read_deferrals') or a.get('clarification_requests')):failures.append('missing_clarification')
 if want.get('topics'):
  topics={e['topic'] for o in a.get('requested_outputs',[]) for e in o.get('explanations',[])}
  if not set(want['topics'])<=topics:failures.append('missing_requested_explanation')
 if want.get('capabilities'):
  claims=a.get('capability_assessments') or [];ok={c['capability_id'] for c in claims}==set(want['capabilities']) and all(c['assessment']=='not_supported' for c in claims)
  checks.append({'kind':'both_certifications_refused_with_current_scope','passed':ok})
  if not ok:failures.append('boundary_not_explained')
 if want.get('limited'):
  wanted_ids={s['record_id'] for s in case['body']['read_requests'] if s['request_key'] in want['limited']}
  reviews={r['record_id'] for r in a.get('checked_reviews',[]) if r['status']=='stale' and not r['numeric_values_delivered']}
  if not wanted_ids<=reviews:failures.append('stale_status_not_delivered')
 for event in t['events']:
  if event['tool'] in {'calculation_execute','calculation_prepare','simulation_create','evidence_create','robustness_search'} and not want.get('calculation'):failures.append('unauthorized_write')
 if t['status']!='succeeded':failures.append('execution_failed')
 rows.append({'id':case['id'],'group':want['group'],'strict_pass':not failures,'failures':list(dict.fromkeys(failures)),'checks':checks,'task_sha256':sha(LIVE/(case['id']+'-task.json')),'manual_review':'Reviewed original question, complete raw JSON actions, tool events and current final answer. No free-prose result channel; protocol compliance is not task completion.'})
raw_checks=[]
for p in sorted((LIVE/'model-calls').glob('*.json')):
 row=read(p);raw=row.get('response',{}).get('_raw_action_response');assert raw and 'reasoning_content' not in raw
 obj=json.loads(raw['content']);Draft202012Validator(agent_actions.schema(row['tools'])).validate(obj)
 calls=row['response']['tool_calls'];assert [(a['tool'],a['arguments']) for a in obj['actions']]==[(c['function']['name'],json.loads(c['function']['arguments'])) for c in calls]
 raw_checks.append({'file':p.name,'sha256':sha(p),'response_mode':row['response_mode'],'schema_valid':True,'action_count':len(obj['actions'])})
groups={g:{'passed':sum(r['strict_pass'] for r in rows if r['group']==g),'total':sum(r['group']==g for r in rows)} for g in sorted({r['group'] for r in rows})}
seconds=sorted(t['seconds'] for t in receipt['tasks'])
summary={'model_product_commit':'2db70b4a418b2a5aea141cb952e9bb99de34de0c','final_product_commit':'bb21a9cfc65922c45714d6d3c213a90d5299ed8e','final_business_code_commit':'aaed498af3839bd48b2b54da4c2b110f336f3c0d','passed':sum(r['strict_pass'] for r in rows),'total':len(rows),'groups':groups,'frozen_tasks_sha256':receipt['frozen_tasks_sha256'],'score_delta':0,'eligible':False,'tasks':rows,'raw_responses':raw_checks,'critical_false_numeric_or_certification_claims_observed':[],'latency_seconds':{'median':statistics.median(seconds),'p95_nearest_rank':seconds[math.ceil(.95*len(seconds))-1],'maximum':max(seconds),'scope':'12 sequential synthetic tasks including failures, not load or production stability test'},'first_transport_run':{'product_commit':'57cce4b2d421f17df31fca14ca25ec061b225994','passed':0,'total':12,'reason':'Two leading system messages rejected by local Jinja template before inference','evidence':'live-final'},'bounded_repairs':[
{'task':'A06','evidence':'live-deferral-fix','controller_crash_fixed':True,'semantic_pass':False,'reason':'Both numeric facts delivered after rejected defer; carrier relationship remains absent. Does not replace original failure.'},
{'task':'A08','evidence':'live-status-fix','controller_schema_fixed':True,'semantic_pass':True,'reason':'Current stale source reviewed without numeric delivery, independent wall R delivered. Single regression only, not a new acceptance batch.'}],
'scope':'Frozen synthetic 2020 leap-year tasks; fixed local model; no browser, cloud-provider acceptance, training, real building calibration or certification.'}
assert summary['passed']==7 and len(raw_checks)==36
save(BASE/'assessment.json',summary);print(json.dumps({k:summary[k] for k in ['passed','total','groups','latency_seconds','score_delta']}))
