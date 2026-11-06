"""User-declared read scope, distinct from model inference or compute permission."""
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from . import core, agent_missing
from .schema import Contract
from .agent_semantics import inspection


class ReadRequest(Contract):
    request_key: str = Field(pattern=r'^[A-Za-z0-9_-]{1,40}$')
    kind: Literal['thermal','lifecycle','cost','engineering','schedule','operation']
    purpose: Literal['availability','results']
    record_id: str | None = Field(default=None,pattern=r'^(thermal|lifecycle|cost|engineering|schedule|operation)_[a-f0-9]{32}$')

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
             'checked_at':core.now(),
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
    available={r['request']['request_key'] for r in record.get('availability_deliveries',[])}
    results={r['record_id'] for r in record.get('professional_deliveries',[])}
    absent={r['request'].get('record_id') for r in record.get('missing_deliveries',[])}
    return [r['request_key'] for r in record.get('read_requests',[]) if
            (r['request_key'] not in available if r['purpose']=='availability' else r['record_id'] not in results|absent)]


def progress(record,answer):
    answer=answer or {};available={r['request_key'] for r in answer.get('checked_availability',[])}
    values={r['record_id'] for r in answer.get('checked_statements',[])}
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
        if state=='unfulfilled' and r['request_key'] in submitted:state='delivery_not_currently_verified'
        rows.append({**r,'state':state})
    return rows


def attach(answer,domain,pid,record,reader=None):
    if not record.get('read_requests'):return answer
    answer={**answer,'verification':list(answer.get('verification',[])),'gaps':list(answer.get('gaps',[]))}
    refs=record.get('availability_deliveries',[]);checked=[]
    if refs:
        result=reader() if reader else recheck(domain,pid,record['read_requests'],refs)
        if len(result['checks'])!=len(refs):raise core.ValidationError('Incomplete availability recheck')
        for saved,row in zip(refs,result['checks']):
            if row['request_key']!=saved['request']['request_key']:raise core.ValidationError('Availability recheck scope mismatch')
            if row['passed']:checked.append(row['availability'])
            answer['verification'].append({'check':'current_requested_availability','request_key':row['request_key'],
                'passed':row['passed'],'meaning':'只核验声明范围的记录可用性，不证明结果有效或完成工程计算'})
    answer['checked_availability']=checked
    rows=progress(record,answer)
    answer['read_request_progress']=rows
    answer['read_request_coverage']='all_declared_scopes_checked' if all(r['state'] not in {'unfulfilled','delivery_not_currently_verified'} for r in rows) else 'incomplete'
    if checked:
        answer['task_completion']='partial'
        answer['summary']='已按项核验部分或全部声明范围；未完成项见读取进度，数值有效性和自由问题完整覆盖仍分别判断。'
        answer['gaps']=[g for g in answer['gaps'] if g.get('message')!='本轮没有通过核验的专业交付']
    for row in rows:
        if row['state'] in {'unfulfilled','delivery_not_currently_verified'}:
            answer['gaps'].append({'request_key':row['request_key'],'message':'声明读取目标尚未形成当前有效交付：'+row['request_key'],
                                  'action':'按本次声明范围查询并交付，不替换编号或新增计算。'})
    answer['task_notice']='只按用户明确声明的读取范围跟踪交付；存在记录不证明当前结果有效，缺失不等于零或从未计算。自由问题的其他要求未获完整覆盖核验。'
    return answer
