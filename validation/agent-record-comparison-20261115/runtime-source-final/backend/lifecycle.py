"""Explicit-boundary CO2e inventories, not certification or tradable carbon assets."""
import html
import json
import math
import uuid
from fractions import Fraction
from pathlib import Path
from typing import Literal
from pydantic import Field, StrictFloat, StrictInt, model_validator
from .calculation_provenance import validity, persist, version as provenance_version
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
    replacement_overlap: Literal['unknown', 'excluded', 'included'] = 'unknown'
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



# A bounded, explicitly declared B4-style scenario, not an automatic standards claim.
PROCESS_STAGES = {'production': 'production', 'transport': 'transport',
                  'installation': 'construction', 'removal': 'end_of_life'}


class ReplacementProcess(Contract):
    process: Literal['production', 'transport', 'installation', 'removal']
    included: bool
    reason: str = Field(min_length=5, max_length=1000)
    activity: Activity | None = None

    @model_validator(mode='after')
    def scope(self):
        if not self.included and self.activity is not None:
            raise ValueError('Excluded replacement process cannot carry an activity')
        if self.activity and (self.activity.stage != PROCESS_STAGES[self.process] or self.activity.period != 'whole_period'):
            raise ValueError('Replacement process requires matching stage and one-event quantity, never annual')
        return self


class ReplacementComponent(Contract):
    component_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    condition: Literal['new', 'existing']
    service_life_years: StrictFloat | None = Field(default=None, gt=0, le=1000)
    remaining_life_years: StrictFloat | None = Field(default=None, gt=0, le=1000)
    life_source: str = Field(min_length=5, max_length=2000)
    life_evidence_id: str | None = Field(default=None, pattern=r'^evidence_[a-f0-9]{32}$')
    endpoint: Literal['strictly_before_horizon']
    scope: Literal['same_function_replacements_only']
    overlap_review: str = Field(min_length=20, max_length=2000)
    processes: list[ReplacementProcess] = Field(min_length=4, max_length=4)

    @model_validator(mode='after')
    def consistent(self):
        if {p.process for p in self.processes} != set(PROCESS_STAGES):
            raise ValueError('Declare all four replacement processes exactly once')
        if self.condition == 'new' and self.remaining_life_years is not None:
            raise ValueError('New component uses service life; remaining life is only for existing components')
        if not any(p.included for p in self.processes):
            raise ValueError('At least one replacement process must be included')
        ids = [p.activity.activity_id for p in self.processes if p.activity]
        if len(ids) != len(set(ids)):
            raise ValueError('Duplicate replacement activity ID')
        return self


def replacement_years(component, horizon):
    first = component.service_life_years if component.condition == 'new' else component.remaining_life_years
    if first is None or component.service_life_years is None:
        return None
    # Exact rational arithmetic from the declared decimal values avoids endpoint drift.
    first, step, end = Fraction(str(first)), Fraction(str(component.service_life_years)), Fraction(horizon)
    distance = (end - first) / step
    count = max(0, -(-distance.numerator // distance.denominator))
    if count > 1000:
        raise ValueError('Replacement scenario exceeds 1000 events per component')
    return [float(first + step * i) for i in range(count)]


def all_activities(body):
    return list(body.activities) + [p.activity for c in body.replacements for p in c.processes if p.activity]


def evidence_ids(body):
    return ({a.factor.evidence_id for a in all_activities(body) if a.factor.evidence_id}
            | {c.life_evidence_id for c in body.replacements if c.life_evidence_id})


def replacement_calculate(body):
    components, missing = [], []
    for component in body.replacements:
        years = replacement_years(component, body.study_years)
        gaps = [] if years is not None else ['service_or_remaining_life']
        processes = []
        for process in component.processes:
            a = process.activity
            normalized = None if a is None or a.quantity is None else finite(a.quantity * UNITS[a.unit][1] / UNITS[a.factor.denominator][1])
            value = None if normalized is None or a.factor.value is None else finite(normalized * a.factor.value)
            if process.included and value is None:
                gaps.append(process.process)
            processes.append({'process': process.process, 'included': process.included, 'reason': process.reason,
                              'quantity_in_factor_unit': normalized, 'kgco2e_per_event': value,
                              'status': 'excluded' if not process.included else 'incomplete' if value is None else 'calculated'})
        per_event = None if any(x['included'] and x['kgco2e_per_event'] is None for x in processes) else finite(math.fsum(x['kgco2e_per_event'] for x in processes if x['included']))
        total = None if gaps else finite(per_event * len(years))
        missing += [component.component_id + ':' + gap for gap in gaps]
        components.append({'component_id': component.component_id, 'name': component.name,
                           'status': 'incomplete' if gaps else 'calculated', 'years': years,
                           'count': None if years is None else len(years), 'processes': processes,
                           'kgco2e_per_event': per_event, 'kgco2e': total,
                           'events': None if years is None else [{'year': y, 'kgco2e': per_event} for y in years],
                           'all_four_processes_included': all(p.included for p in component.processes)})
    return {'scope': body.replacement_scope, 'components': components, 'missing': missing,
            'total_kgco2e': None if missing or not components else finite(math.fsum(c['kgco2e'] for c in components)),
            'status': 'not_separately_assessed' if not components else 'incomplete' if missing else 'calculated',
            'aggregation': 'Replacement ledger is added to operation stage; initial installation and horizon disposal remain in base activities.'}


class Inventory(Contract):
    name: str = Field(min_length=1, max_length=160)
    area_m2: StrictFloat = Field(gt=0, le=1e7)
    study_years: StrictInt = Field(gt=0, le=200)
    region: str = Field(min_length=1, max_length=100)
    method: str = Field(min_length=3, max_length=300)
    functional_unit: str = Field(min_length=5, max_length=1000)
    import_file_id: str | None = Field(default=None, pattern=r'^file_[a-f0-9]{32}$')
    boundaries: list[Boundary] = Field(min_length=5, max_length=5)
    activities: list[Activity] = Field(max_length=500)
    replacement_scope: Literal['not_assessed', 'included_in_activities', 'separate_ledger'] = 'not_assessed'
    replacements: list[ReplacementComponent] = Field(default_factory=list, max_length=50)

    @model_validator(mode='after')
    def consistent(self):
        if {b.stage for b in self.boundaries} != STAGES:
            raise ValueError('Declare each of the five stages exactly once')
        included = {b.stage for b in self.boundaries if b.included}
        if not included:
            raise ValueError('At least one stage must be included')
        if len({a.activity_id for a in self.activities}) != len(self.activities):
            raise ValueError('Duplicate activity ID; double counting rejected')
        if self.replacements and self.replacement_scope != 'separate_ledger':
            raise ValueError('Separate replacement ledger conflicts with base replacement scope')
        if self.replacement_scope == 'separate_ledger':
            if not self.replacements or 'operation' not in included:
                raise ValueError('Separate replacements require components and included operation boundary')
            if any(a.replacement_overlap != 'excluded' for a in self.activities):
                raise ValueError('Review every base activity: replacement overlap must be explicitly excluded')
        if len({c.component_id for c in self.replacements}) != len(self.replacements):
            raise ValueError('Duplicate replacement component ID')
        if sum(len(replacement_years(c, self.study_years) or []) for c in self.replacements) > 5000:
            raise ValueError('Replacement scenario exceeds 5000 events in total')
        factors = {}
        for a in self.activities:
            if a.stage not in included:
                raise ValueError('Activity conflicts with excluded boundary')
        for a in all_activities(self):
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
    replacement = replacement_calculate(body)
    missing += ['replacement:' + x for x in replacement['missing']]
    for b in body.boundaries:
        selected = [r for r in rows if r['stage'] == b.stage]
        base_selected = list(selected)
        if b.stage == 'operation' and body.replacements:
            selected = selected + [{'kgco2e': replacement['total_kgco2e']}]
        complete = bool(selected) and all(r['kgco2e'] is not None for r in selected)
        if b.included and not selected:
            missing.append(b.stage+':no_activities')
        stages[b.stage] = {'included': b.included, 'reason': b.reason,
            'base_activity_kgco2e': finite(math.fsum(r['kgco2e'] for r in base_selected)) if b.included and base_selected and all(r['kgco2e'] is not None for r in base_selected) else None,
            'replacement_kgco2e': replacement['total_kgco2e'] if b.stage == 'operation' and body.replacements else None,
            'status': 'excluded' if not b.included else 'calculated' if complete else 'incomplete',
            'kgco2e': finite(math.fsum(r['kgco2e'] for r in selected)) if b.included and complete else None}
    complete = not missing
    total = finite(math.fsum(s['kgco2e'] for s in stages.values() if s['included'])) if complete else None
    all_stages = all(b.included for b in body.boundaries)
    return {'status': 'calculated' if complete else 'incomplete', 'replacement': replacement, 'rows': rows, 'stages': stages, 'missing': missing,
        'boundary_total_kgco2e': total, 'kgco2e_m2_over_study_period': None if total is None else finite(total/body.area_m2),
        'all_five_stages_entered': all_stages and complete, 'source_status': 'USER_DECLARED',
        'certification': 'NOT_ASSESSED', 'issued_credits_t': None,
        'limitations': ['五阶段通用活动清单，不自动证明符合某项LCA标准；阶段覆盖完整也不证明清单无遗漏。',
            'CO2e因子需方法、版本、地区一致；人工填写来源不等于独立核证。',
            '年运行量线性累计；替换仅按声明寿命离散发生，因子按当前版本固定，不预测电网、衰减或未来技术。',
            '替换账列入使用阶段，逐项排除初次安装和评估终点处置；声明不重叠不等于独立证明没有重复计数。',
            'replacement_scope=not_assessed 表示未评估替换；即使五阶段有值也不代表完整生命周期。',
            '不支持负排放、抵扣或边界外收益合并；核算结果不能直接作为可交易碳资产。']}


class Lifecycle:
    def __init__(self, domain):
        self.domain, self.store = domain, domain.store

    def save(self, pid, body, *, expected_bindings=None):
        project = self.store.get('project', pid)
        if body.region != project['building']['region'] or not math.isclose(body.area_m2, project['building']['area_m2'], rel_tol=1e-9):
            raise core.ValidationError('Inventory region/area must match current project declaration')
        evidence = []
        imported = None
        if body.import_file_id:
            imported, _ = self.domain.file_record(pid, body.import_file_id)
        for eid in sorted(evidence_ids(body)):
            ev = self.store.get('evidence', eid)
            if ev['project_id'] != pid:
                raise core.ValidationError('Cross-project lifecycle evidence rejected')
            if ev['review_state'] == 'rejected':
                raise core.ValidationError('Rejected factor evidence cannot support a new inventory')
            if ev['source_file']:
                self.domain.file_record(pid, ev['source_file'])
            evidence.append(ev)
        obj = {'lifecycle_id': 'lifecycle_'+uuid.uuid4().hex, 'project_id': pid, 'project_revision': project['revision'],
            'input': body.model_dump(), 'result': calculate(body), 'source_snapshot': evidence, 'import_source': imported,
            'calculator_hash': provenance_version(Path(__file__)), 'created_at': core.now()}
        obj['hash'] = core.hash_json(obj)
        persist(self.domain, 'lifecycle', obj, expected_bindings)
        return self.view(pid, obj['lifecycle_id'])

    def view(self, pid, lid):
        obj = self.store.get('lifecycle', lid)
        if obj['project_id'] != pid:
            raise core.ValidationError('Cross-project lifecycle record rejected')
        if core.hash_json({k:v for k,v in obj.items() if k not in {'hash','revision'}}) != obj['hash']:
            raise core.ValidationError('Lifecycle record integrity failed')
        provenance = validity(self.domain, obj, provenance_version(Path(__file__)))
        stale = provenance['stale_reasons']
        return {**obj, **provenance, 'status': 'stale' if stale else obj['result']['status'], 'result': None if stale else obj['result']}


def report(record):
    escape = lambda value: html.escape(str(value))
    display = lambda value: '缺数据 / 不适用' if value is None else format(value, '.10g')
    body, result = record['input'], record.get('result')
    labels = {'production':'材料生产', 'transport':'材料运输', 'construction':'施工',
              'operation':'使用阶段（运行及替换）', 'end_of_life':'寿命末期'}
    summary = '<p>记录已失效，旧结果不得用于当前决策。</p>'
    if result:
        rows = ''.join('<tr>'+''.join('<td>'+escape(v)+'</td>' for v in
            (labels[stage], item['status'], display(item['kgco2e']), item['reason']))+'</tr>'
            for stage, item in result['stages'].items())
        summary = ('<h2>声明边界总排放：'+display(result['boundary_total_kgco2e'])+' kgCO₂e</h2>'
            '<p>单位面积（整个评估期）：'+display(result['kgco2e_m2_over_study_period'])+' kgCO₂e/m²</p>'
            '<table><tr><th>阶段</th><th>状态</th><th>kgCO₂e</th><th>范围依据</th></tr>'+rows+'</table>'
            '<ul>'+''.join('<li>'+escape(x)+'</li>' for x in result['limitations'])+'</ul>')
    if result and result.get('replacement', {}).get('components'):
        summary += '<h2>替换事件账（使用阶段内）</h2><table><tr><th>构件</th><th>年份</th><th>次数</th><th>kgCO₂e</th></tr>' + ''.join(
            '<tr>' + ''.join('<td>' + escape(v) + '</td>' for v in (c['name'], c['years'], c['count'], display(c['kgco2e']))) + '</tr>'
            for c in result['replacement']['components']) + '</table><p>严格早于评估终点；初次安装及终点处置另账。寿命和排放因子均为声明情景。</p>'
    return ('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>阶段化碳清单</title>'
        '<style>body{font:16px/1.7 system-ui,sans-serif;max-width:960px;margin:40px auto;padding:20px;color:#172e31}'
        'table{border-collapse:collapse;width:100%}th,td{border:1px solid #ccd6d4;padding:10px;text-align:left}'
        'pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}</style>'
        '<h1>'+escape(body['name'])+' · 未核证</h1><p>不是完整性认证或碳资产凭证。</p>'
        '<p>评估期 '+escape(body['study_years'])+' 年 · 面积 '+escape(body['area_m2'])+' m² · 地区 '+escape(body['region'])+'</p>'
        '<p>方法：'+escape(body['method'])+'<br>功能单位：'+escape(body['functional_unit'])+'</p>'+summary+
        '<h2>输入、逐项复算与来源快照</h2><pre>'+escape(json.dumps(record,ensure_ascii=False,indent=2,allow_nan=False))+'</pre></html>')


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
            'included': sorted(s['stage'] for s in b['boundaries'] if s['included']),
            'replacement_scope': b.get('replacement_scope', 'not_assessed'),
            'replacement_boundary': sorted((c['component_id'], c['condition'], c['endpoint'], c['scope'],
                tuple(sorted(p['process'] for p in c['processes'] if p['included']))) for c in b.get('replacements', []))}
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
