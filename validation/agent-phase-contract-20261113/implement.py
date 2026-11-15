from pathlib import Path
ROOT=Path('C:/Users/18483/AppData/Local/Temp/vra-timestep-reliability-20261108')
def edit(name,old,new):
 p=ROOT/name;s=p.read_text(encoding='utf-8');assert old in s,(name,old[:90]);p.write_text(s.replace(old,new,1),encoding='utf-8',newline='\n')
(ROOT/'backend/agent_actions.py').write_text('''"""Model-selected actions with no free answer channel; no engineering computation."""
import copy
import json
import uuid
from . import core


class ActionProtocolError(core.ValidationError):
    def __init__(self, reason, response):
        super().__init__('Structured action response rejected: ' + reason)
        self.response = response


def schema(tools):
    variants, definitions = [], {}
    for tool in tools:
        fn = tool['function']; name = fn['name']; args = copy.deepcopy(fn['parameters'])
        local = args.pop('$defs', {})
        def rewrite(value):
            if isinstance(value, dict):
                return {key: ('#/$defs/' + name + '__' + item.removeprefix('#/$defs/')
                             if key == '$ref' and isinstance(item, str) and item.startswith('#/$defs/')
                             else rewrite(item)) for key, item in value.items()}
            if isinstance(value, list):return [rewrite(item) for item in value]
            return value
        definitions.update({name + '__' + key: rewrite(value) for key, value in local.items()})
        variants.append({'type':'object','description':fn.get('description',''),
                         'properties':{'tool':{'type':'string','const':name},'arguments':rewrite(args)},
                         'required':['tool','arguments'],'additionalProperties':False})
    if not variants:raise core.ValidationError('No action offered; cannot request structured execution')
    result={'type':'object','properties':{'actions':{'type':'array','minItems':1,'maxItems':4,'items':{'oneOf':variants}}},
            'required':['actions'],'additionalProperties':False}
    if definitions:result['$defs']=definitions
    return result


def payload(messages, tools, *, strict):
    contract = schema(tools)
    instruction = ('Return one JSON object containing actions, each with tool and arguments. '
                   'Only choose offered actions, obey their schemas and the original request. '
                   'No prose, invented results, or completion claims. Read a selected fact before delivering it. '
                   'Use the offered clarification action when the requested metric is unresolved. '
                   'JSON action contract: ' + json.dumps(contract, ensure_ascii=False))
    result={'messages':[{'role':'system','content':instruction},*messages],
            'response_format':{'type':'json_schema','json_schema':{'name':'vra_actions','strict':True,'schema':contract}} if strict else {'type':'json_object'}}
    return result


def decode(message, tools):
    """Validate the transport envelope; invoke still validates every tool argument."""
    def reject(reason):raise ActionProtocolError(reason, message)
    if not isinstance(message,dict) or message.get('role')!='assistant' or message.get('tool_calls'):
        reject('expected a JSON action message, not native calls')
    content=message.get('content')
    if not isinstance(content,str) or len(content)>64000:reject('missing or oversized JSON content')
    def pairs(items):
        obj={}
        for key,value in items:
            if key in obj:raise ValueError('Duplicate key')
            obj[key]=value
        return obj
    def constant(_):raise ValueError('Nonfinite JSON')
    try:obj=json.loads(content,object_pairs_hook=pairs,parse_constant=constant)
    except (ValueError,RecursionError):reject('invalid, duplicate or nonfinite JSON')
    if not isinstance(obj,dict) or set(obj)!={'actions'}:reject('unexpected root fields')
    actions=obj['actions'];offered={t['function']['name']:t for t in tools}
    if not isinstance(actions,list) or not 1<=len(actions)<=4:reject('action count outside 1..4')
    calls=[]
    for action in actions:
        if not isinstance(action,dict) or set(action)!={'tool','arguments'}:reject('invalid action fields')
        if not isinstance(action['tool'],str) or action['tool'] not in offered:reject('unoffered action')
        if not isinstance(action['arguments'],dict):reject('arguments must be an object')
        calls.append({'id':'action_'+uuid.uuid4().hex,'type':'function','function':{
            'name':action['tool'],'arguments':json.dumps(action['arguments'],ensure_ascii=False,allow_nan=False)}})
    return {'role':'assistant','content':'','tool_calls':calls,'_raw_action_response':message}
''',encoding='utf-8')
for name in ('backend/local_model.py','backend/gateway.py'):
 edit(name,'from . import core','from . import agent_actions\nfrom . import core')
 edit(name,'def complete(self, messages, tools, *, transport=None):','def complete(self, messages, tools, *, transport=None, response_mode="tools"):')
 if name.endswith('local_model.py'):
  edit(name,"        try:\n            raw = json.dumps(payload", "        if response_mode not in {'tools','actions'}:raise core.ValidationError('Unknown model response mode')\n        if response_mode=='actions':\n            payload.pop('tools');payload.pop('tool_choice')\n            payload.update(agent_actions.payload(messages,tools,strict=True))\n        try:\n            raw = json.dumps(payload")
 else:
  edit(name,"                with client.stream('POST', self.endpoint", "                if response_mode not in {'tools','actions'}:raise core.ValidationError('Unknown model response mode')\n                if response_mode=='actions':\n                    payload.pop('tools');payload.pop('tool_choice')\n                    payload.update(agent_actions.payload(messages,tools,strict=False))\n                with client.stream('POST', self.endpoint")
 edit(name,"            return {k: message[k] for k in ('role', 'content', 'tool_calls') if k in message}", "            if response_mode=='actions':return agent_actions.decode(message,tools)\n            return {k: message[k] for k in ('role', 'content', 'tool_calls') if k in message}")
 # Preserve typed protocol errors rather than swallowing their raw audit response.
 edit(name,'        except ModelServiceUnavailable:', '        except agent_actions.ActionProtocolError:\n            raise\n        except ModelServiceUnavailable:')

(ROOT/'backend/agent_selections.py').write_text('''"""Select facts actually read in this task; materialize exact source fields in application."""
import copy
from typing import Literal
from pydantic import Field, model_validator
from .schema import Contract
from . import core
from .agent_semantics import Statement, NumericDelivery, inspection, model_projection


class Selection(Contract):
    kind: Literal['thermal','lifecycle','cost','engineering','schedule','operation','scenario','enduse','utility']
    record_id: str = Field(pattern=r'^(?:thermal|lifecycle|cost|engineering|schedule|operation|scenario|enduse|utility)_[a-f0-9]{32}$')
    record_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    fact_keys: list[str] = Field(min_length=1,max_length=12,description='Select only requested facts from the current selected read. Application copies exact values/context and rechecks the source.')
    finish: bool = False

    @model_validator(mode='after')
    def unique(self):
        if not self.record_id.startswith(self.kind+'_') or len(set(self.fact_keys))!=len(self.fact_keys):
            raise ValueError('Mismatched kind or duplicate fact keys')
        return self


def tool_schema(tool, candidates):
    result=copy.deepcopy(tool);variants=[]
    for spec,source in candidates:
        facts=model_projection(source,spec.kind)['explanation_facts']
        if not facts:continue
        item=Selection.model_json_schema();props=item['properties']
        for key,value in [('kind',spec.kind),('record_id',source[spec.record_key]),('record_hash',source['hash'])]:
            props[key]={'type':'string','const':value}
        props['fact_keys']['items']={'type':'string','enum':[f['fact'] for f in facts]}
        item['required']=list(dict.fromkeys(item['required']+['finish']))
        variants.append(item)
    if not variants:raise core.ValidationError('Cannot offer fact selection without a selected numeric read')
    result['function']['description']='Select requested fact_keys from an actual read, with its record_id/kind/hash. Do not copy numbers or context. Application constructs all fields from that read and rechecks current source; stale results remain refused.'
    result['function']['parameters']={'type':'object','properties':{'delivery':{'oneOf':variants}},'required':['delivery'],'additionalProperties':False}
    return result


def materialize(record, raw):
    selection=Selection.model_validate(raw);spec=inspection(selection.kind)
    matches=[(i,e['result']) for i,e in enumerate(record['events']) if e['tool']==spec.read_tool and e['status']=='succeeded'
             and e.get('result',{}).get(spec.record_key)==selection.record_id]
    if not matches:raise core.ValidationError('Read this record in the current task before selecting facts')
    index,source=matches[-1]
    if source['hash']!=selection.record_hash:raise core.ValidationError('Selection must use the latest read receipt')
    available={f['fact']:f for f in model_projection(source,selection.kind)['explanation_facts']}
    if not set(selection.fact_keys)<=set(available):raise core.ValidationError('Selected facts have not been numerically read; a catalog is not a numeric receipt')
    numeric=NumericDelivery(kind=selection.kind,record_id=selection.record_id,record_hash=selection.record_hash,
        statements=[{field:available[key][field] for field in Statement.model_fields} for key in selection.fact_keys],finish=selection.finish)
    return numeric.model_dump(mode='json'),{'origin':'application_from_current_task_read','read_event_index':index,
        'record_id':selection.record_id,'record_hash':selection.record_hash,'fact_keys':selection.fact_keys,'current_source_recheck_required':True}
''',encoding='utf-8')
edit('backend/agent.py','from . import agent_outputs','from . import agent_outputs, agent_actions, agent_selections')
edit('backend/agent.py',"    'requested_availability': ('request_keys','finish'),", "    'requested_defer': ('request_keys',),\n    'requested_availability': ('request_keys','finish'),")
edit('backend/agent.py',"    'professional_deliver': '先读取", "    'requested_defer': '当前请求所需指标不明确时，提交未完成的request_keys等待用户澄清。只表明模型不确定，不证明资料缺失或应用不支持，不产生数值、不计完成。不能用于用户已明确勾选的指标。',\n    'professional_deliver': '先读取")
edit('backend/agent.py',"{'requested_output_plan', 'requested_availability', 'professional_review'}", "{'requested_output_plan', 'requested_availability', 'professional_review', 'requested_defer'}")
edit('backend/agent.py',"            offered = {'project_get'}", "            offered = {'project_get','requested_defer'}")
edit('backend/agent.py',"            choices = {}\n", "            deferrable = [r.request_key for r in body.read_requests if r.request_key in waiting and not r.output_contract]\n            if not deferrable:available.discard('requested_defer')\n            choices = {}\n")
edit('backend/agent.py',"                if name == 'capability_lookup':\n                    parameters['required']", "                if name == 'requested_defer':\n                    parameters['properties']['request_keys']={'type':'array','minItems':1,'maxItems':len(deferrable),'uniqueItems':True,'items':{'type':'string','enum':deferrable}}\n                    parameters['required']=['request_keys']\n                if name == 'capability_lookup':\n                    parameters['required']")
edit('backend/agent.py',"                    parameters['required'] = ['limitation' if limited else 'delivery']", "                    parameters['required'] = ['limitation' if limited else 'delivery']\n                    if not limited and body.read_requests:\n                        replacement=agent_selections.tool_schema(tool,candidates)\n                        tool.clear();tool.update(replacement)")
# Check actual variable used by the existing loop before running this script.
edit('backend/agent.py',"                canonical = ToolArgs.model_validate(args).model_dump(mode='json', include=set(TOOL_FIELDS[name]))", "                if name=='professional_deliver' and isinstance(args.get('delivery'),dict) and 'fact_keys' in args['delivery']:\n                    numeric,receipt=agent_selections.materialize(record,args['delivery'])\n                    event['selection_receipt']=receipt\n                    args={'delivery':numeric}\n                canonical = ToolArgs.model_validate(args).model_dump(mode='json', include=set(TOOL_FIELDS[name]))")
edit('backend/agent.py',"                if name=='requested_availability':", "                if name=='requested_defer':\n                    keys=canonical['request_keys'] or []\n                    allowed={r.request_key for r in body.read_requests if r.request_key in requested_scopes.pending(record) and not r.output_contract}\n                    if not keys or len(set(keys))!=len(keys) or not set(keys)<=allowed:raise core.ValidationError('Defer only pending scopes without explicit user-selected outputs')\n                    record['read_deferrals']=list(dict.fromkeys(record.get('read_deferrals',[])+keys))\n                    result={'status':'needs_clarification','request_keys':keys,'finish':False,'notice':'Model uncertainty only; no numeric result or capability conclusion.'}\n                    event.update(status='succeeded',result=result,result_hash=core.hash_json(result));return result\n                if name=='requested_availability':")
edit('backend/agent.py',"                        raw_message=gateway.complete(messages,turn_tools())", "                        current_tools=turn_tools()\n                        if body.read_requests:\n                            provider_event['response_protocol']='structured_actions'\n                            raw_message=gateway.complete(messages,current_tools,response_mode='actions')\n                        else:raw_message=gateway.complete(messages,current_tools)\n                        raw_message=dict(raw_message)\n                        if '_raw_action_response' in raw_message:provider_event['raw_action_response']=raw_message.pop('_raw_action_response')")
edit('backend/agent.py',"                    except model_recovery.ModelServiceUnavailable as exc:", "                    except agent_actions.ActionProtocolError as exc:\n                        provider_event.update(status='failed',error=str(exc),raw_action_response=exc.response)\n                        if record['recovery_attempts']>=2 or turn>=4:raise\n                        record['recovery_attempts']+=1\n                        messages.append({'role':'user','content':'Response did not match the offered JSON action contract; no action executed. Select an offered read/delivery/clarification action. Budget and permissions unchanged.'})\n                        continue\n                    except model_recovery.ModelServiceUnavailable as exc:")
edit('backend/agent.py',"                    if body.read_requests and body.infer_outputs and record.get('output_plan') and not batch_failed", "                    if record.get('read_deferrals') and not batch_failed and not requested_scopes.pending(record):\n                        record['termination']={'reason':'read_scopes_deferred','model_declared_finished':False,'pending_request_keys':[]}\n                        break\n                    if body.read_requests and body.infer_outputs and record.get('output_plan') and not batch_failed")
edit('backend/agent_requests.py',"    unresolved={i['request_key']", "    unresolved=set(record.get('read_deferrals',[])) | {i['request_key']")
edit('backend/agent_requests.py',"        if wanted.get('clarification_question'):", "        if wanted.get('clarification_question') or r['request_key'] in record.get('read_deferrals',[]):")
edit('backend/agent_requests.py',"    return agent_outputs.attach(answer, record)", "    answer=agent_outputs.attach(answer, record)\n    if record.get('read_deferrals'):\n        answer['task_completion']='partial' if answer.get('checked_statements') else 'incomplete'\n        answer['read_deferrals']=[{'request_key':key,'state':'needs_clarification','notice':'模型尚不能确定所需指标，请明确指标。不是资料缺失、应用不支持或任务完成的证明。'} for key in record['read_deferrals']]\n        answer['summary']='仍有读取目标需要明确指标；已交付部分单独核验，未明确项未作数值交付。'\n    return answer")
print('Actions and read receipt implementation written')
