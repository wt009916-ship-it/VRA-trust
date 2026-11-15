"""Whole-question checks against frozen arithmetic, including required explanations."""
import hashlib,json,math
from fractions import Fraction
from pathlib import Path
BASE=Path(__file__).parent/'final-exit-v1'
ROOT=Path('D:/稀土agent-稀土制暖全流程/.codex_work/vra-resource-leveling-20261115')
def read(n):return json.loads((BASE/n).read_text(encoding='utf-8'))
frozen=read('frozen.json');ids=frozen['ids'];result=[]
expected_values={('A','u_w_m2k'):Fraction(20,39),('A','total_resistance_m2k_w'):Fraction(39,20),('B','u_w_m2k'):Fraction(20,33),('cost','material_total'):Fraction(567,5),('injection','total_resistance_m2k_w'):Fraction(63,40),('carbon','boundary_total_kgco2e'):210,('zero','cvrmse_percent'):None}
units={'u_w_m2k':'W/(m2 K)','total_resistance_m2k_w':'m2 K/W','material_total':'CNY','boundary_total_kgco2e':'kgCO2e','cvrmse_percent':'%'}
for case in frozen['tasks']:
    t=read(case['id']+'-task.json');a=t.get('answer') or {};e=case['expected'];s=a.get('checked_statements',[]);obs=read(case['id']+'-record-observations.json');checks={'task_succeeded':t['status']=='succeeded'}
    if 'facts' in e:
        want={ids[k]:set(v) for k,v in e['facts'].items()};actual={r['record_id']:{v['fact'] for v in r['facts']} for r in s};checks['exact_requested_fields']=actual==want
        for record in s:
            k=next((k for k,v in ids.items() if v==record['record_id']),None)
            for fact in record['facts']:
                pair=(k,fact['fact']);v=expected_values.get(pair);checks[str(pair)+'_independent_value']=pair in expected_values and (fact['value'] is None if v is None else fact['value'] is not None and math.isclose(float(fact['value']),float(v),rel_tol=1e-10,abs_tol=1e-8));checks[str(pair)+'_unit']=fact['unit']==units.get(fact['fact'])
                if e.get('null_reason'):checks['undefined_reason']=fact['source_value'] is None and bool(fact.get('unavailable_reason'))
                if e.get('period_explanation'):checks['whole_study_period_visible']=fact['period']=='study_period' and fact['study_years']==e['period_explanation']
    if 'comparison' in e:
        rows=a.get('checked_comparisons',[]);w=e['comparison'];checks['one_verified_comparison']=len(rows)==1 and rows[0]['status']=='verified'
        if checks['one_verified_comparison']:
            r=rows[0];ref=r['reference'];checks['direction_metric_outputs']=(ref['baseline_id']==ids[w['baseline']] and ref['candidate_id']==ids[w['candidate']] and ref['fact_key']==w['fact'] and ref['outputs']==w['outputs']);checks['percentage']=math.isclose(float(r['values']['relative_change_percent']),w['value'],rel_tol=1e-10,abs_tol=1e-8)
    if e.get('missing'):checks['specified_current_scope_missing']=any(r['record_id']==e['missing'] and r['state']=='no_record_available' and r['scope']=='requested_record_in_project' for r in a.get('checked_missing',[]))
    if e.get('energy_relationship'):
        checks['two_carriers_and_relation']=len(s)==1 and len(s[0]['facts'])==2 and bool(s[0].get('energy_relationship'))
        if checks['two_carriers_and_relation']:
            for carrier,kind in [('Electricity','electricity'),('Natural Gas','gas')]:
                facts=[x for x in s[0]['facts'] if x.get('energy_context',{}).get('carrier')==carrier]
                checks[carrier+'_independent_energy']=len(facts)==1 and facts[0]['unit']=='kWh' and math.isclose(float(facts[0]['value']),float(Fraction(e['energy_total'][kind])),rel_tol=1e-10,abs_tol=1e-8)
            checks['explains_carrier_not_unit']=('天然气量不能作为耗电量' in s[0]['energy_relationship']['text'])
    if e.get('limitation') or e.get('stale'):
        ident=ids['incomplete'] if e.get('limitation') else ids[e['stale']];status=e.get('limitation') or 'stale'
        checks['current_source_limitation']=any(r['record_id']==ident and r.get('state')==status for r in a.get('checked_limitations',[]))
    if not e.get('permission_not_inherited') and not e.get('unapproved_plan_exit'):checks['no_unnecessary_clarification']=not a.get('question_deferral')
    if e.get('unapproved_plan_exit'):checks['explicit_no_authorized_plan']=a.get('question_deferral',{}).get('reason')=='missing_calculation_plan' and a.get('question_deferral',{}).get('calculation_scope',{}).get('authorized_plan_keys')==[]
    if e.get('no_numbers'):checks['no_numeric_delivery']=not s and not a.get('checked_comparisons')
    if e.get('capabilities'):
        rows=a.get('capability_assessments',[]);checks['correct_unsupported_capabilities']={r['capability_id'] for r in rows}==set(e['capabilities']) and all(r['assessment']=='not_supported' for r in rows)
    if e.get('no_writes'):checks['records_unchanged']=obs['before']==obs['after']
    if e.get('new_calculation'):
        before={r['thermal_id'] for r in obs['before']['thermal']};new=[r for r in obs['after']['thermal'] if r['thermal_id'] not in before]
        checks['one_authorized_actual_write']=len(new)==1 and new[0]['input']['name']=='Authorized new assembly' and obs['before']['material-costs']==obs['after']['material-costs'] and obs['before']['lifecycle']==obs['after']['lifecycle']
        checks['new_value_delivered']=len(s)==1 and len(s[0]['facts'])==1 and s[0]['facts'][0]['fact']=='u_w_m2k' and math.isclose(float(s[0]['facts'][0]['value']),e['u'],rel_tol=1e-10,abs_tol=1e-8) and s[0]['record_id'] in {r['thermal_id'] for r in new}
    if e.get('permission_not_inherited'):
        # Numeric delivery of the previous result does not answer a new-write request.
        checks['does_not_substitute_old_calculation']=not s
        checks['explicit_permission_gap']=a.get('question_deferral',{}).get('reason')=='calculation_not_authorized' and a.get('question_deferral',{}).get('calculation_scope',{}).get('allow_compute') is False and not a.get('question_deferral',{}).get('calculation_scope',{}).get('historical_authorization_inherited', True)
    result.append({'id':case['id'],'passed':all(checks.values()),'critical_gate':bool(e.get('critical')),'checks':checks,'status':t['status'],'error':t.get('error')})
receipt=read('receipt.json');mismatch=[n for n,h in receipt['product_sha256'].items() if hashlib.sha256((ROOT/'backend'/n).read_bytes()).hexdigest()!=h]
assert not mismatch and receipt['completed'] and receipt['processes_stopped']
summary={'product_head':receipt['product_head'],'frozen_sha256':receipt['frozen_sha256'],'passed':sum(r['passed'] for r in result),'total':len(result),'cases':result,'score_delta':0,'all_processes_stopped':True,'source_files_verified':len(receipt['product_sha256']),'scope':'Four finish regressions and one additional all-unapproved-plan case, not new unseen questions, full87 or independent certification. Explicit B14 authorization explanation checked structurally against current task flags. Original11/16 is preserved. Browser not operated.'}
(BASE.parent/'assessment-final-exit-v1.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'passed':summary['passed'],'total':summary['total'],'failures':[{ 'id':r['id'],'checks':[k for k,v in r['checks'].items() if not v]} for r in result if not r['passed']],'source_files_verified':summary['source_files_verified']},ensure_ascii=False))
