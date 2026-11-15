exec(open('D:/稀土agent-稀土制暖全流程/outputs/agent-phase-20261113/implement.py',encoding='utf-8').read().split("(ROOT/'backend/agent_actions.py')")[0])
edit('backend/agent_actions.py','import uuid\n','import uuid\nfrom jsonschema import Draft202012Validator, ValidationError as SchemaValidationError\n')
edit('backend/agent_actions.py',"    actions=obj['actions'];offered", "    try:Draft202012Validator(schema(tools)).validate(obj)\n    except SchemaValidationError:reject('action arguments violate the offered schema')\n    actions=obj['actions'];offered")
with (ROOT/'backend/requirements.txt').open('a',encoding='utf-8') as f:f.write('jsonschema==4.25.1\n')
# Scope is checked on the current receipt as well as the model-facing schema.
edit('backend/agent_selections.py','from . import core\n','from . import core, agent_outputs\n')
edit('backend/agent_selections.py','def tool_schema(tool, candidates):','def tool_schema(tool, candidates, record):')
edit('backend/agent_selections.py',"        facts=model_projection(source,spec.kind)['explanation_facts']", "        facts=model_projection(source,spec.kind)['explanation_facts']\n        request=next((r for r in record.get('read_requests',[]) if r['record_id']==source[spec.record_key]),None)\n        wanted=agent_outputs.requirement(record,request['request_key']) if request else None\n        if wanted:facts=[f for f in facts if f['fact'] in wanted['fact_keys']]")
edit('backend/agent_selections.py',"    available={f['fact']", "    request=next((r for r in record.get('read_requests',[]) if r['record_id']==selection.record_id),None)\n    wanted=agent_outputs.requirement(record,request['request_key']) if request else None\n    if wanted and not set(selection.fact_keys)<=set(wanted['fact_keys']):raise core.ValidationError('Selected facts are outside the frozen requested metrics')\n    available={f['fact']")
edit('backend/agent.py','agent_selections.tool_schema(tool,candidates)','agent_selections.tool_schema(tool,candidates,record)')
# Model pending hints must describe the offered selector, not the legacy numeric API.
edit('backend/agent_requests.py',"required_fields=['delivery.statements'], available_facts=facts,", "required_fields=['delivery.fact_keys'], available_fact_keys=[f['fact'] for f in facts],")
edit('backend/agent.py',"                        if len(json.dumps(messages, ensure_ascii=False)) > 64000:", "                        if body.read_requests:\n                            messages[0]['content'] += '\\n本轮professional_deliver使用fact_keys选择当前已经数值读取的事实；由应用复制所有数值及上下文并重验来源。不自行抄写或修改statements。未确定指标时用requested_defer标记待澄清，不声称完成。'\n                        if len(json.dumps(messages, ensure_ascii=False)) > 64000:")
print('Pinned observed jsonschema4.25.1; full offered-schema validation and receipt metric scope wired')
