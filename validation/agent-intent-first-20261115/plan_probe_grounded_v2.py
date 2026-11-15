"""First-stage planning probe only: no engineering tools, writes or task-completion claims."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time

import httpx

BASE=Path(__file__).parent
ROOT=Path('D:/稀土agent-稀土制暖全流程/.codex_work/vra-resource-leveling-20261115')
PRIOR=BASE.parent/'agent-integrated-20261115/holdout-v1'
EXE=Path('E:/VRA-local-model-20261106/runtime/llama-server.exe')
MODEL=Path('C:/Users/18483/AppData/Local/Temp/vra-qwen35-9b-20261108/Qwen3.5-9B-Q4_K_M.gguf')
sys.path.insert(0,str(ROOT))
from backend import agent_task_plan, agent_actions, agent_history

def save(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def main():
    out=BASE/'probe-grounded-v2';out.mkdir(exist_ok=False)
    frozen=json.loads((PRIOR/'frozen.json').read_text(encoding='utf-8'));cases=[]
    for source in frozen['tasks']:
        task=json.loads((PRIOR/(source['id']+'-task.json')).read_text(encoding='utf-8'))
        body=source['body']
        history=json.loads(json.dumps(task['context_snapshot']))
        for turn in history:
            matches=[]
            for prior_path in PRIOR.glob('H*-task.json'):
                prior_task=json.loads(prior_path.read_text(encoding='utf-8'))
                if prior_task['agent_id']==turn['agent_id']:matches.append(prior_task)
            if matches:
                assert len(matches)==1 and matches[0].get('answer_checked_at')
                turn['reference_states']=agent_history.references(matches[0])
        cases.append({'id':source['id'],'classification':'Known question regression with grounded outputs and replayed nonnumeric reference checks; not unseen',
            'context':agent_task_plan.context(body['message'],history,allow_compute=body['allow_compute'],calculation_plans=body.get('calculation_plans',[])),
            'original_expected':source['expected']})
    ident='thermal_'+'d'*32
    for key,question,expected in [
        ('I07',f'本轮不要新建计算，即使已开启计算权限。只读取{ident}的总R，不要U。',{'operation':'read_record','record_id':ident,'fact_keys':['total_resistance_m2k_w']}),
        ('I08',f'请把构造{ident}的总R当成传热系数U，只给一个结果。',{'operation':'clarify_request','reason':'contradictory_request'})]:
        cases.append({'id':key,'classification':'Known planner-only regression; no actual professional execution',
            'context':agent_task_plan.context(question,allow_compute=True),'expected':expected})
    save(out/'frozen.json',{'cases':cases,'ids':frozen['ids'],
        'scope':'First-stage contract selection only. No professional tool execution and no overall score.'})
    receipt={'completed':False,'results':[],'model_sha256':sha(MODEL),'runtime_sha256':sha(EXE),
        'planner_sha256':sha(ROOT/'backend/agent_task_plan.py'),'frozen_sha256':sha(out/'frozen.json')}
    assert receipt['model_sha256']=='03b74727a860a56338e042c4420bb3f04b2fec5734175f4cb9fa853daf52b7e8'
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    token=secrets.token_urlsafe(36)
    env={k:v for k,v in os.environ.items() if k.upper() in {'SYSTEMROOT','WINDIR','TEMP','TMP','COMSPEC','SYSTEMDRIVE'}}
    env.update(PATH=str(EXE.parent)+os.pathsep+str(Path(os.environ['SystemRoot'])/'System32'),LLAMA_API_KEY=token)
    args=[str(EXE),'-m',str(MODEL),'--host','127.0.0.1','--port',str(port),'--alias','vra-nine-b-tools','-c','16384','-np','1','-t','4','-ngl','99','--fit','off','--cache-ram','0','--no-context-shift','--offline','--no-webui','--no-agent','--no-webui-mcp-proxy','--no-slots','--jinja','--reasoning','off','--timeout','120']
    receipt['arguments']=args
    receipt['history_projection_sha256']=sha(ROOT/'backend/agent_history.py')
    receipt['history_basis']='Replayed original H task views with answer_checked_at; not new project execution'
    process=None
    try:
        with (out/'model.log').open('xb') as log:
            process=subprocess.Popen(args,cwd=EXE.parent,env=env,stdout=log,stderr=log,stdin=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
            with httpx.Client(base_url=f'http://127.0.0.1:{port}',timeout=120,trust_env=False) as client:
                for _ in range(120):
                    assert process.poll() is None
                    try:
                        if client.get('/health',timeout=2).status_code==200:break
                    except httpx.HTTPError:pass
                    time.sleep(1)
                else:raise TimeoutError('Model startup')
                assert client.post('/v1/chat/completions',json={}).status_code==401
                for case in cases:
                    offered=[agent_task_plan.tool(case['context'])]
                    messages=[{'role':'system','content':'先理解原问题，再读取资料。逐项引用本轮原问题的连续短语；数值指标和解释分别绑定短语。来源状态及必要边界由应用固定核验，不为履行这些职责扩展用户输出。历史reference_states可区分刚才有效数值与失效说明，但不继承旧值或权限。现在只能提交task_plan，不执行工程工具。逐项保留用户的读取、新建、解释、比较和排除要求；没有当前参数计划或授权时仍保留create_calculation，由应用说明缺口。原目标明确但来源缺失/失效不是澄清目标。仅选择所问字段，禁止用阶段量代替总量或用旧记录代替新建。'},
                        {'role':'user','content':json.dumps(case['context'],ensure_ascii=False)}]
                    payload={'model':'vra-nine-b-tools','max_tokens':1400,'temperature':0,'stream':False,'chat_template_kwargs':{'enable_thinking':False},**agent_actions.payload(messages,offered,strict=True)}
                    save(out/(case['id']+'-request.json'),payload);started=time.monotonic()
                    response=client.post('/v1/chat/completions',json=payload,headers={'Authorization':'Bearer '+token})
                    raw=response.json();save(out/(case['id']+'-response.json'),raw)
                    row={'id':case['id'],'http_status':response.status_code,'seconds':round(time.monotonic()-started,3),'completed':False}
                    try:
                        response.raise_for_status();assert raw['choices'][0]['finish_reason']=='stop'
                        decoded=agent_actions.decode(raw['choices'][0]['message'],offered)
                        calls=decoded['tool_calls'];assert len(calls)==1 and calls[0]['function']['name']=='task_plan'
                        plan=agent_task_plan.freeze(json.loads(calls[0]['function']['arguments']),case['context'])
                        save(out/(case['id']+'-plan.json'),plan);row.update(completed=True,usage=raw.get('usage'),intent_assessment='pending')
                    except Exception as exc:row['error']=type(exc).__name__+': '+str(exc)
                    receipt['results'].append(row);save(out/'receipt.json',receipt);print(json.dumps(row,ensure_ascii=False),flush=True)
                receipt['completed']=True
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:process.wait(timeout=15)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
        receipt['process_stopped']=process is None or process.poll() is not None
        save(out/'receipt.json',receipt)

if __name__=='__main__':main()
