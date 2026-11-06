"""Project-scoped absence is checked against the full catalog, never a recent slice."""
import json
from pathlib import Path
from typing import Literal

from pydantic import Field, StrictBool, model_validator

from . import core
from .schema import Contract
from .agent_semantics import inspection


class Missing(Contract):
    kind: Literal['thermal', 'lifecycle', 'cost', 'engineering', 'schedule', 'operation']
    record_id: str | None = Field(default=None, pattern=r'^(thermal|lifecycle|cost|engineering|schedule|operation)_[a-f0-9]{32}$')
    finish: StrictBool = False

    @model_validator(mode='after')
    def matching_kind(self):
        if self.record_id and not self.record_id.startswith(self.kind+'_'):
            raise ValueError('Record identifier must match the selected kind')
        return self


def snapshot(domain, pid, kind):
    """One SQLite read snapshot for project revision and every owned record ID."""
    domain.store.check_id(pid)
    inspection(kind)
    with domain.store.connect() as con:
        con.execute('BEGIN')
        project = con.execute("SELECT revision FROM records WHERE kind='project' AND id=? ORDER BY revision DESC LIMIT 1", (pid,)).fetchone()
        if project is None: raise KeyError(pid)
        rows = con.execute('SELECT body FROM records r WHERE kind=? AND project_id=? AND revision=(SELECT MAX(revision) '
                           'FROM records x WHERE x.kind=r.kind AND x.id=r.id) ORDER BY rowid DESC', (kind, pid)).fetchall()
        records = [json.loads(r[0]) for r in rows]
    key = inspection(kind).record_key
    basis = {'project_id':pid, 'project_revision':project[0], 'kind':kind,
             'records':[{k:r[k] for k in (key,'revision','hash')} for r in records],
             'catalog_version':core.sha(Path(__file__))}
    return records, core.hash_json(basis)


def catalog(domain, pid, spec):
    records, digest = snapshot(domain, pid, spec.kind)
    recent = [{spec.record_key:r[spec.record_key], 'name':r['input']['name'],
               'status':spec.service(domain).view(pid,r[spec.record_key])['status']} for r in records[:6]]
    return {'kind':spec.kind, 'records':recent, 'total_count':len(records), 'returned_count':len(recent),
            'truncated':len(records)>len(recent), 'catalog_hash':digest,
            'notice':'最近6条不代表完整目录；未列出不证明不存在。总数为0或明确ID不可用时，可用professional_missing核验；不能猜ID或补造数值。'}


def rows(value):
    # Old persisted task events contain bare arrays. They are not absence proofs.
    return value if isinstance(value, list) else value['records']


def key(reference):
    request = reference['request']
    return request['kind'], request.get('record_id')


def assess(domain, pid, request):
    if not request: raise core.ValidationError('Provide missing kind and optional explicit record_id')
    records, digest = snapshot(domain, pid, request.kind)
    record_key = inspection(request.kind).record_key
    if (request.record_id is None and records) or any(r[record_key]==request.record_id for r in records):
        raise core.ValidationError('Record available in this project; read its current result or limitation instead of claiming absence')
    # Never query a foreign project to distinguish a foreign ID from a nonexistent ID.
    receipt = {'kind':request.kind, 'record_id':request.record_id, 'state':'no_record_available',
               'scope':'requested_record_in_project' if request.record_id else 'entire_project_kind',
               'reason_code':'record_not_available_in_project' if request.record_id else 'no_records_in_project',
               'project_record_count':len(records), 'checked_at':core.now(),
               'notice':'只核验当前项目的记录可用性，不代表已计算、建筑资料充分或应用不支持此功能。失败调用也不能证明未产生副作用，禁止据此自动重试写操作。'}
    return {'status':'verified', 'reference':{'request':request.model_dump(mode='json'),'catalog_hash':digest},
            'missing':receipt}


def attach(answer, domain, pid, references, reader=None):
    answer = {**answer, 'verification':list(answer.get('verification',[])), 'gaps':list(answer.get('gaps',[]))}
    checked = []
    for saved in references:
        request = Missing.model_validate(saved['request']); valid = False
        try:
            current = reader(request) if reader else assess(domain,pid,request)
            if current['reference']['catalog_hash'] != saved['catalog_hash']:
                raise ValueError('Catalog changed since absence was checked')
            checked.append(current['missing']); valid = True
        except (ValueError, KeyError, OSError):
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
