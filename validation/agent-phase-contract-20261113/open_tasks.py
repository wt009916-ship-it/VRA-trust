exec(open('D:/稀土agent-稀土制暖全流程/outputs/agent-phase-20261113/implement.py',encoding='utf-8').read().split("(ROOT/'backend/agent_actions.py')")[0])
edit('backend/agent.py',"        offered -= {'requested_availability', 'requested_output_plan', 'professional_review', 'requested_defer'}", "        offered -= {'requested_availability', 'requested_output_plan', 'professional_review'}\n        if body.objective!='open_ended':offered.discard('requested_defer')")
edit('backend/agent.py',"            if not deferrable:available.discard('requested_defer')", "            if body.read_requests and not deferrable:available.discard('requested_defer')")
edit('backend/agent.py',"                    parameters['properties']['request_keys']={'type':'array','minItems':1,'maxItems':len(deferrable),'uniqueItems':True,'items':{'type':'string','enum':deferrable}}\n                    parameters['required']=['request_keys']", "                    if body.read_requests:\n                        parameters['properties']['request_keys']={'type':'array','minItems':1,'maxItems':len(deferrable),'uniqueItems':True,'items':{'type':'string','enum':deferrable}}\n                        parameters['required']=['request_keys']\n                    else:\n                        parameters['properties']['request_keys']={'type':'null'}\n                        parameters['required']=[]")
edit('backend/agent.py',"                    if not limited and body.read_requests:","                    if not limited and body.objective=='open_ended':")
edit('backend/agent.py',"                if name=='requested_defer':\n                    keys=canonical['request_keys'] or []", "                if name=='requested_defer':\n                    if not body.read_requests:\n                        if canonical['request_keys'] is not None:raise core.ValidationError('No declared request keys in this task')\n                        record['question_deferral']={'question_hash':core.hash_json(record['question']),'origin':'model_uncertainty'}\n                        result={'status':'needs_clarification','finish':True,'notice':'Question needs clarification; no numeric result, unsupported-capability conclusion or completion claim.'}\n                        event.update(status='succeeded',result=result,result_hash=core.hash_json(result));return result\n                    keys=canonical['request_keys'] or []")
edit('backend/agent.py',"                        if body.read_requests:\n                            messages[0]['content'] +=", "                        if body.objective=='open_ended':\n                            messages[0]['content'] +=")
edit('backend/agent.py',"                        if body.read_requests:\n                            provider_event['response_protocol']='structured_actions'", "                        if body.objective=='open_ended':\n                            provider_event['response_protocol']='structured_actions'")
edit('backend/agent.py',"                        if call['function']['name']=='requested_availability' and result.get('status')=='verified':", "                        if call['function']['name']=='requested_defer':finish_requested |= result['finish']\n                        if call['function']['name']=='requested_availability' and result.get('status')=='verified':")
edit('backend/agent.py',"当前请求所需指标不明确时，提交未完成的request_keys等待用户澄清。", "当前请求所需指标不明确时，提交未完成的request_keys等待用户澄清；没有声明读取范围时省略request_keys，标记整个自由问题需澄清。")
edit('backend/agent_requests.py',"    if not record.get('read_requests'):return answer", "    if record.get('question_deferral'):\n        answer={**answer,'task_completion':'partial' if answer.get('checked_statements') else 'incomplete',\n                'question_deferral':record['question_deferral'],'summary':'模型仍需明确问题中的目标或指标；未将不确定性当成资料缺失、能力结论或任务完成。'}\n    if not record.get('read_requests'):return answer")
with (ROOT/'tests/test_agent_actions.py').open('a',encoding='utf-8') as f:
 f.write('''

def test_unscoped_open_task_uses_actions_and_has_honest_deferral(client,monkeypatch):
    pid=create_project(client)['project_id'];a=client.app.state.agent
    scripted(a,monkeypatch,[tool('requested_defer',{})])
    original=a.gateway.complete;policies=[]
    def capture(messages,tools,**options):
        policies.append(options);return original(messages,tools,**options)
    monkeypatch.setattr(a.gateway,'complete',capture)
    t=a.start(pid,Chat(message='请帮我处理那个尚未指明的指标',mode='provider'),background=False)
    assert t['status']=='succeeded',t.get('error')
    assert policies==[{'response_mode':'actions'}]
    assert t['answer']['task_completion']=='incomplete' and t['answer']['question_deferral']['origin']=='model_uncertainty'


def test_open_task_receipt_selection_not_limited_to_declared_read_form(client,monkeypatch):
    pid=create_project(client)['project_id'];a=client.app.state.agent;r=create_record(client,pid,'thermal')
    scripted(a,monkeypatch,[tool('thermal_read',{'thermal_id':r['thermal_id']}),tool('professional_deliver',{'delivery':selected(r)})])
    t=a.start(pid,Chat(message='Read total R from '+r['thermal_id'],mode='provider'),background=False)
    assert t['status']=='succeeded',t.get('error')
    assert t['answer']['checked_statements'][0]['facts'][0]['value']=='1.97'
    assert any(e.get('selection_receipt') for e in t['events'])
''')
print('Structured actions and receipt selection now cover general open-ended tasks, not only declared read scopes')
