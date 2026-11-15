"""Planner-only semantic checks; no professional task or scoring claim."""
import json
from pathlib import Path
import sys

BASE=Path(__file__).parent
folder=BASE/(sys.argv[1] if len(sys.argv)>1 else 'probe-v1')
frozen=json.loads((folder/'frozen.json').read_text(encoding='utf-8'));ids=frozen['ids'];rows=[]
for case in frozen['cases']:
    path=folder/(case['id']+'-plan.json')
    if not path.exists():
        rows.append({'id':case['id'],'passed':False,'checks':{'valid_frozen_plan':False}});continue
    plan=json.loads(path.read_text(encoding='utf-8'));items=plan['items'];key=case['id']
    # Several read items may express disjoint outputs of the same source.
    # Compare output obligations, not a required one-item-per-record shape.
    groups={}; other=[]; duplicate_numeric=False
    for row in items:
        if row['operation']!='read_record':
            other.append(row);continue
        ident=row['record_id']
        if ident not in groups:groups[ident]={**row,'fact_keys':[],'explanation_topics':[]}
        group=groups[ident]
        duplicate_numeric |= bool(set(group['fact_keys']) & set(row['fact_keys']))
        group['fact_keys'].extend(row['fact_keys'])
        group['explanation_topics']=list(dict.fromkeys(group['explanation_topics']+row['explanation_topics']))
    items=[*groups.values(),*other]
    reads=[x for x in items if x['operation']=='read_record']
    checks={'no_unassigned_fragments':not plan['unassigned_fragment_ids'], 'no_duplicate_numeric_obligations':not duplicate_numeric}
    extras=[{'item_key':x['item_key'],'topics':x.get('explanation_topics',[])} for x in reads if set(x.get('explanation_topics',[]))-{'status','meaning','period','energy_relationship'}]
    if key=='H01':
        checks['exact_sources_and_operations']=len(items)==3 and {x['record_id'] for x in reads}=={ids['incomplete'],ids['incomplete2'],ids['fresh']}
        checks['no_partial_stage_substitution']=all(set(x['fact_keys'])<={'boundary_total_kgco2e'} and (x['fact_keys'] or 'status' in x['explanation_topics']) for x in reads if x['record_id'] in {ids['incomplete'],ids['incomplete2']})
        checks['wall_only_U']=any(x['record_id']==ids['fresh'] and x['fact_keys']==['u_w_m2k'] for x in reads)
    elif key=='H02':
        checks['no_unrequested_comparison']=len(items)==2 and len(reads)==2
        checks['old_status_only']=any(x['record_id']==ids['stale_h'] and not x['fact_keys'] and 'status' in x['explanation_topics'] for x in reads)
        checks['current_R_only']=any(x['record_id']==ids['current_h'] and x['fact_keys']==['total_resistance_m2k_w'] for x in reads)
    elif key=='H03':
        checks['current_reference']=len(reads)==1 and reads[0]['record_id']==ids['current_h'] and reads[0]['fact_keys']==['total_resistance_m2k_w']
        creates=[x for x in items if x['operation']=='create_calculation']
        checks['new_task_preserved_with_gap']=len(items)==2 and len(creates)==1 and creates[0]['kind']=='thermal' and creates[0]['execution_requirements']==['current_computation_authorization','current_locked_parameter_plan']
    elif key=='H04':
        checks['new_cost_not_old_record']=len(items)==1 and items[0]['operation']=='create_calculation' and items[0]['kind']=='cost' and items[0]['execution_requirements']==['current_locked_parameter_plan']
    elif key=='H05':
        checks['current_U']=len(reads)==1 and reads[0]['record_id']==ids['injected_h'] and reads[0]['fact_keys']==['u_w_m2k']
        checks['scoped_availability']=len(items)==2 and any(x['operation']=='record_availability' and x['record_id']==ids['foreign'] for x in items)
    elif key=='H06':
        checks['only_two_energy_fields']=len(items)==1 and len(reads)==1 and reads[0]['record_id']==ids['enduse'] and set(reads[0]['fact_keys'])=={'end_use.InteriorLights.Electricity','end_use.InteriorEquipment.NaturalGas'}
        checks['relationship_obligation']=len(reads)==1 and 'energy_relationship' in reads[0]['explanation_topics']
    elif key=='I07':
        checks['negation_preserved']=len(items)==1 and len(reads)==1 and reads[0]['record_id']==case['expected']['record_id'] and reads[0]['fact_keys']==['total_resistance_m2k_w']
    elif key=='I08':
        checks['contradiction_preserved']=len(items)==1 and items[0]['operation']=='clarify_request' and items[0]['reason']=='contradictory_request'
    rows.append({'id':key,'passed':all(checks.values()),'checks':checks,'additional_explanation_topics_for_review':extras})
receipt=json.loads((folder/'receipt.json').read_text(encoding='utf-8'))
assert receipt['completed'] and receipt['process_stopped']
result={'scope':'Planner-only operations, sources and numeric-output obligations; optional explanation verbosity recorded separately. Not task execution or app score.',
        'passed':sum(r['passed'] for r in rows),'total':len(rows),'cases':rows,'score_delta':0,'normalization':'Read-only output items grouped by identical source ID; duplicate numeric obligations still fail. Original item-shape checker kept separately.',
        'cases_H':'Known tasks reused for a new planning-stage regression','cases_I':'Two new planning-only probes',
        'source_planner_sha256':receipt['planner_sha256'],'frozen_sha256':receipt['frozen_sha256']}
(folder/'assessment-obligations.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'passed':result['passed'],'total':result['total'],'failures':[{'id':r['id'],'checks':[k for k,v in r['checks'].items() if not v]} for r in rows if not r['passed']]},ensure_ascii=False))
