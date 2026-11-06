"""Execute only user-supplied, typed inputs; model arguments select a frozen key."""
from typing import Annotated, Literal

from pydantic import Field

from . import core
from .schema import Contract
from .thermal import Assembly
from .lifecycle import Inventory
from .material_cost import Estimate
from .engineering import BeamInput
from .construction import ScheduleInput
from .operations import AnalysisInput
from .agent_semantics import inspection


class ThermalPlan(Contract):
    plan_key: str = Field(pattern=r'^[A-Za-z0-9_-]{1,40}$')
    kind: Literal['thermal']
    input: Assembly


class LifecyclePlan(Contract):
    plan_key: str = Field(pattern=r'^[A-Za-z0-9_-]{1,40}$')
    kind: Literal['lifecycle']
    input: Inventory


class CostPlan(Contract):
    plan_key: str = Field(pattern=r'^[A-Za-z0-9_-]{1,40}$')
    kind: Literal['cost']
    input: Estimate


class EngineeringPlan(Contract):
    plan_key: str = Field(pattern=r'^[A-Za-z0-9_-]{1,40}$')
    kind: Literal['engineering']
    input: BeamInput


class SchedulePlan(Contract):
    plan_key: str = Field(pattern=r'^[A-Za-z0-9_-]{1,40}$')
    kind: Literal['schedule']
    input: ScheduleInput


class OperationPlan(Contract):
    plan_key: str = Field(pattern=r'^[A-Za-z0-9_-]{1,40}$')
    kind: Literal['operation']
    input: AnalysisInput


CalculationPlan = Annotated[ThermalPlan | LifecyclePlan | CostPlan | EngineeringPlan | SchedulePlan | OperationPlan, Field(discriminator='kind')]


def bindings(domain, pid, plan):
    """Bind project and attached evidence at submission, recheck before each write."""
    project = domain.store.get('project', pid)
    body = plan.input
    if plan.kind == 'thermal':
        ids = {row.evidence_id for row in body.layers if row.evidence_id}
    elif plan.kind == 'lifecycle':
        ids = {row.factor.evidence_id for row in body.activities if row.factor.evidence_id}
    elif plan.kind == 'cost':
        ids = {eid for row in body.lines for eid in row.evidence_ids}
    else:
        ids = set(body.evidence_ids)
    files = set()
    if plan.kind == 'operation':
        files.add(body.file_id)
    if getattr(body, 'import_file_id', None):
        files.add(body.import_file_id)
    sources = []
    for eid in sorted(ids):
        ev = domain.store.get('evidence', eid)
        if ev['project_id'] != pid or ev['review_state'] == 'rejected':
            raise core.ValidationError('Foreign or rejected calculation-plan evidence')
        sources.append({'evidence_id': eid, 'revision': ev['revision'], 'hash': ev['hash']})
        if ev['source_file']:
            files.add(ev['source_file'])
    file_records = [domain.file_record(pid, fid)[0] for fid in sorted(files)]
    return {'project_revision': project['revision'], 'sources': sources,
            'files_hash': core.hash_json(file_records)}


def snapshot(domain, pid, plans):
    items = [{'plan': p.model_dump(mode='json'), 'bindings': bindings(domain, pid, p)} for p in plans]
    return {'items': items, 'hash': core.hash_json(items)}


def execute(domain, pid, key, plans, frozen):
    if not frozen or core.hash_json(frozen['items']) != frozen['hash']:
        raise core.ValidationError('Calculation plan snapshot integrity failed')
    plan = next((p for p in plans if p.plan_key == key), None)
    saved = next((p for p in frozen['items'] if p['plan']['plan_key'] == key), None)
    if not plan or not saved or saved['plan'] != plan.model_dump(mode='json'):
        raise core.ValidationError('Select an explicit user calculation plan; do not invent parameters')
    if bindings(domain, pid, plan) != saved['bindings']:
        raise core.ValidationError('Project or calculation-plan sources changed; submit a new reviewed plan')
    spec = inspection(plan.kind)
    record = spec.service(domain).save(pid, plan.input)
    return {'plan_key': key, 'kind': plan.kind, 'record_id': record[spec.record_key],
            'record_hash': record['hash'], 'status': record['status'], 'input_hash': core.hash_json(saved['plan']['input']),
            'next_tool': spec.read_tool, 'next_arguments': {spec.argument: record[spec.record_key]},
            'notice': '已保存真实计算记录；需读取当前结果并交付核验事实。保存成功不等于结果完整、来源独立核证或任务完成。'}


def progress(record, answer):
    """Saved writes remain visible on partial/failure; current validity needs a read."""
    verified = {a.get('record_id') or a.get('cost_id') for a in (answer or {}).get('artifacts', []) if a.get('verified')}
    limited = {x['record_id'] for x in (answer or {}).get('checked_limitations', [])}
    fields = {x['record_id'] for x in (answer or {}).get('checked_statements', []) if x['facts']}
    rows = []
    for item in record.get('calculation_plan_snapshot', {}).get('items', []):
        plan = item['plan']
        events = [e for e in record['events'] if e['tool'] == 'calculation_execute'
                  and e['status'] == 'succeeded' and e.get('result', {}).get('plan_key') == plan['plan_key']]
        result = events[-1]['result'] if events else {}
        rows.append({'plan_key': plan['plan_key'], 'kind': plan['kind'], 'name': plan['input']['name'],
                     'record_id': result.get('record_id'),
                     'state': 'verified' if result.get('record_id') in verified else 'limits_verified' if result.get('record_id') in limited else 'fields_verified' if result.get('record_id') in fields else 'saved_unverified' if result else 'not_executed'})
    return rows
