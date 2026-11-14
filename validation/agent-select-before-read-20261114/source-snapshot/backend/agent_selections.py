"""Select facts actually read in this task; materialize exact source fields in application."""
import copy
from typing import Literal
from pydantic import Field, model_validator
from .schema import Contract
from . import core, agent_outputs
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


def tool_schema(tool, candidates, record):
    result=copy.deepcopy(tool);variants=[]
    for spec,source in candidates:
        facts=model_projection(source,spec.kind)['explanation_facts']
        request=next((r for r in record.get('read_requests',[]) if r['record_id']==source[spec.record_key]),None)
        wanted=agent_outputs.requirement(record,request['request_key']) if request else None
        if wanted:facts=[f for f in facts if f['fact'] in wanted['fact_keys']]
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
    request=next((r for r in record.get('read_requests',[]) if r['record_id']==selection.record_id),None)
    wanted=agent_outputs.requirement(record,request['request_key']) if request else None
    if wanted and not set(selection.fact_keys)<=set(wanted['fact_keys']):raise core.ValidationError('Selected facts are outside the frozen requested metrics')
    available={f['fact']:f for f in model_projection(source,selection.kind)['explanation_facts']}
    if not set(selection.fact_keys)<=set(available):raise core.ValidationError('Selected facts have not been numerically read; a catalog is not a numeric receipt')
    numeric=NumericDelivery(kind=selection.kind,record_id=selection.record_id,record_hash=selection.record_hash,
        statements=[{field:available[key][field] for field in Statement.model_fields} for key in selection.fact_keys],finish=selection.finish)
    return numeric.model_dump(mode='json'),{'origin':'application_from_current_task_read','read_event_index':index,
        'record_id':selection.record_id,'record_hash':selection.record_hash,'fact_keys':selection.fact_keys,'current_source_recheck_required':True}
