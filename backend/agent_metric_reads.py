"""Current task read selections: identifiers, observed catalogs and bounded batches."""
import copy
import re
from pydantic import Field, model_validator
from .schema import Contract
from . import core, agent_energy, agent_outputs
from .agent_semantics import inspection, model_projection

KINDS='thermal|lifecycle|cost|engineering|schedule|operation|scenario|enduse|utility'
ID_PATTERN=r'(?:'+KINDS+r')_[a-f0-9]{32}'


def identifiers(text, kind=None):
    pattern=(re.escape(kind)+r'_[a-f0-9]{32}') if kind else ID_PATTERN
    return re.findall(r'(?<![A-Za-z0-9_])'+pattern+r'(?![A-Za-z0-9_])',text)


class ReadSelection(Contract):
    record_id: str = Field(pattern='^'+ID_PATTERN+'$')
    fact_keys: list[str] | None = Field(default=None,min_length=1,max_length=12)

    @model_validator(mode='after')
    def selected(self):
        if self.fact_keys is not None:
            if len(set(self.fact_keys))!=len(self.fact_keys) or any(len(k)>100 for k in self.fact_keys):
                raise ValueError('Distinct bounded fact keys required')
        return self


def state(record, ident):
    kind=ident.split('_',1)[0];spec=inspection(kind)
    frozen = record.get('metric_read_selections', {}).get(ident)
    if frozen is not None:
        return {'stage': 'selected_from_question', 'keys': frozen}
    if kind not in agent_energy.KINDS:
        if record.get('objective') == 'open_ended' and not record.get('read_requests'):
            return {'stage': 'select_before_read', 'keys': agent_outputs.FACTS[kind]}
        return {'stage': 'whole_record', 'keys': None}
    request=next((r for r in record.get('read_requests',[]) if r['record_id']==ident),None)
    wanted=agent_outputs.requirement(record,request['request_key']) if request else None
    events=[e for e in record['events'] if e['tool']==spec.read_tool and e['status']=='succeeded' and e.get('result',{}).get(spec.record_key)==ident]
    if wanted and not wanted['fact_keys']:
        return {'stage':'source_status','keys':None}
    if events:
        source=events[-1]['result'];projected=model_projection(source,kind)
        keys=[f['fact'] for f in projected['available_fact_catalog']]
        if wanted:keys=[k for k in keys if k in wanted['fact_keys']]
        return {'stage':'select_facts' if keys else 'source_status','keys':keys or None,
                'read_event_index':record['events'].index(events[-1]),'selected_fact_keys':source.get('selected_energy_fact_keys') or []}
    if wanted and wanted['fact_keys']:
        return {'stage':'planned_facts','keys':wanted['fact_keys']}
    return {'stage':'discover_catalog','keys':None}


def key_schema(record,ident):
    current=state(record,ident);keys=current['keys']
    if not keys:return {'type':'null','description':'Read current source/catalog only; no numeric fact selected.'}
    return {'type':'array','minItems':1,'maxItems':min(12,len(keys)),'uniqueItems':True,
            'items':{'type':'string','enum':keys},
            'description':'Before reading values, select ONLY fields requested in the original question and obey exclusions. The initial selection is retained for subsequent reads and deliveries. Select the requested facts using the known catalog. Null is a defined source value, not a reason to skip reading. Catalog-only repetition makes no progress.'}


def leaf_schema(tool,record,ids,argument):
    result=copy.deepcopy(tool);variants=[]
    for ident in ids:
        props={argument:{'type':'string','const':ident},'fact_keys':key_schema(record,ident)}
        variants.append({'type':'object','properties':props,'required':[argument,'fact_keys'],'additionalProperties':False})
    result['function']['parameters']={'oneOf':variants}
    return result


def batch_schema(tool,record,ids):
    result=copy.deepcopy(tool);variants=[]
    for ident in ids:
        item=ReadSelection.model_json_schema();item['properties']['record_id']={'type':'string','const':ident}
        item['properties']['fact_keys']=key_schema(record,ident)
        item['required']=['record_id','fact_keys'];variants.append(item)
    result['function']['parameters']={'type':'object','properties':{'selections':{'type':'array','minItems':1,'maxItems':3,'items':{'oneOf':variants}}},'required':['selections'],'additionalProperties':False}
    return result


def validate(record,selection):
    kind = selection.record_id.split('_',1)[0]
    if kind not in agent_energy.KINDS and selection.fact_keys is None:
        return  # Legacy internal readers and inspection callers retain whole-record reads.
    current=state(record,selection.record_id);keys=current['keys']
    if keys and (not selection.fact_keys or not set(selection.fact_keys)<=set(keys)):
        raise core.ValidationError('Select requested fact_keys from the current known catalog; repeating only the catalog is not progress')
    if not keys and selection.fact_keys:
        raise core.ValidationError('Discover the current source catalog before choosing numeric facts')


def progress(record):
    ids=[]
    for e in record['events']:
        if e['status']=='succeeded' and e['tool'] in {'end_use_read','utility_comparison_read'}:
            result=e['result'];ident=result.get('enduse_id') or result.get('utility_id')
            if ident not in ids:ids.append(ident)
    return [{'record_id':ident,**state(record,ident)} for ident in ids]


def freeze_selection(record, selection):
    if selection.fact_keys is None:
        return
    frozen = record.setdefault('metric_read_selections', {})
    previous = frozen.get(selection.record_id)
    if previous is not None and not set(selection.fact_keys) <= set(previous):
        raise core.ValidationError('Read fields cannot expand after observing values; clarify the requested outputs')
    frozen.setdefault(selection.record_id, list(selection.fact_keys))
