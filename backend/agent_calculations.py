"""Execute only user-supplied, typed inputs; model arguments select a frozen key."""
from typing import Annotated, Literal

from pydantic import Field, StrictBool

from . import core
from .schema import Contract
from .thermal import Assembly
from .lifecycle import Inventory
from .material_cost import Estimate
from .engineering import BeamInput
from .construction import ScheduleInput
from .operations import AnalysisInput
from .agent_semantics import inspection


class PlanAuthorization(Contract):
    execution_authorized: StrictBool = Field(default=True,
        description='False retains a deferred plan without permitting execution. Omitted means authorized by this request; natural-language conditions are not access control.')


class ThermalPlan(PlanAuthorization):
    plan_key: str = Field(pattern=r'^[A-Za-z0-9_-]{1,40}$')
    kind: Literal['thermal']
    input: Assembly


class LifecyclePlan(PlanAuthorization):
    plan_key: str = Field(pattern=r'^[A-Za-z0-9_-]{1,40}$')
    kind: Literal['lifecycle']
    input: Inventory


class CostPlan(PlanAuthorization):
    plan_key: str = Field(pattern=r'^[A-Za-z0-9_-]{1,40}$')
    kind: Literal['cost']
    input: Estimate


class EngineeringPlan(PlanAuthorization):
    plan_key: str = Field(pattern=r'^[A-Za-z0-9_-]{1,40}$')
    kind: Literal['engineering']
    input: BeamInput


class SchedulePlan(PlanAuthorization):
    plan_key: str = Field(pattern=r'^[A-Za-z0-9_-]{1,40}$')
    kind: Literal['schedule']
    input: ScheduleInput


class OperationPlan(PlanAuthorization):
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


def resolve(domain, pid, key, plans, frozen):
    """Side-effect-free validation, also used to preflight a selected plan batch."""
    if not frozen or core.hash_json(frozen['items']) != frozen['hash']:
        raise core.ValidationError('Calculation plan snapshot integrity failed')
    plan = next((p for p in plans if p.plan_key == key), None)
    saved = next((p for p in frozen['items'] if p['plan']['plan_key'] == key), None)
    if not plan or not saved or saved['plan'] != plan.model_dump(mode='json'):
        raise core.ValidationError('Select an explicit user calculation plan; do not invent parameters')
    if not plan.execution_authorized:
        raise core.ValidationError('Plan execution is not authorized; submit a new explicitly authorized request')
    if bindings(domain, pid, plan) != saved['bindings']:
        raise core.ValidationError('Project or calculation-plan sources changed; submit a new reviewed plan')
    return plan, saved


def execute(domain, pid, key, plans, frozen):
    plan, saved = resolve(domain, pid, key, plans, frozen)
    spec = inspection(plan.kind)
    record = spec.service(domain).save(pid, plan.input, expected_bindings=saved['bindings'])
    return {'plan_key': key, 'kind': plan.kind, 'record_id': record[spec.record_key],
            'record_hash': record['hash'], 'status': record['status'], 'input_hash': core.hash_json(saved['plan']['input']),
            'next_tool': spec.read_tool, 'next_arguments': {spec.argument: record[spec.record_key]},
            'notice': '已保存真实计算记录；需读取当前结果并交付核验事实。保存成功不等于结果完整、来源独立核证或任务完成。'}


def execution_stages(record):
    """Task-local tool history, not a claim that the full user request is satisfied."""
    delivered = {d['record_id'] for d in record.get('professional_deliveries', [])}
    rows = []
    for item in record.get('calculation_plan_snapshot', {}).get('items', []):
        plan = item['plan'];spec = inspection(plan['kind'])
        executions = [e['result'] for e in record['events'] if e['tool']=='calculation_execute'
                      and e['status']=='succeeded' and e['result']['plan_key']==plan['plan_key']]
        result = executions[-1] if executions else {}
        ident = result.get('record_id')
        read = bool(ident and any(e['tool']==spec.read_tool and e['status']=='succeeded'
                    and e['result'][spec.record_key]==ident for e in record['events']))
        stage = 'not_authorized' if not plan.get('execution_authorized', True) else 'delivery_submitted' if ident in delivered else 'awaiting_delivery' if read else 'awaiting_read' if ident else 'not_executed'
        rows.append({'plan_key':plan['plan_key'], 'kind':plan['kind'], 'record_id':ident, 'stage':stage})
    return rows


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
                     'state': 'not_authorized' if not plan.get('execution_authorized', True) else 'verified' if result.get('record_id') in verified else 'limits_verified' if result.get('record_id') in limited else 'fields_verified' if result.get('record_id') in fields else 'saved_unverified' if result else 'not_executed'})
    return rows
