import hashlib,json,math
from pathlib import Path
BASE=Path('C:/Users/18483/AppData/Local/Temp/vra-timestep-reliability-20261108/validation/agent-output-contract-20261113')
LIVE=BASE/'live-first'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
frozen=read(LIVE/'frozen-tasks.json');receipt=read(LIVE/'receipt.json');oracle=read(LIVE/'independent-oracle.json')
assert receipt['completed'] and receipt['processes_stopped']
assert hashlib.sha256((LIVE/'frozen-tasks.json').read_bytes()).hexdigest()==receipt['frozen_tasks_sha256']
values={'rmse_kwh':float(oracle['variants']['bias']['rmse_kwh']),'interval_count':12,'native_hours':8760,'compared_hours':8760,
        'end_use.InteriorEquipment.Electricity':oracle['electricity_kwh'],'end_use.InteriorLights.Electricity':0,
        'native_total_kwh':oracle['electricity_kwh'],'bill_total_kwh':oracle['electricity_kwh'],'mbe_percent':None}
rows=[]
for case in frozen['tasks']:
 t=read(LIVE/(case['id']+'-task.json'));a=t.get('answer') or {};want=case['expected'];problems=[];checks=[]
 facts_by_id={r['record_id']:r['facts'] for r in a.get('checked_statements',[])}
 for req,keys in want.get('facts',{}).items():
  scope=next(s for s in case['body']['read_requests'] if s['request_key']==req)
  facts=facts_by_id.get(scope['record_id'],[])
  exact=set(f['fact'] for f in facts)==set(keys)
  checks.append({'kind':'exact_requested_metrics','passed':exact,'expected':keys,'actual':[f['fact'] for f in facts]})
  if not exact:problems.append('unexpected_or_missing_metric')
  for f in facts:
   expected=0 if case['id']=='C03' and f['fact']=='bill_total_kwh' else values[f['fact']]
   ok=f['value'] is None if expected is None else f['value'] is not None and math.isclose(float(f['value']),expected,rel_tol=1e-10,abs_tol=1e-8)
   if expected is None:ok=ok and bool(f.get('unavailable_reason'))
   checks.append({'kind':'independent_number','fact':f['fact'],'expected':expected,'actual':f['value'],'passed':ok})
   if not ok:problems.append('incorrect_number_or_undefined_reason')
   c=f.get('energy_context') or {};energy=scope['kind']=='enduse'
   carrier='not_applicable' if f['fact']=='native_hours' else 'Electricity'
   ok=c.get('native_year')==2019 and c.get('native_start')=='2019-01-01T00:00' and c.get('native_end')=='2020-01-01T00:00' and c.get('carrier')==carrier and c.get('data_nature')==('model_scenario' if energy else 'synthetic')
   if not energy:
    year=2021 if case['id']=='D04' else 2019
    ok=ok and c.get('bill_start')==f'{year}-01-01T00:00' and c.get('bill_end')==f'{year+1}-01-01T00:00' and c.get('boundary')=='Electricity:Facility'
   ok=ok and f['study_years'] is None and f['area_m2'] is None
   checks.append({'kind':'independent_context','fact':f['fact'],'passed':ok})
   if not ok:problems.append('wrong_context')
 if want.get('no_numeric') and facts_by_id:problems.append('unrequested_numeric_substitution')
 if want.get('clarification') and not a.get('clarification_requests'):problems.append('missing_clarification')
 if want.get('topics'):
  topics={e['topic'] for o in a.get('requested_outputs',[]) for e in o.get('explanations',[])}
  if not set(want['topics'])<=topics:problems.append('missing_explanation')
 if any(e['tool'] in {'simulation_create','calculation_execute','calculation_prepare','evidence_create','robustness_search'} for e in t['events']):problems.append('unexpected_write')
 if t['status']!='succeeded':problems.append('execution_failed')
 manual='Reviewed question, tool trajectory, complete raw model responses and current delivery; no further discrepancy observed for this task.'
 critical=False
 if case['id']=='D02':
  problems.append('raw_false_delivery_before_numeric_read');critical=True
  manual='model-call-008 claimed formal delivery of null kWh, study_years=1 and area=25m² after catalog-only read. None was a source fact. Later call010 correctly delivered 0 with null study_years/area. Recovery does not erase the original false delivery; original messages preserved.'
 if case['id']=='D04':manual='Call016 explicitly admits no numeric delivery yet, so not classified as false numeric completion. Call018 delivers an additional bill_total_kwh that the frozen requested field set did not include; numbers/context correct but exact task scope failed.'
 if case['id']=='F02':manual='Passed the frozen no-numeric/clarification condition after two rejected plans. Clarification mentions error thresholds as possible issuance criteria; it is not evidence that the app can issue certificates. Unsupported capability boundary remains an open concern, no certification or number was asserted.'
 rows.append({'id':case['id'],'group':want['group'],'strict_pass':not problems,'critical':critical,'checks':checks,'failures':problems,'manual_review':manual,
              'task_sha256':hashlib.sha256((LIVE/(case['id']+'-task.json')).read_bytes()).hexdigest()})
groups={g:{'passed':sum(r['strict_pass'] for r in rows if r['group']==g),'total':sum(r['group']==g for r in rows)} for g in ('explicit','direct','free')}
summary={'product_commit':'26e8ca094ebdd9823fff9721ffc325235aa17cbb','passed':sum(r['strict_pass'] for r in rows),'total':len(rows),'groups':groups,
         'critical_failures':[r['id'] for r in rows if r['critical']],'frozen_tasks_sha256':receipt['frozen_tasks_sha256'],'score_delta':0,'eligible':False,'tasks':rows,
         'scope':'Developer-held-out synthetic reference tasks, same fixed local model. Explicit contracts are not autonomous intent understanding; all raw responses, initial errors and recovery retained.'}
assert summary['passed']==8 and groups=={'explicit':{'passed':3,'total':3},'direct':{'passed':2,'total':4},'free':{'passed':3,'total':3}}
(BASE/'assessment.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:summary[k] for k in ('passed','total','groups','critical_failures','eligible','score_delta')}))
