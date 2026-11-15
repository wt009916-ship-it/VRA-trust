"""Independent half-day discrete enumeration; no import from the application."""
import itertools,json
from pathlib import Path
root=Path(__file__).parent
def feasible(tasks,capacities,starts):
 finishes={k:starts[k]+t['duration_half_days'] for k,t in tasks.items()}
 for k,t in tasks.items():
  if any(starts[k]<finishes[p]+lag for p,lag in t['predecessors']):return False
 for tick in range(max(finishes.values(),default=0)):
  for r,capacity in capacities.items():
   if sum(t['demands'].get(r,0) for k,t in tasks.items() if starts[k]<=tick<finishes[k])>capacity:return False
 return True
def optimum(tasks,capacities,horizon):
 keys=list(tasks);best=horizon+1;witness=None;feasible_count=0
 for values in itertools.product(*(range(horizon-tasks[k]['duration_half_days']+1) for k in keys)):
  starts=dict(zip(keys,values));finish=max(starts[k]+tasks[k]['duration_half_days'] for k in keys)
  if finish>best:continue
  if feasible(tasks,capacities,starts):
   feasible_count+=1
   if finish<best:best=finish;witness=starts
 assert witness is not None
 return {'minimum_makespan_days':best/2,'one_witness_start_days':{k:v/2 for k,v in witness.items()},'scope':'only stated half-day integer grid, not general continuous optimization'}
def task(days,demands,preds=()):return {'duration_half_days':round(days*2),'demands':demands,'predecessors':[(k,round(lag*2)) for k,lag in preds]}
cases=[
 {'id':'R01','capacities':{'crew':1},'tasks':{'A':task(2,{'crew':1}),'B':task(3,{'crew':1}),'C':task(1,{'crew':1},[('A',0),('B',0)])},'priority':['A','B','C'],'expected_starts_days':{'A':0,'B':2,'C':5},'expected_finish_days':6},
 {'id':'R02','capacities':{'crew':2},'tasks':{'A':task(4,{'crew':1}),'B':task(2,{'crew':2}),'C':task(3,{'crew':1})},'priority':['A','B','C'],'expected_starts_days':{'A':0,'B':4,'C':0},'expected_finish_days':6,'purpose':'Later-priority task must be allowed in the free earlier slot; serial selection does not require serial time'},
 {'id':'R03','capacities':{'crew':2,'crane':1},'tasks':{'A':task(2,{'crew':1,'crane':1}),'B':task(3,{'crew':1}),'C':task(1,{'crew':2,'crane':1},[('A',.5)])},'priority':['A','C','B'],'expected_starts_days':{'A':0,'C':2.5,'B':3.5},'expected_finish_days':6.5,'purpose':'Feasible priority schedule is intentionally worse than the independent small-grid optimum'},
 {'id':'R04','capacities':{'crew':1},'tasks':{'M':task(0,{}),'A':task(2,{'crew':1},[('M',1)]),'B':task(1,{'crew':1},[('A',0)])},'priority':['M','A','B'],'expected_starts_days':{'M':0,'A':1,'B':3},'expected_finish_days':4},
]
for case in cases:
 starts={k:round(v*2) for k,v in case['expected_starts_days'].items()}
 assert feasible(case['tasks'],case['capacities'],starts)
 assert max((starts[k]+t['duration_half_days'])/2 for k,t in case['tasks'].items())==case['expected_finish_days']
 case['independent_discrete_optimum']=optimum(case['tasks'],case['capacities'],14)
assert cases[2]['independent_discrete_optimum']['minimum_makespan_days']==4
out=root/'reference-frozen.json';assert not out.exists()
out.write_text(json.dumps({'status':'independent reference only; product not implemented or tested','cases':cases,'adversarial':['unknown capacity','zero capacity with positive-duration demand','individual demand above capacity','missing duration','source withdrawal','cross-project source','cycle','no invented work calendar']},indent=2)+'\n',encoding='utf-8')
print(json.dumps({'reference_cases':len(cases),'intentionally_suboptimal_case':{'priority_result':6.5,'grid_optimum':4},'application_tests_run':0}))
