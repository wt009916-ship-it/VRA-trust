"""User-declared read scope, distinct from model inference or compute permission."""
import re
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from . import core, agent_missing, agent_outputs, agent_energy
from .schema import Contract
from .agent_semantics import inspection, can_deliver_requested_facts


class ReadRequest(Contract):
    request_key: str = Field(pattern=r'^[A-Za-z0-9_-]{1,40}$')
    kind: Literal['thermal','lifecycle','cost','engineering','schedule','operation','scenario', 'enduse', 'utility']
    purpose: Literal['availability','results']
    record_id: str | None = Field(default=None,pattern=r'^(thermal|lifecycle|cost|engineering|schedule|operation|scenario|enduse|utility)_[a-f0-9]{32}$')

    @model_validator(mode='after')
    def scope(self):
        if self.record_id and not self.record_id.startswith(self.kind+'_'):
            raise ValueError('Record ID must match the requested professional kind')
        if self.purpose=='results' and not self.record_id:
            raise ValueError('Result inspection requires an explicit record ID; no silent latest-record substitution')
        return self


def result_ids(requests):
    return {r['record_id'] for r in requests if r['purpose']=='results'}


def availability(domain,pid,requests,keys):
    if not keys or len(keys)>6 or len(set(keys))!=len(keys):
        raise core.ValidationError('Select one to six distinct declared availability request keys')
    allowed={r['request_key']:r for r in requests if r['purpose']=='availability'}
    if any(k not in allowed for k in keys):
        raise core.ValidationError('Availability keys must come from this task user-declared read requests')
    selected=[allowed[k] for k in keys]
    snapshots=agent_missing.snapshot_many(domain,pid,list(dict.fromkeys(r['kind'] for r in selected)))
    results=[]
    for request in selected:
        records,digest=snapshots[request['kind']];field=inspection(request['kind']).record_key
        present=any(r[field]==request['record_id'] for r in records) if request['record_id'] else bool(records)
        row={'request_key':request['request_key'],'kind':request['kind'],'record_id':request['record_id'],
             'scope':'requested_record_in_project' if request['record_id'] else 'entire_project_kind',
             'state':'records_present' if present else 'no_record_available','project_record_count':len(records),
             'checked_at':core.now(), 'knowledge_limits':agent_missing.availability_knowledge(),
             'notice':'仅检查当前项目记录是否存在；存在不证明结果当前有效，缺失不证明未执行过计算。不查询其他项目、不输出工程数值。'}
        results.append({'request':dict(request),'catalog_hash':core.hash_json([digest,core.sha(Path(__file__))]),'availability':row})
    return {'status':'verified','references':results,'snapshot_count':1,'finish':False}


def recheck(domain,pid,requests,references):
    keys=[r['request']['request_key'] for r in references]
    current=availability(domain,pid,requests,keys)['references']
    checks=[]
    for previous,now in zip(references,current):
        valid=previous['request']==now['request'] and previous['catalog_hash']==now['catalog_hash']
        checks.append({'request_key':now['request']['request_key'],'passed':valid,
                       'availability':now['availability'] if valid else None})
    return {'checks':checks,'snapshot_count':1}


def pending(record):
    if record.get('infer_outputs') and not record.get('output_plan'):
        return [r['request_key'] for r in record.get('read_requests', [])]
    available={r['request']['request_key'] for r in record.get('availability_deliveries',[])}
    results={r['record_id'] for r in record.get('professional_deliveries',[])}
    reviewed={r['record_id'] for r in record.get('professional_reviews',[])}
    unresolved={i['request_key'] for i in (record.get('output_plan') or {}).get('items',[]) if i.get('clarification_question')}
    absent={r['request'].get('record_id') for r in record.get('missing_deliveries',[])}
    return [r['request_key'] for r in record.get('read_requests',[]) if r['request_key'] not in unresolved and
            (r['request_key'] not in available if r['purpose']=='availability' else
             r['record_id'] not in results|absent|reviewed or
             (r['record_id'] in results and not any(d.get('limitation_status') for d in record.get('professional_deliveries', []) if d['record_id'] == r['record_id'])
              and agent_outputs.missing_facts(record, r, record.get('professional_deliveries', []))))]


def progress(record,answer):
    answer=answer or {};available={r['request_key'] for r in answer.get('checked_availability',[])}
    values={r['record_id'] for r in answer.get('checked_statements',[])}
    reviewed={r['record_id'] for r in answer.get('checked_reviews',[])}
    limited={r['record_id'] for r in answer.get('checked_limitations',[])}
    absent={r.get('record_id') for r in answer.get('checked_missing',[])}
    submitted=set(r['request_key'] for r in record.get('read_requests',[]))-set(pending(record))
    rows=[]
    for r in record.get('read_requests',[]):
        state='unfulfilled'
        if r['purpose']=='availability' and r['request_key'] in available:state='availability_verified'
        elif r['purpose']=='results':
            state=('result_verified' if r['record_id'] in values else 'limitation_verified' if r['record_id'] in limited
                   else 'record_unavailable' if r['record_id'] in absent else state)
        wanted = agent_outputs.requirement(record, r['request_key']) or {}
        if wanted.get('clarification_question'):
            state='needs_clarification'
        elif r['record_id'] in reviewed and not wanted.get('fact_keys'):
            state='source_review_verified'
        if state == 'result_verified':
            actual = [{'record_id': d['record_id'], 'statements': d['facts']} for d in answer.get('checked_statements', [])]
            if agent_outputs.missing_facts(record, r, actual):state='required_facts_missing'
            else:
                wanted=agent_outputs.requirement(record,r['request_key'])
                if any(f['value'] is None for d in answer.get('checked_statements',[]) if d['record_id']==r['record_id']
                       for f in d['facts'] if not wanted or f['fact'] in wanted['fact_keys']):
                    state='fields_unavailable'
        if record.get('infer_outputs') and not record.get('output_plan'):state='output_plan_missing'
        if state=='unfulfilled' and r['request_key'] in submitted:state='delivery_not_currently_verified'
        rows.append({**r,'state':state})
    return rows


def attach(answer,domain,pid,record,reader=None):
    if not record.get('read_requests'):return answer
    answer={**answer,'verification':list(answer.get('verification',[])),'gaps':list(answer.get('gaps',[]))}
    answer['read_execution'] = record.get('read_execution', 'model')
    answer['read_execution_receipt'] = record.get('read_execution_receipt')
    if record.get('read_execution') == 'application':
        answer['task_notice'] = '模型解析所需字段；应用执行用户声明范围的读取与查询，并重验来源。执行记录不证明模型自主选工具、完整理解意图或工程合规。'
    refs=record.get('availability_deliveries',[]);checked=[]
    if refs:
        result=reader() if reader else recheck(domain,pid,record['read_requests'],refs)
        if len(result['checks'])!=len(refs):raise core.ValidationError('Incomplete availability recheck')
        for saved,row in zip(refs,result['checks']):
            if row['request_key']!=saved['request']['request_key']:raise core.ValidationError('Availability recheck scope mismatch')
            if row['passed']:checked.append(row['availability'])
            answer['verification'].append({'check':'current_requested_availability','request_key':row['request_key'],
                'passed':row['passed'],'meaning':'只核验声明范围的记录可用性，不证明结果有效或完成工程计算'})
    if record.get('termination'):
        answer['termination'] = record['termination']
    answer['checked_availability']=checked
    rows=progress(record,answer)
    answer['read_request_progress']=rows
    answer['read_request_coverage']='all_declared_scopes_checked' if all(r['state'] not in {'unfulfilled','delivery_not_currently_verified','required_facts_missing','output_plan_missing','needs_clarification'} for r in rows) else 'incomplete'
    if checked:
        answer['task_completion']='partial'
        answer['summary']='已按项核验部分或全部声明范围；未完成项见读取进度，数值有效性和自由问题完整覆盖仍分别判断。'
        answer['gaps']=[g for g in answer['gaps'] if g.get('message')!='本轮没有通过核验的专业交付']
    for row in rows:
        if row['state'] in {'unfulfilled','delivery_not_currently_verified','required_facts_missing','output_plan_missing','needs_clarification'}:
            answer['gaps'].append({'request_key':row['request_key'],'message':'声明读取目标尚未形成当前有效交付：'+row['request_key'],
                                  'action':'按本次声明范围查询并交付，不替换编号或新增计算。'})
    answer['task_notice']='只按用户明确声明的读取范围跟踪交付；存在记录不证明当前结果有效，缺失不等于零或从未计算。自由问题的其他要求未获完整覆盖核验。'
    return agent_outputs.attach(answer, record)

def next_actions(record):
    """Suggestions from declared scopes and observed reads; never execute or infer scope."""
    waiting = set(pending(record))
    reads = {}
    unavailable = set()
    for event in record.get('events', []):
        unavailable.update(event.get('recovery', {}).get('unavailable_record_ids', []))
        if event['status'] != 'succeeded':
            continue
        for request in record.get('read_requests', []):
            spec = inspection(request['kind'])
            if event['tool'] == spec.read_tool:
                current = event['result']
                reads[current[spec.record_key]] = current
    actions = []
    availability_keys = []
    for request in record.get('read_requests', []):
        if request['request_key'] not in waiting:
            continue
        if request['purpose'] == 'availability':
            availability_keys.append(request['request_key'])
            continue
        ident = request['record_id']; kind = request['kind']; spec = inspection(kind)
        current = reads.get(ident)
        action = {'request_key': request['request_key'], 'record_id': ident}
        if current is not None:
            wanted = agent_outputs.requirement(record, request['request_key']) or {}
            if wanted and not wanted.get('fact_keys') and wanted.get('explanation_topics'):
                from .agent_reviews import reference
                action.update(tool='professional_review', arguments={'review': reference(current, kind)})
            elif not can_deliver_requested_facts(current, kind, wanted.get('fact_keys', [])):
                action.update(tool='professional_limit', arguments={'limitation': {
                    'kind': kind, 'record_id': ident, 'record_hash': current['hash'],
                    'status': current['status'], 'finish': False}})
            else:
                facts = current.get('explanation_facts', [])
                if kind in agent_energy.KINDS:
                    facts = [f for f in facts if f['fact'] in (current.get('selected_energy_fact_keys') or [])]
                if kind in agent_energy.KINDS and not facts:
                    arguments = {spec.argument:ident}
                    if wanted.get('fact_keys'):arguments['fact_keys'] = wanted['fact_keys']
                    action.update(tool=spec.read_tool, arguments=arguments, required_fields=['fact_keys'],
                                  notice='Select needed keys from the read result available_fact_catalog; no numeric facts were selected yet.')
                else:
                    action.update(tool='professional_deliver', arguments={'delivery': {
                        'kind': kind, 'record_id': ident, 'record_hash': current['hash'], 'finish': False}},
                        required_fields=['delivery.statements'], available_facts=facts,
                        output_requirement=agent_outputs.requirement(record, request['request_key']))
        elif ident in unavailable:
            action.update(tool='professional_missing', arguments={'missing': {
                'kinds': [kind], 'record_id': ident, 'finish': False}})
        else:
            arguments={spec.argument:ident};wanted=agent_outputs.requirement(record,request['request_key']) or {}
            if kind in agent_energy.KINDS and wanted.get('fact_keys'):arguments['fact_keys']=wanted['fact_keys']
            action.update(tool=spec.read_tool, arguments=arguments)
        actions.append(action)
    if availability_keys:
        actions.append({'tool': 'requested_availability',
                        'arguments': {'request_keys': availability_keys, 'finish': False}})
    return actions


def commentary_review(record, text):
    """Exact identifier membership only, not validation of numerical or semantic prose."""
    allowed = {r['record_id'] for r in record.get('read_requests', []) if r.get('record_id')}
    mentioned = set(re.findall(
        r'\b(?:thermal|lifecycle|cost|engineering|schedule|operation|scenario|enduse|utility)_[A-Za-z0-9_-]+\b', text or ''))
    unknown = sorted(mentioned - allowed)
    return {'status': 'reference_mismatch' if unknown else 'references_match',
            'unknown_record_ids': unknown, 'allowed_record_ids': sorted(allowed),
            'scope': 'declared_record_identifiers_only', 'semantics_verified': False}
