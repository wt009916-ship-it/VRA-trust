"""Append-only manual maintenance workflow with current source-bound rechecks."""
import copy
import html
import json
from pathlib import Path
from typing import Literal
from fastapi import Request
from fastapi.responses import HTMLResponse
from pydantic import Field, StrictBool, StrictFloat, StrictInt, model_validator
from . import core, maintenance_recheck
from .schema import Contract
from .domain import identifier
from .operations import Operations


class OpenOrder(Contract):
    name: str = Field(min_length=1, max_length=160)
    operation_id: str = Field(pattern=r'^operation_[a-f0-9]{32}$')
    rule_id: str = Field(min_length=1, max_length=60)
    event_index: StrictInt = Field(ge=0, le=199)
    minimum_observation_seconds: StrictFloat = Field(gt=0, le=604800)
    observation_basis: str = Field(min_length=20, max_length=2000)
    responsible_person: str = Field(min_length=2, max_length=160)


class OrderAction(Contract):
    expected_revision: StrictInt = Field(gt=0)
    action: Literal['triage', 'record_work', 'recheck', 'close', 'reopen']
    note: str = Field(min_length=20, max_length=4000)
    responsible_person: str = Field(min_length=2, max_length=160)
    evidence_ids: list[str] = Field(default_factory=list, max_length=20)
    work_completed_at: str | None = Field(default=None, max_length=80)
    after_operation_id: str | None = Field(default=None, pattern=r'^operation_[a-f0-9]{32}$')
    same_equipment_and_conditions: StrictBool = False

    @model_validator(mode='after')
    def scope(self):
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError('Duplicate evidence ID')
        if (self.action == 'record_work') != (self.work_completed_at is not None):
            raise ValueError('Only record_work requires work completion time')
        if (self.action == 'recheck') != (self.after_operation_id is not None):
            raise ValueError('Only recheck requires a new operation record')
        if self.action in {'record_work', 'close'} and not self.evidence_ids:
            raise ValueError('Work and closure require explicit supporting evidence')
        if self.action == 'close' and not self.same_equipment_and_conditions:
            raise ValueError('Closure requires explicit equipment and condition review')
        if self.action != 'close' and self.same_equipment_and_conditions:
            raise ValueError('Condition confirmation belongs to closure only')
        return self


def version():
    return core.hash_json({p.name:core.sha(p) for p in (Path(__file__), Path(maintenance_recheck.__file__))})


class Maintenance:
    def __init__(self, domain):
        self.domain, self.store = domain, domain.store
        self.operations = Operations(domain)

    def _operation(self, pid, oid):
        r = self.operations.view(pid, oid)
        if r['status'] == 'stale' or r['result'] is None:
            raise core.ValidationError('Current operation evidence required')
        return r

    def _evidence(self, pid, ids):
        result = []
        for eid in ids:
            e = self.store.get('evidence', eid)
            if e['project_id'] != pid or e['review_state'] == 'rejected':
                raise core.ValidationError('Foreign or withdrawn maintenance evidence')
            if e.get('source_file'):
                self.domain.file_record(pid, e['source_file'])
            result.append(e)
        return result

    def _read(self, pid, mid):
        r = self.store.get('maintenance', mid)
        if r['project_id'] != pid:
            raise core.ValidationError('Cross-project work order rejected')
        if core.hash_json({k:v for k,v in r.items() if k not in {'hash', 'revision'}}) != r['hash']:
            raise core.ValidationError('Maintenance record integrity failed')
        return r

    def _stale(self, r):
        reasons = []
        if r['calculator_version'] != version():reasons.append('calculator_version')
        if self.store.get('project', r['project_id'])['revision'] != r['project_revision']:reasons.append('project_revision')
        for old in r['operation_snapshots']:
            try:
                current = self._operation(r['project_id'], old['operation_id'])
                if current['hash'] != old['hash']:reasons.append(old['operation_id']+':changed')
            except (KeyError, ValueError, OSError):reasons.append(old['operation_id']+':unavailable')
        for old in r['evidence_snapshots']:
            try:
                current = self._evidence(r['project_id'], [old['evidence_id']])[0]
                if (current['revision'],current['hash']) != (old['revision'],old['hash']):
                    reasons.append(old['evidence_id']+':changed')
            except (KeyError, ValueError, OSError):reasons.append(old['evidence_id']+':unavailable')
        return reasons

    def view(self, pid, mid):
        r = self._read(pid, mid); reasons = self._stale(r)
        return {**r, 'status':'stale' if reasons else r['state'], 'stale_reasons':reasons,
                'recheck':None if reasons else r.get('recheck'),
                'history_notice':'Actions preserve historical user statements; only the current recheck field is current evidence.',
                'equipment_health':'NOT_ASSESSED', 'cause_confirmed':False}

    def _put(self, con, record, expected):
        reasons = self._stale(record)
        if reasons:raise core.ValidationError('Maintenance sources changed: '+', '.join(reasons))
        record.pop('hash',None);record.pop('revision',None)
        record['hash'] = core.hash_json(record)
        return self.store.put_in(con, 'maintenance', record, expected)

    def create(self, pid, body, actor):
        with self.store.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            baseline = self._operation(pid, body.operation_id)
            _, event = maintenance_recheck.select_event(baseline, body.rule_id, body.event_index)
            if baseline['input']['clock_basis'] != 'offset_aware':
                raise core.ValidationError('Maintenance chronology requires offset-aware source times')
            record = {'maintenance_id':identifier('maintenance'), 'project_id':pid,
                'project_revision':self.store.get('project',pid)['revision'], 'input':body.model_dump(),
                'equipment':baseline['input']['equipment'], 'data_nature':baseline['input']['data_nature'],
                'source_event':event,'state':'open','recheck':None,'work_completed_at':None,
                'operation_snapshots':[{'operation_id':baseline['operation_id'],'hash':baseline['hash']}],
                'evidence_snapshots':[], 'created_at':core.now(), 'calculator_version':version(),
                'actions':[{'action':'open','actor_user_id':actor,'responsible_person':body.responsible_person,'at':core.now()}]}
            self._put(con, record, 0)
        return self.view(pid, record['maintenance_id'])

    def act(self, pid, mid, body, actor):
        allowed = {'triage':{'open'}, 'record_work':{'triaged','work_recorded','recheck_failed'},
                   'recheck':{'work_recorded','recheck_failed','rechecked'}, 'close':{'rechecked'},
                   'reopen':{'closed_under_declared_rule'}}
        with self.store.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            record = copy.deepcopy(self._read(pid, mid))
            if record['revision'] != body.expected_revision:
                raise core.ValidationError('Revision conflict; refresh work order')
            if self._stale(record):raise core.ValidationError('Stale work order; retain history and create a new reviewed order')
            if record['state'] not in allowed[body.action]:raise core.ValidationError('Invalid maintenance state transition')
            if len(record['actions']) >= 100:raise core.ValidationError('Work order action limit reached')
            for e in self._evidence(pid, body.evidence_ids):
                if e['evidence_id'] not in {x['evidence_id'] for x in record['evidence_snapshots']}:
                    record['evidence_snapshots'].append(e)
            if body.action == 'triage':record['state'] = 'triaged'
            elif body.action == 'record_work':
                completed = maintenance_recheck.instant(body.work_completed_at)
                if completed < maintenance_recheck.instant(record['source_event']['end']):
                    raise core.ValidationError('Work completion precedes source event')
                record.update(state='work_recorded',work_completed_at=body.work_completed_at,recheck=None)
            elif body.action == 'recheck':
                before = self._operation(pid,record['input']['operation_id']);after = self._operation(pid,body.after_operation_id)
                result = maintenance_recheck.assess(before,after,record['input']['rule_id'],record['input']['event_index'],record['work_completed_at'],record['input']['minimum_observation_seconds'])
                record.update(recheck=result,state='rechecked' if result['eligible_for_human_closure'] else 'recheck_failed')
                if after['operation_id'] not in {r['operation_id'] for r in record['operation_snapshots']}:
                    record['operation_snapshots'].append({'operation_id':after['operation_id'],'hash':after['hash']})
            elif body.action == 'close':
                if not record['recheck'] or not record['recheck']['eligible_for_human_closure']:
                    raise core.ValidationError('No eligible current rule recheck')
                record['state'] = 'closed_under_declared_rule'
            else:record.update(state='triaged',recheck=None,work_completed_at=None)
            record['actions'].append({**body.model_dump(exclude={'expected_revision'}), 'actor_user_id':actor,'at':core.now()})
            self._put(con,record,body.expected_revision)
        return self.view(pid,mid)


def report(record):
    esc = lambda value: html.escape(str(value))
    return ('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>运维处置与规则复验</title>'
        '<h1>'+esc(record['input']['name'])+'</h1><p>状态：'+esc(record['status'])+'</p>'
        '<p>人工处置记录及限定窗口规则复验；不是设备健康、根因确诊或维修认证。资料性质：'+esc(record['data_nature'])+'</p>'
        '<p>旧动作属于历史记录；当前失效时不得将历史复验作为当前结论。</p><pre style="white-space:pre-wrap;overflow-wrap:anywhere">'+
        esc(json.dumps(record,ensure_ascii=False,indent=2))+'</pre></html>')


def register(app, domain):
    service = Maintenance(domain)
    @app.post('/api/projects/{project_id}/maintenance-orders',status_code=201)
    def create(project_id:str,body:OpenOrder,request:Request):
        return service.create(project_id,body,request.state.user['id'])
    @app.get('/api/projects/{project_id}/maintenance-orders')
    def history(project_id:str):
        return [service.view(project_id,r['maintenance_id']) for r in domain.store.list('maintenance',project_id)]
    @app.get('/api/projects/{project_id}/maintenance-orders/{maintenance_id}')
    def view(project_id:str,maintenance_id:str):
        return service.view(project_id,maintenance_id)
    @app.post('/api/projects/{project_id}/maintenance-orders/{maintenance_id}/actions')
    def action(project_id:str,maintenance_id:str,body:OrderAction,request:Request):
        return service.act(project_id,maintenance_id,body,request.state.user['id'])
    @app.get('/api/projects/{project_id}/maintenance-orders/{maintenance_id}/report.html',response_class=HTMLResponse)
    def html_report(project_id:str,maintenance_id:str):
        return report(service.view(project_id,maintenance_id))
