"""Project-scoped absence is checked against the full catalog, never a recent slice."""
import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import ConfigDict, Field, StrictBool, model_validator
from pydantic.json_schema import SkipJsonSchema

from . import core
from .schema import Contract
from .agent_semantics import inspection


class Missing(Contract):
    # Legacy single-kind receipts remain readable; the model sees one array selector only.
    model_config = ConfigDict(json_schema_extra={'required':['kinds']})
    kind: SkipJsonSchema[Literal['thermal', 'lifecycle', 'cost', 'engineering', 'schedule', 'operation'] | None] = None
    kinds: Annotated[list[Literal['thermal', 'lifecycle', 'cost', 'engineering', 'schedule', 'operation']], Field(min_length=1,max_length=6)] | SkipJsonSchema[None] = None
    record_id: str | None = Field(default=None, pattern=r'^(thermal|lifecycle|cost|engineering|schedule|operation)_[a-f0-9]{32}$')
    finish: StrictBool = False

    @model_validator(mode='after')
    def matching_kind(self):
        if (self.kind is None)==(self.kinds is None):
            raise ValueError('Select either one kind or multiple kinds, not both')
        if self.kinds is not None and (len(set(self.kinds))!=len(self.kinds) or (len(self.kinds)>1 and self.record_id is not None)):
            raise ValueError('Kinds must be distinct; a record ID requires exactly one kind')
        selected=self.kind or self.kinds[0]
        if self.record_id and not self.record_id.startswith(selected+'_'):
            raise ValueError('Record identifier must match the selected kind')
        return self

    def requests(self):
        return [Missing(kind=k,record_id=self.record_id,finish=self.finish) for k in self.kinds] if self.kinds else [self]


def references(result):
    return result.get('references') or [result['reference']]


def snapshot_many(domain, pid, kinds):
    """One SQLite read snapshot for project revision and every owned record ID."""
    domain.store.check_id(pid)
    if not kinds or len(kinds)>6 or len(set(kinds))!=len(kinds):
        raise core.ValidationError('Select one to six distinct professional kinds')
    for kind in kinds: inspection(kind)
    with domain.store.connect() as con:
        con.execute('BEGIN')
        project = con.execute("SELECT revision FROM records WHERE kind='project' AND id=? ORDER BY revision DESC LIMIT 1", (pid,)).fetchone()
        if project is None: raise KeyError(pid)
        rows = con.execute('SELECT kind,body FROM records r WHERE kind IN ('+','.join('?' for _ in kinds)+') AND project_id=? '
                           'AND revision=(SELECT MAX(revision) FROM records x WHERE x.kind=r.kind AND x.id=r.id) '
                           'ORDER BY rowid DESC', (*kinds,pid)).fetchall()
    version=core.sha(Path(__file__));result={}
    for kind in kinds:
        records=[json.loads(r[1]) for r in rows if r[0]==kind];key=inspection(kind).record_key
        basis={'project_id':pid,'project_revision':project[0],'kind':kind,
               'records':[{k:r[k] for k in (key,'revision','hash')} for r in records],'catalog_version':version}
        result[kind]=(records,core.hash_json(basis))
    return result


def snapshot(domain, pid, kind):
    return snapshot_many(domain,pid,[kind])[kind]


def catalog(domain, pid, spec):
    records, digest = snapshot(domain, pid, spec.kind)
    return catalog_rows(domain,pid,spec,records,digest)


def catalog_rows(domain,pid,spec,records,digest):
    recent = [{spec.record_key:r[spec.record_key], 'name':r['input']['name'],
               'status':spec.service(domain).view(pid,r[spec.record_key])['status']} for r in records[:6]]
    return {'kind':spec.kind, 'records':recent, 'total_count':len(records), 'returned_count':len(recent),
            'truncated':len(records)>len(recent), 'catalog_hash':digest,
            'notice':'最近6条不代表完整目录；未列出不证明不存在。总数为0或明确ID不可用时，可用professional_missing核验；不能猜ID或补造数值。'}


def inventory(domain,pid,kinds):
    snapshots=snapshot_many(domain,pid,kinds)
    return {'catalogs':[catalog_rows(domain,pid,inspection(kind),*snapshots[kind]) for kind in kinds],
            'notice':'所选专业目录在一次数据库快照中读取，逐类标明覆盖范围；存在记录仍需读取当前结果，空目录仍需professional_missing正式说明。'}


def rows(value):
    # Old persisted task events contain bare arrays. They are not absence proofs.
    return value if isinstance(value, list) else value['records']


def key(reference):
    request = reference['request']
    return request['kind'], request.get('record_id')


def availability_knowledge():
    # A catalog snapshot cannot establish historical execution or engineering readiness.
    return {'historical_calculation': 'not_assessed', 'current_numeric_validity': 'not_assessed',
            'application_capability': 'not_assessed', 'building_data_sufficiency': 'not_assessed'}


def assess(domain, pid, request, captured=None):
    if not request: raise core.ValidationError('Provide missing kind and optional explicit record_id')
    if request.kinds:
        snapshots=snapshot_many(domain,pid,request.kinds)
        results=[assess(domain,pid,r,snapshots[r.kind]) for r in request.requests()]
        return {'status':'verified','references':[r['reference'] for r in results],
                'missing':[r['missing'] for r in results],'finish':request.finish,'snapshot_count':1}
    records, digest = captured if captured is not None else snapshot(domain, pid, request.kind)
    record_key = inspection(request.kind).record_key
    if (request.record_id is None and records) or any(r[record_key]==request.record_id for r in records):
        raise core.ValidationError('Record available in this project; read its current result or limitation instead of claiming absence')
    # Never query a foreign project to distinguish a foreign ID from a nonexistent ID.
    receipt = {'kind':request.kind, 'record_id':request.record_id, 'state':'no_record_available',
               'scope':'requested_record_in_project' if request.record_id else 'entire_project_kind',
               'reason_code':'record_not_available_in_project' if request.record_id else 'no_records_in_project',
               'project_record_count':len(records), 'checked_at':core.now(), 'knowledge_limits':availability_knowledge(),
               'notice':'只核验当前项目的记录可用性，不证明曾经计算或从未计算、建筑资料充分或应用不支持此功能。失败调用也不能证明未产生副作用，禁止据此自动重试写操作。'}
    return {'status':'verified', 'reference':{'request':request.model_dump(mode='json'),'catalog_hash':digest},
            'missing':receipt}


def recheck(domain,pid,references):
    requests=[Missing.model_validate(saved['request']) for saved in references]
    snapshots=snapshot_many(domain,pid,list(dict.fromkeys(r.kind for r in requests)))
    checks=[]
    for saved,request in zip(references,requests):
        row={'request':request.model_dump(mode='json'),'passed':False,'missing':None}
        try:
            result=assess(domain,pid,request,snapshots[request.kind])
            if result['reference']['catalog_hash']==saved['catalog_hash']:
                row.update(passed=True,missing=result['missing'])
        except (ValueError,KeyError,OSError):pass
        checks.append(row)
    return {'checks':checks,'snapshot_count':1,'notice':'同一完整目录快照重新核对先前所选缺失范围；不调用计算器、不改变记录。'}


def attach(answer, domain, pid, references, reader=None):
    answer = {**answer, 'verification':list(answer.get('verification',[])), 'gaps':list(answer.get('gaps',[]))}
    checked = []
    result=reader() if reader else recheck(domain,pid,references)
    checks=result['checks']
    if len(checks)!=len(references):raise core.ValidationError('Incomplete absence recheck; no delivery accepted')
    for saved,row in zip(references,checks):
        request = Missing.model_validate(saved['request']); valid = False
        if row['request']==saved['request'] and row['passed']:
            checked.append(row['missing']);valid=True
        else:
            answer['gaps'].append({'kind':request.kind,'message':'记录目录已变化或当前不可核验，原缺失说明不能沿用',
                                   'action':'重新查询完整项目范围并读取当前记录；不继续宣称原记录缺失'})
        answer['verification'].append({'check':'current_project_record_absence','kind':request.kind,
            'record_id':request.record_id,'passed':valid,'meaning':'只核验当前项目范围内无所选记录，不代表工程任务完成'})
    answer['checked_missing'] = checked
    if checked:
        answer['execution_scope'] = 'checked_record_availability_and_professional_deliveries'
        if answer.get('task_completion') == 'not_assessed': answer['task_completion'] = 'incomplete'
        answer['summary'] = '已核验所列记录缺失；没有补造工程结果，所需计算仍未完成。' if not answer.get('checked_statements') else '部分结果已核验，另有所需记录缺失；不能视为整个工程任务完成。'
        answer['gaps'] = [g for g in answer['gaps'] if g.get('message')!='本轮没有通过核验的专业交付']
        answer['gaps'] += [{'kind':r['kind'],'message':'所需记录在当前项目中不可用',
                           'action':'核对项目和记录编号；需要计算时另行提交完整参数与授权，不自动重试失败写操作'} for r in checked]
    answer['can_recommend'] = False
    return answer


def pending_empty(record):
    """Observed empty catalogs without a corresponding formal availability statement."""
    last={};read=set();delivered={r['request']['kind'] for r in record.get('missing_deliveries',[])}
    for event in record['events']:
        if event['status']!='succeeded':continue
        result=event.get('result') or {}
        if event['tool']=='professional_inventory':
            for catalog in result['catalogs']:last[catalog['kind']]=catalog['total_count']
        else:
            for kind in ['thermal','lifecycle','cost','engineering','schedule','operation']:
                spec=inspection(kind)
                if event['tool']==spec.list_tool and isinstance(result,dict):last[kind]=result['total_count']
                if event['tool']==spec.read_tool:read.add(kind)
    return sorted(kind for kind,count in last.items() if count==0 and kind not in delivered|read)


def pending_available(record):
    """A bounded reminder, not an inferred interpretation of the user's requested facts."""
    catalogs={}
    for event in record['events']:
        if event['status']=='succeeded' and event['tool']=='professional_inventory':
            for catalog in event['result']['catalogs']:catalogs[catalog['kind']]=catalog['total_count']
    delivered={r['kind'] for r in record.get('professional_deliveries',[])}
    return sorted(k for k,count in catalogs.items() if count and k not in delivered)
