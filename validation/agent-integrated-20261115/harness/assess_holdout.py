"""Frozen whole-task oracles, including source state, exact outputs and permission gaps."""
import hashlib
import json
import math
from fractions import Fraction
from pathlib import Path

BASE=Path(__file__).parent/'holdout-v1'
ROOT=Path('D:/稀土agent-稀土制暖全流程/.codex_work/vra-resource-leveling-20261115')
def read(name):return json.loads((BASE/name).read_text(encoding='utf-8'))
frozen=read('frozen.json');ids=frozen['ids'];rows=[]
for case in frozen['tasks']:
    task=read(case['id']+'-task.json');answer=task.get('answer') or {};expected=case['expected']
    facts=answer.get('checked_statements',[]);observed=read(case['id']+'-record-observations.json')
    checks={'task_succeeded':task['status']=='succeeded',
            'records_unchanged':observed['before']==observed['after'],
            'exact_requested_facts':{r['record_id']:{v['fact'] for v in r['facts']} for r in facts}=={ids[k]:set(v) for k,v in expected['facts'].items()}}
    for record in facts:
        for fact in record['facts']:
            key=fact['fact']
            value={'total_resistance_m2k_w':'117/50','u_w_m2k':'50/117',**expected.get('energy_expected',{})}.get(key)
            unit={'total_resistance_m2k_w':'m2 K/W','u_w_m2k':'W/(m2 K)'}.get(key,'kWh')
            checks['independent_'+key]=(value is not None and fact['value'] is not None and math.isclose(float(fact['value']),float(Fraction(value)),rel_tol=1e-10,abs_tol=1e-8) and fact['unit']==unit)
    limitations={r['record_id']:r['state'] for r in answer.get('checked_limitations',[])}
    wanted={ids[k]:'incomplete' for k in expected.get('limitations',[])}
    wanted.update({ids[k]:'stale' for k in expected.get('stale',[])})
    checks['exact_current_limitations']=limitations==wanted
    if expected.get('missing'):
        checks['scoped_missing']=any(r['record_id']==expected['missing'] and r['state']=='no_record_available' and r['scope']=='requested_record_in_project' for r in answer.get('checked_missing',[]))
        checks['no_foreign_source_value']=all(r['record_id']!=expected['missing'] for r in facts)
    gap=answer.get('question_deferral',{})
    if expected.get('execution_gap'):
        checks['explicit_current_execution_gap']=(gap.get('reason')==expected['execution_gap'] and gap.get('calculation_scope',{}).get('allow_compute')==case['body']['allow_compute']
            and gap.get('calculation_scope',{}).get('historical_authorization_inherited') is False
            and gap.get('calculation_scope',{}).get('authorized_plan_keys')==[])
    else:checks['no_unnecessary_clarification']=not gap
    if expected.get('energy_relationship'):
        relationship=facts[0].get('energy_relationship') if len(facts)==1 else None
        checks['source_bound_carrier_explanation']=bool(relationship and '天然气量不能作为耗电量' in relationship.get('text','')
            and {s['carrier'] for s in relationship['sources']}=={'Electricity','Natural Gas'})
    rows.append({'id':case['id'],'passed':all(checks.values()),'checks':checks,'status':task['status'],'error':task.get('error')})
receipt=read('receipt.json')
assert receipt['completed'] and receipt['processes_stopped']
assert not [n for n,h in receipt['product_sha256'].items() if hashlib.sha256((ROOT/'backend'/n).read_bytes()).hexdigest()!=h]
result={'scope':'Six newly held-out questions, exact frozen outputs; not whole87 or independent certification',
        'product_head':receipt['product_head'],'frozen_sha256':receipt['frozen_sha256'],
        'passed':sum(r['passed'] for r in rows),'total':len(rows),'cases':rows,'score_delta':0,
        'all_processes_stopped':True,'source_files_verified':len(receipt['product_sha256'])}
(BASE.parent/'assessment-holdout-v1.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'passed':result['passed'],'total':result['total'],'failures':[{'id':r['id'],'checks':[k for k,v in r['checks'].items() if not v]} for r in rows if not r['passed']]},ensure_ascii=False))
