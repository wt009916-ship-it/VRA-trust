"""Explicit-boundary CO2e inventories, not certification or tradable carbon assets."""
import html
import json
import math
import uuid
from pathlib import Path
from typing import Literal
from pydantic import Field, StrictFloat, StrictInt, model_validator
from . import core
from .schema import Contract

Stage = Literal['production', 'transport', 'construction', 'operation', 'end_of_life']
STAGES = {'production', 'transport', 'construction', 'operation', 'end_of_life'}
Unit = Literal['kg', 't', 'tkm', 'kWh', 'm3', 'm2', 'item']
UNITS = {'kg': ('mass', 1), 't': ('mass', 1000), 'tkm': ('transport', 1),
         'kWh': ('energy', 1), 'm3': ('volume', 1), 'm2': ('area', 1), 'item': ('count', 1)}


class Boundary(Contract):
    stage: Stage
    included: bool
    reason: str = Field(min_length=5, max_length=1000)


class EmissionFactor(Contract):
    factor_id: str = Field(min_length=1, max_length=100)
    value: StrictFloat | None = Field(default=None, ge=0, le=1e12)
    denominator: Unit
    numerator: Literal['kgCO2e'] = 'kgCO2e'
    stage: Stage
    source: str = Field(min_length=5, max_length=2000)
    publisher: str = Field(min_length=2, max_length=200)
    version: str = Field(min_length=1, max_length=100)
    year: StrictInt = Field(ge=1900, le=2100)
    region: str = Field(min_length=1, max_length=100)
    method: str = Field(min_length=3, max_length=300)
    evidence_id: str | None = None


class Activity(Contract):
    activity_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    stage: Stage
    quantity: StrictFloat | None = Field(default=None, ge=0, le=1e15)
    unit: Unit
    period: Literal['whole_period', 'annual']
    source: str = Field(min_length=5, max_length=2000)
    factor: EmissionFactor

    @model_validator(mode='after')
    def dimensions(self):
        if self.stage != self.factor.stage:
            raise ValueError('Factor stage does not match activity stage')
        if UNITS[self.unit][0] != UNITS[self.factor.denominator][0]:
            raise ValueError('Activity and factor units are incompatible; density/conversion cannot be invented')
        if self.period == 'annual' and self.stage != 'operation':
            raise ValueError('Annual repetition is only supported for operation; other stages require whole-period quantities')
        return self


class Inventory(Contract):
    name: str = Field(min_length=1, max_length=160)
    area_m2: StrictFloat = Field(gt=0, le=1e7)
    study_years: StrictInt = Field(gt=0, le=200)
    region: str = Field(min_length=1, max_length=100)
    method: str = Field(min_length=3, max_length=300)
    functional_unit: str = Field(min_length=5, max_length=1000)
    boundaries: list[Boundary] = Field(min_length=5, max_length=5)
    activities: list[Activity] = Field(max_length=500)

    @model_validator(mode='after')
    def consistent(self):
        if {b.stage for b in self.boundaries} != STAGES:
            raise ValueError('Declare each of the five stages exactly once')
        included = {b.stage for b in self.boundaries if b.included}
        if not included:
            raise ValueError('At least one stage must be included')
        if len({a.activity_id for a in self.activities}) != len(self.activities):
            raise ValueError('Duplicate activity ID; double counting rejected')
        factors = {}
        for a in self.activities:
            if a.stage not in included:
                raise ValueError('Activity conflicts with excluded boundary')
            if a.factor.region not in {self.region, '*'} or a.factor.method != self.method:
                raise ValueError('Factor region or assessment method mismatch')
            payload = a.factor.model_dump()
            if a.factor.factor_id in factors and factors[a.factor.factor_id] != payload:
                raise ValueError('Same factor ID has inconsistent value, version or source')
            factors[a.factor.factor_id] = payload
        return self


def finite(value):
    if not math.isfinite(value) or value < 0:
        raise core.ValidationError('Non-finite or negative inventory result')
    return value


def calculate(body):
    rows, missing, stages = [], [], {}
    for a in body.activities:
        multiplier = body.study_years if a.period == 'annual' else 1
        normalized = None if a.quantity is None else finite(a.quantity*UNITS[a.unit][1]/UNITS[a.factor.denominator][1]*multiplier)
        result = None if normalized is None or a.factor.value is None else finite(normalized*a.factor.value)
        if result is None:
            missing.append(a.activity_id)
        rows.append({'activity_id': a.activity_id, 'stage': a.stage, 'quantity_in_factor_unit': normalized,
            'factor_unit': 'kgCO2e/'+a.factor.denominator, 'period_multiplier': multiplier,
            'kgco2e': result, 'formula': 'quantity * unit_conversion * period_multiplier * factor'})
    for b in body.boundaries:
        selected = [r for r in rows if r['stage'] == b.stage]
        complete = bool(selected) and all(r['kgco2e'] is not None for r in selected)
        if b.included and not selected:
            missing.append(b.stage+':no_activities')
        stages[b.stage] = {'included': b.included, 'reason': b.reason,
            'status': 'excluded' if not b.included else 'calculated' if complete else 'incomplete',
            'kgco2e': finite(math.fsum(r['kgco2e'] for r in selected)) if b.included and complete else None}
    complete = not missing
    total = finite(math.fsum(s['kgco2e'] for s in stages.values() if s['included'])) if complete else None
    all_stages = all(b.included for b in body.boundaries)
    return {'status': 'calculated' if complete else 'incomplete', 'rows': rows, 'stages': stages, 'missing': missing,
        'boundary_total_kgco2e': total, 'kgco2e_m2_over_study_period': None if total is None else finite(total/body.area_m2),
        'all_five_stages_entered': all_stages and complete, 'source_status': 'USER_DECLARED',
        'certification': 'NOT_ASSESSED', 'issued_credits_t': None,
        'limitations': ['五阶段通用活动清单，不自动证明符合某项LCA标准；阶段覆盖完整也不证明清单无遗漏。',
            'CO2e因子需方法、版本、地区一致；人工填写来源不等于独立核证。',
            '年运行量仅按评估年限线性重复；不预测电网因子变化、设备衰减或替换周期。',
            '不支持负排放、抵扣或边界外收益合并；核算结果不能直接作为可交易碳资产。']}


class Lifecycle:
    def __init__(self, domain):
        self.domain, self.store = domain, domain.store

    def save(self, pid, body):
        project = self.store.get('project', pid)
        if body.region != project['building']['region'] or not math.isclose(body.area_m2, project['building']['area_m2'], rel_tol=1e-9):
            raise core.ValidationError('Inventory region/area must match current project declaration')
        evidence = []
        for eid in sorted({a.factor.evidence_id for a in body.activities if a.factor.evidence_id}):
            ev = self.store.get('evidence', eid)
            if ev['project_id'] != pid:
                raise core.ValidationError('Cross-project lifecycle evidence rejected')
            if ev['source_file']:
                self.domain.file_record(pid, ev['source_file'])
            evidence.append(ev)
        obj = {'lifecycle_id': 'lifecycle_'+uuid.uuid4().hex, 'project_id': pid, 'project_revision': project['revision'],
            'input': body.model_dump(), 'result': calculate(body), 'source_snapshot': evidence,
            'calculator_hash': core.sha(Path(__file__)), 'created_at': core.now()}
        obj['hash'] = core.hash_json(obj)
        self.store.put('lifecycle', obj)
        return self.view(pid, obj['lifecycle_id'])

    def view(self, pid, lid):
        obj = self.store.get('lifecycle', lid)
        if obj['project_id'] != pid:
            raise core.ValidationError('Cross-project lifecycle record rejected')
        if core.hash_json({k:v for k,v in obj.items() if k not in {'hash','revision'}}) != obj['hash']:
            raise core.ValidationError('Lifecycle record integrity failed')
        stale = obj['calculator_hash'] != core.sha(Path(__file__)) or obj['project_revision'] != self.store.get('project',pid)['revision']
        for old in obj['source_snapshot']:
            ev = self.store.get('evidence', old['evidence_id'])
            stale |= ev['revision'] != old['revision'] or ev['hash'] != old['hash']
            if ev['source_file']:
                try:
                    self.domain.file_record(pid, ev['source_file'])
                except (OSError, ValueError, KeyError):
                    stale = True
        return {**obj, 'status': 'stale' if stale else obj['result']['status'], 'result': None if stale else obj['result']}


def report(record):
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>阶段化碳清单</title><h1>阶段化碳清单 · 未核证</h1><p>不是完整性认证或碳资产凭证。</p><pre style="white-space:pre-wrap;overflow-wrap:anywhere">'+html.escape(json.dumps(record,ensure_ascii=False,indent=2,allow_nan=False))+'</pre></html>'


class Comparison(Contract):
    lifecycle_ids: list[str] = Field(min_length=2, max_length=5)


def compare(service, pid, body):
    if len(set(body.lifecycle_ids)) != len(body.lifecycle_ids):
        raise core.ValidationError('Distinct inventories required')
    records = [service.view(pid, lid) for lid in body.lifecycle_ids]
    if any(r['status'] != 'calculated' for r in records):
        raise core.ValidationError('Only complete current inventories can be compared')
    def context(r):
        b = r['input']
        return {k:b[k] for k in ('area_m2','study_years','region','method','functional_unit')} | {
            'included': sorted(s['stage'] for s in b['boundaries'] if s['included'])}
    if any(context(r) != context(records[0]) for r in records[1:]):
        raise core.ValidationError('Comparison requires identical functional unit, period, method and boundary')
    baseline = records[0]['result']['boundary_total_kgco2e']
    def percentage(value):
        if baseline == 0:
            return None
        result = (1-value/baseline)*100
        if not math.isfinite(result):
            raise core.ValidationError('Comparison percentage overflow; inspect input scale')
        return result
    return {'baseline_id': body.lifecycle_ids[0], 'results': [{'lifecycle_id':r['lifecycle_id'],
        'kgco2e':r['result']['boundary_total_kgco2e'], 'reduction_kgco2e':baseline-r['result']['boundary_total_kgco2e'],
        'reduction_pct':percentage(r['result']['boundary_total_kgco2e'])} for r in records],
        'note': '仅比较相同声明边界下的清单；未验证材料功能等效性，不构成最优推荐或碳资产核证。'}
