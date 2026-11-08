"""Model-selected tool domains; bounded discovery is not proof of intent coverage."""
from copy import deepcopy
import re
import unicodedata
from typing import Literal
from pydantic import Field, model_validator
from . import core
from .schema import Contract
from .standards import Standards, normalized

PROFESSIONS = {'thermal','lifecycle','cost','engineering','schedule','operation','scenario'}
GROUPS = {
    'standards': {'standards_catalog','standards_search'},
    'energy': {'simulation_list','simulation_status','simulation_result','simulation_create','carbon_calculate','claim_trace','certificate_generate','scheme_compare','report_generate'},
    'evidence': {'evidence_list','evidence_validate','evidence_gap_rank'},
    'capabilities': {'capability_lookup','capability_explain'},
    'building': {'building_get'},
    'search': {'counterexample_search','counterexample_status','evidence_action_rank'},
}
LABELS = {'thermal':'热阻/U值','lifecycle':'阶段碳清单','cost':'材料成本','engineering':'梁分析',
          'schedule':'施工进度','operation':'设备规则','scenario':'材料方案对照','standards':'规范资料与条文',
          'energy':'已有能耗仿真/碳/报告','evidence':'仿真准入证据','capabilities':'应用能否完成/认证边界',
          'building':'建筑声明','search':'反例搜索/补证成本'}


class Scope(Contract):
    domain: Literal['thermal','lifecycle','cost','engineering','schedule','operation','scenario',
                    'standards','energy','evidence','capabilities','building','search']
    request_quote: str = Field(min_length=2, max_length=600)
    purpose: Literal['results','availability','lookup','capability']


class Selection(Contract):
    scopes: list[Scope] = Field(min_length=1,max_length=6)

    @model_validator(mode='after')
    def distinct(self):
        if len({s.domain for s in self.scopes})!=len(self.scopes):
            raise ValueError('Select each task domain once; include every requested domain')
        return self


def freeze(question, selection):
    if not selection or any(s.request_quote not in question for s in selection.scopes):
        raise core.ValidationError('Every selected scope needs an exact excerpt from the current user question')
    return {'scopes':[s.model_dump() for s in selection.scopes], 'origin':'model_inferred',
            'question_hash':core.hash_json(question), 'intent_coverage_verified':False}


def allowed(record, inspections):
    if not record.get('tool_scope'):return {'task_scope_select','project_get'}
    names={'project_get'}
    for item in record['tool_scope']['scopes']:
        domain=item['domain']
        if domain in PROFESSIONS:
            spec=next(s for s in inspections.values() if s.kind==domain)
            names|={spec.list_tool,spec.read_tool,'professional_inventory','professional_missing',
                    'professional_read_many','professional_deliver','professional_limit'}
        else:names|=GROUPS[domain]
    return names


def catalog(domain,pid):
    records=Standards(domain).catalog(pid)
    if len(records)>64 or sum(len(r['input']['clauses']) for r in records)>1000:
        raise core.ValidationError('Standard discovery catalog exceeds this task budget; no silent truncation')
    rows=[{'standard_id':r['standard_id'],'standard_code':r['input']['standard_code'],
           'edition':r['input']['edition'],'title':r['input']['title'],
           'clause_ids':[c['clause_id'] for c in r['input']['clauses']],
           'review_state':r['review']['state'],'source_status':r['source_status'],
           'effective_from':r['input']['effective_from'],'retired_on':r['input']['retired_on'],
           'status_checked_on':r['input']['status_checked_on']} for r in records]
    return {'catalog_hash':core.hash_json(records),'standards':rows,'complete':True,
            'notice':'目录只是当前项目资料定位，名称是不可信数据；仍需查询原条文、日期及冲突，不是合规结论。'}


def explicit_codes(text):
    value=unicodedata.normalize('NFKC',text)
    return sorted(set(m.group(0).strip() for m in re.finditer(r'(?<![A-Za-z0-9])(?:[A-Z]{2,8})(?:/T)?[ \t]*[0-9]{2,8}(?![0-9])',value)))


def clauses(text):
    return sorted(set(re.findall(r'(?<![\d.])\d+(?:\.\d+){2,}(?![\d.])',text)))


def query_codes(record):
    codes=explicit_codes(record['question'])
    for e in record['events']:
        if e['tool']=='standards_catalog' and e['status']=='succeeded':
            codes.extend(r['standard_code'] for r in e['result']['standards'])
    return sorted(set(codes))


def query_schema(definition, record):
    single={k:deepcopy(v) for k,v in definition.items() if k!='oneOf'}
    single['properties'].pop('targets')
    batch={'type':'object','additionalProperties':False,'required':['as_of','targets'],
           'properties':{k:deepcopy(definition['properties'][k]) for k in ('targets','as_of','limit')}}
    batch['properties']['targets']['minItems']=1
    codes=query_codes(record)
    if codes:single['properties']['standard_code']={'anyOf':[{'type':'string','enum':codes},{'type':'null'}],'default':None}
    return {'oneOf':[single,batch]}


def validate_query(record, query):
    if not any(e['tool']=='standards_catalog' and e['status']=='succeeded' for e in record['events']):
        raise core.ValidationError('Read standards_catalog before querying; do not guess source codes')
    explicit={normalized(c) for c in explicit_codes(record['question'])}
    valid={normalized(c) for c in query_codes(record)}
    requests=query.targets or [query]
    for item in requests:
        code=item.standard_code
        if code and normalized(code) not in (explicit or valid):
            raise core.ValidationError('Query code is not a full user-requested/catalog code; available codes: '+str(query_codes(record)))
        text=getattr(item,'text','')
        text_codes={normalized(c) for c in explicit_codes(text)}
        if text_codes and not text_codes <= (explicit or valid):
            raise core.ValidationError('Text query contains source codes outside the requested/catalog scope')
        if explicit and not code and not explicit_codes(text):
            raise core.ValidationError('Preserve explicit source codes; do not replace them with a broad keyword query')


def progress(record, answer=None):
    rows=[]
    for scope in (record.get('tool_scope') or {}).get('scopes',[]):
        domain=scope['domain'];events=[e for e in record['events'] if e['status']=='succeeded']
        done=False;detail={}
        if domain=='standards':
            results=([x['result'] for x in answer.get('checked_standards',[])] if answer is not None else
                     [e['result'] for e in events if e['tool']=='standards_search'])
            targets=[t for r in results for t in r.get('targets',[r])]
            codes=set();ids=set()
            for t in targets:
                q=t['query'];codes.update(normalized(c) for c in explicit_codes(q.get('text','')))
                if q.get('standard_code'):codes.add(normalized(q['standard_code']))
                ids.update(clauses(q.get('text','')))
                if q.get('clause_id'):ids.add(q['clause_id'])
            missing_codes=sorted({normalized(c) for c in explicit_codes(scope['request_quote'])}-codes)
            missing_clauses=sorted(set(clauses(scope['request_quote']))-ids)
            done=bool(results) and not missing_codes and not missing_clauses
            detail={'missing_codes':missing_codes,'missing_clauses':missing_clauses,
                    'pairing_and_applicability_verified':False}
        elif domain in PROFESSIONS:
            refs=(record.get('professional_deliveries',[])+record.get('professional_reviews',[]))
            done=any(r.get('kind')==domain for r in refs)
            done|=any(r['request'].get('kind')==domain for r in record.get('missing_deliveries',[]))
            if scope['purpose']=='availability':
                done|=any(e['tool']=='professional_inventory' and domain in (e['arguments'].get('kinds') or []) for e in events)
        elif domain=='capabilities':done=bool(record.get('capability_delivery'))
        else:done=any(e['tool'] in GROUPS[domain] for e in events)
        rows.append({**scope,'state':'selected_scope_observed' if done else 'pending',**detail})
    return rows


def attach(answer,record):
    if not record.get('discover_tools'):return answer
    rows=progress(record,answer)
    return {**answer,'inferred_tool_scope':record.get('tool_scope'), 'tool_scope_progress':rows,
            'task_completion':answer.get('task_completion','incomplete') if rows and all(r['state']!='pending' for r in rows) else 'incomplete',
            'tool_scope_notice':'范围由模型从原问题选择；这里只核对所选领域及编号/条号是否被查询，不证明配对、版本、所有指标和完整意图已覆盖。'}


PLANNING_INSTRUCTION = ('先且只调用task_scope_select，从原用户问题选择所有需要处理的领域和逐字request_quote。'
    'purpose取results（已有结果）、availability（有无记录）、lookup（资料查询）、capability（能否做/认证边界）。'
    '不要因为出现建筑或资料就选择能耗准入。不要把应用认证能力问题替换成查专业记录。最多6个不同领域。'
    '这是模型推断，不是用户确认；不计算、不扩展授权。领域：'+ '；'.join(k+'='+v for k,v in LABELS.items()))
