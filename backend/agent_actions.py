"""Model-selected actions with no free answer channel; no engineering computation."""
import copy
import json
import uuid
from jsonschema import Draft202012Validator, ValidationError as SchemaValidationError
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
    if isinstance(message,dict):message={k:message[k] for k in ('role','content','tool_calls') if k in message}
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
    try:Draft202012Validator(schema(tools)).validate(obj)
    except SchemaValidationError:reject('action arguments violate the offered schema')
    actions=obj['actions'];offered={t['function']['name']:t for t in tools}
    if not isinstance(actions,list) or not 1<=len(actions)<=4:reject('action count outside 1..4')
    calls=[]
    for action in actions:
        if not isinstance(action,dict) or set(action)!={'tool','arguments'}:reject('invalid action fields')
        if not isinstance(action['tool'],str) or action['tool'] not in offered:reject('unoffered action')
        if not isinstance(action['arguments'],dict):reject('arguments must be an object')
        try:encoded=json.dumps(action['arguments'],ensure_ascii=False,allow_nan=False)
        except (ValueError,RecursionError):reject('invalid numeric or nested arguments')
        calls.append({'id':'action_'+uuid.uuid4().hex,'type':'function','function':{
            'name':action['tool'],'arguments':encoded}})
    return {'role':'assistant','content':'','tool_calls':calls,'_raw_action_response':message}
