"""Real same-input Qwen availability checks through the production Agent and Gateway.

Requires the isolated benchmark_agent_server bridge and original Golden EPW.
No model response or engineering result is fabricated. Availability is distinct
from correctness of the explanation, which remains explicitly unverified.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time

import httpx


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--epw',type=Path,required=True)
    parser.add_argument('--base',default='http://127.0.0.1:8770')
    parser.add_argument('--count',type=int,choices=range(1,6),default=5)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    trace=[]
    def save(name,value):
        (args.output/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    with httpx.Client(base_url=args.base,timeout=180) as client:
        auth=client.post('/api/auth/register',json={'username':'qwen_repair','display_name':'Isolated real-model recovery acceptance',
            'password':'Qwen-repair-acceptance-2026!'})
        auth.raise_for_status();client.headers['X-CSRF-Token']=auth.json()['csrf_token']
        config=client.put('/api/developer/provider',json={'enabled':True,'model':'qwen3-benchmark',
            'endpoint':'http://127.0.0.1:8791/v1/chat/completions','request_timeout_s':120,
            'max_output_tokens':1000,'local_qwen_no_thinking':True})
        config.raise_for_status();save('configuration.json',config.json())
        p=client.post('/api/projects',json={'name':'Real Qwen repair: same Golden input, no building model',
            'building':{'use':'software test','location':'Golden reference only','region':'TEST','area_m2':80.}})
        p.raise_for_status();base='/api/projects/'+p.json()['project_id']
        raw=args.epw.read_bytes();digest=hashlib.sha256(raw).hexdigest()
        f=client.post(base+'/files',files={'file':(args.epw.name,raw)});f.raise_for_status()
        weather=client.post(base+'/weather/epw',json={'file_id':f.json()['file_id']});weather.raise_for_status()
        questions=[
            ('auto','核对天气、空间模型、仿真状态和资料来源，不提交计算。'),
            ('auto','同时检查天气、IFC模型、仿真状态与资料来源，请逐项说明；禁止启动计算。'),
            ('weather','核对天气文件站点、全年记录数、年平均气温、HDD18、CDD26以及来源SHA256。'),
            ('auto','检查空间模型和资料缺口，目前能否运行仿真？不允许启动计算。'),
            ('auto','再次核对天气、模型、仿真状态、资料来源。不提交计算，也不补造能耗。')]
        for number,(kind,question) in enumerate(questions[:args.count],1):
            start=time.monotonic()
            r=client.post(base+'/agent/chat',json={'message':question,'mode':'provider','task':kind,'allow_compute':False})
            r.raise_for_status();task=r.json()
            while task['status']=='running' and time.monotonic()-start<220:
                time.sleep(.3)
                r=client.get(base+'/agent/'+task['agent_id']);r.raise_for_status();task=r.json()
            save(f'task-{number}.json',task)
            provider=[e for e in task['events'] if e['tool']=='llm.request']
            row={'case':number,'question':question,'status':task['status'],'tool_status':task['tool_status'],
                 'explanation_status':task['explanation_status'],'seconds':round(time.monotonic()-start,3),
                 'error':task.get('explanation_error'),'provider_events':provider,
                 'source_sha256':digest,'engine_jobs_created':len(client.get(base+'/runs').json())}
            if kind=='weather' or any(t=='weather' for t in task.get('resolved_tasks',[])):
                assert task['answer']['weather'][0]['source_hash']==digest
                assert task['answer']['weather'][0]['annual']==weather.json()['annual']
            assert row['engine_jobs_created']==0
            trace.append(row);save('results.json',trace)
            print(number,task['status'],task['explanation_status'],row['seconds'],flush=True)
        assert all(r['tool_status']=='succeeded' for r in trace)
        assert all(r['explanation_status']=='available' for r in trace), 'At least one actual model request still failed or was truncated; see traces'
        print('REAL_QWEN_REQUESTS_PASSED',len(trace),flush=True)


if __name__=='__main__':
    main()
