"""Run an explicitly enabled paid provider on a COPY of verified public meter projects.

Tests task execution and tool evidence; model prose still needs engineering review.
Never use a customer/formal runtime as --dataset-runtime.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import time


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset-runtime',type=Path,required=True)
    parser.add_argument('--provider-config',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--cases',type=int,default=10,choices=range(1,21))
    parser.add_argument('--partition',choices=['development','holdout'],default='development')
    parser.add_argument('--execute-provider',action='store_true',required=True,
                        help='Explicitly permit billable provider requests on public test data')
    args=parser.parse_args();repo=Path(__file__).resolve().parents[1]
    sys.path.insert(0,str(repo));source=args.dataset_runtime.resolve();out=args.output_dir.resolve()
    if source.name!='runtime' or not (source.parent/'execution.json').is_file() or not (source.parent/'completed.json').is_file():
        raise SystemExit('Use an isolated output from verify_public_meter_data.py, with execution/completion manifests')
    verification=json.loads((source.parent/'results.json').read_text(encoding='utf-8'))
    if verification.get('distinct_bdg2_buildings')!=20:raise SystemExit('Verified20-building input required')
    config=json.loads(args.provider_config.read_text(encoding='utf-8'))
    if not config.get('enabled') or not config.get('sealed_key'):raise SystemExit('Saved, enabled provider with encrypted key required on this Windows host')
    out.mkdir(parents=True,exist_ok=False);runtime=out/'runtime';shutil.copytree(source,runtime)
    (runtime/'private').mkdir(exist_ok=True);shutil.copyfile(args.provider_config,runtime/'private/provider.json')
    os.environ['VRA_DATA_DIR']=str(runtime)
    from backend import core
    from backend.api import create_app
    from backend.agent import Chat
    app=create_app(runtime,start_worker=False);agent=app.state.agent;store=agent.store
    projects={p['name'].split(' / ')[-1]:p['project_id'] for p in store.list('project')}
    records=verification['bdg2'];ordered=sorted(records,key=lambda r:(r['summary']['valid_rows'],r['building_id']))
    # Include genuinely missing and complete series, selected deterministically before model calls.
    selected=ordered[:5]+[r for r in ordered if r['summary']['eligible_for_comparison']][:5]
    if args.partition=='holdout':selected=[r for r in ordered if r not in selected]
    elif args.cases>10:selected+=[r for r in ordered if r not in selected]
    if args.cases>len(selected):raise SystemExit('Requested more cases than this partition contains')
    results=[]
    execution={'started_at':core.now(),'provider':agent.gateway.public()['model'],
        'dataset_execution_sha256':core.sha(source.parent/'execution.json'),
        'source_code_sha256':{name:core.sha(repo/name) for name in ['backend/agent.py','backend/agent_context.py','backend/agent_policy.py','backend/gateway.py']},
        'model_weight_training':False,'scope':'Public measured-series task execution, not thermal-model or field-calibration accuracy',
        'partition':args.partition,'maximum_cases':args.cases,'maximum_iterations_per_case':5,'compute_authorized':False,'documents_authorized':False}
    core.write_json(out/'execution.json',execution)
    for row in selected[:args.cases]:
        bid=row['building_id'];pid=projects[bid]
        prompt=f'请检查本项目{bid}的实测电表数据：有效行与缺测各多少，来源是什么，目前能否用于完整时段比较或声称设备已完成现场校准？给出下一步行动。请调用measurement_audit自行复核，不要只复述初始摘要。'
        start=time.perf_counter();task=agent.start(pid,Chat(message=prompt,mode='provider',task='measurements'),background=False)
        core.write_json(out/(bid+'.private-task.json'),task)
        events=task['events'];audits=[e for e in events if e['tool']=='measurement_audit' and e['status']=='succeeded']
        current=[s for e in audits for s in e['result']['series'] if s['options'].get('role')=='observed' and s['current']]
        exact=bool(current) and all(s['summary']==row['summary'] for s in current)
        models=[e for e in events if e['tool']=='llm.request']
        result={'building_id':bid,'source_sha256':row['original_source_sha256'],'status':task['status'],
            'explanation_status':task['explanation_status'],'error':task.get('explanation_error') or task.get('error'),
            'expected_valid_rows':row['summary']['valid_rows'],'expected_issues':row['summary']['issues'],
            'current_tool_summary_matches_source_acceptance':exact,'provider_requests':len(models),
            'provider_tool_calls_returned':sum(e.get('result',{}).get('tool_calls_returned',0) for e in models),
            'model_selected_tools':[e['tool'] for e in events if e.get('origin')=='model'],
            'usage':[e.get('request_info',{}).get('usage') for e in models],
            'computed_jobs_added':len(store.jobs(pid)),
            'seconds':time.perf_counter()-start,'commentary':task.get('llm_commentary'),
            'semantic_engineering_accuracy':'requires_review','calibrated':False}
        results.append(result);core.write_json(out/'results.json',results)
        print(json.dumps({k:result[k] for k in ['building_id','status','explanation_status','current_tool_summary_matches_source_acceptance','provider_requests','model_selected_tools','seconds']},ensure_ascii=False),flush=True)
        if result['error'] and any(code in result['error'] for code in ['HTTP 401','HTTP 402','HTTP 403']):
            core.write_json(out/'stopped.json',{'reason':'Provider account/authentication rejected; stopped before remaining cases','completed_cases':len(results)})
            break
    current={name:core.sha(repo/name) for name in execution['source_code_sha256']}
    if current!=execution['source_code_sha256']:raise SystemExit('Code changed during evaluation; output is not a frozen-code acceptance')
    core.write_json(out/'completed.json',{'completed_at':core.now(),'cases':len(results),'execution_code_unchanged':True})


if __name__=='__main__':main()
