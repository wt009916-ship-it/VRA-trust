"""Check structured explanations against current records; never certify model prose."""
from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from .schema import Contract
from .agent_inspections import INSPECTIONS
from . import core


class Statement(Contract):
    fact: str = Field(min_length=1, max_length=100)
    value: str | None = Field(max_length=80, pattern=r'^-?([0-9]+(\.[0-9]*)?|\.[0-9]+)([eE][+-]?[0-9]{1,4})?$',
                             description='Required. Copy the current explanation_facts numeric value as a string. Use null only when that source fact value is null.')
    unit: str = Field(min_length=1, max_length=40)
    period: Literal['steady_state', 'study_period', 'quote_date']
    study_years: int | None = Field(default=None, ge=1, le=200)
    area_m2: float | None = Field(default=None, gt=0, allow_inf_nan=False)


class Delivery(Contract):
    kind: Literal['thermal', 'lifecycle', 'cost']
    record_id: str = Field(pattern=r'^(?:thermal|lifecycle|cost)_[a-f0-9]{32}$')
    record_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    statements: list[Statement] = Field(min_length=1, max_length=12)

    @model_validator(mode='after')
    def consistent(self):
        if not self.record_id.startswith(self.kind + '_'):
            raise ValueError('Record kind and ID disagree')
        if len({s.fact for s in self.statements}) != len(self.statements):
            raise ValueError('Duplicate fact statements')
        return self


def inspection(kind):
    return next(s for s in INSPECTIONS.values() if s.kind == kind)


def facts(record, kind):
    """Explicit meanings from calculator fields, not free-text source descriptions."""
    result = record.get('result')
    if result is None or record['status'] == 'stale':
        return []
    body = record['input']
    rows = []

    def add(key, label, value, unit, period, *, years=None, area=None, path=None):
        # Match the established 12-significant-digit engineering display, not binary float tails.
        raw = None if value is None else str(value)
        display = format(value, '.12g') if isinstance(value, float) else raw
        rows.append({'fact': key, 'label': label, 'value': display, 'source_value': raw,
                     'value_policy': '12_significant_digits_display' if isinstance(value, float) else 'exact_decimal',
                     'unit': unit, 'period': period, 'study_years': years, 'area_m2': area,
                     'source_path': path or '/result/' + key})

    if kind == 'thermal':
        for key, label, unit in [('total_resistance_m2k_w', '总热阻 R', 'm2 K/W'),
                                 ('layer_resistance_m2k_w', '材料层热阻合计', 'm2 K/W'),
                                 ('u_w_m2k', '传热系数 U', 'W/(m2 K)')]:
            add(key, label, result[key], unit, 'steady_state')
    elif kind == 'lifecycle':
        years = body['study_years']
        add('boundary_total_kgco2e', '声明边界碳排总量', result['boundary_total_kgco2e'], 'kgCO2e', 'study_period', years=years)
        add('kgco2e_m2_over_study_period', '整个评估期单位面积碳排', result['kgco2e_m2_over_study_period'],
            'kgCO2e/m2', 'study_period', years=years, area=body['area_m2'])
        for stage, value in result['stages'].items():
            if value['included']:
                add('stage.' + stage, stage + '阶段总量', value['kgco2e'], 'kgCO2e', 'study_period',
                    years=years, path='/result/stages/' + stage + '/kgco2e')
    elif kind == 'cost':
        add('material_total', '声明材料清单合计（日期 ' + body['as_of'] + '）', result['material_total'], body['currency'], 'quote_date')
    return rows


def readable(record, kind):
    return {**record, 'explanation_facts': facts(record, kind),
            'explanation_instruction': '开放问答需用professional_deliver提交所需事实的value/unit/period/study_years/area_m2及当前hash。'
            '只核验这些结构化字段；没有的节能率、安全、合规、认证及信用不得作为事实交付。未知值保持null，排除阶段没有事实项。'}


def model_projection(record, kind):
    """Explicit fact projection for delivery, with full source retained in the tool audit."""
    spec = inspection(kind)
    artifact = spec.artifact(record)
    return {spec.record_key: record[spec.record_key], 'hash': record['hash'], 'name': record['input']['name'],
            'status': record['status'], 'source_status': artifact['source_status'], 'scope': artifact['scope'],
            'explanation_facts': facts(record, kind),
            'explanation_instruction': record['explanation_instruction'],
            'projection_notice': '这是正式交付事实的显式投影，不是完整输入。完整来源、逐层/逐项计算及排除项保存在本次工具审计和同源记录中；不能据此假定未列字段已核验。'}


class SemanticMismatch(ValueError):
    def __init__(self, corrections):
        super().__init__('Structured explanation disagrees with current facts; correct units, values and periods before delivery')
        self.corrections = corrections


def check(record, delivery):
    if record['hash'] != delivery.record_hash or record['status'] == 'stale':
        raise ValueError('Record changed or stale; read the current record again')
    available = {f['fact']: f for f in facts(record, delivery.kind)}
    corrections, accepted = [], []
    for claim in delivery.statements:
        fact = available.get(claim.fact)
        if fact is None:
            corrections.append({'fact': claim.fact, 'error': 'Not an available calculated fact; do not infer or invent it'})
            continue
        value_matches = (claim.value is None and fact['value'] is None) or (
            claim.value is not None and fact['value'] is not None and
            Decimal(claim.value) in {Decimal(fact['value']), Decimal(fact['source_value'])})
        if not value_matches or any(getattr(claim, k) != fact[k] for k in ('unit', 'period', 'study_years', 'area_m2')):
            corrections.append({'fact': claim.fact, 'expected': fact})
        else:
            accepted.append(fact)
    if corrections:
        raise SemanticMismatch(corrections)
    return {'status': 'verified', 'reference': delivery.model_dump(mode='json'), 'statements': accepted,
            'notice': '仅核验指定字段与当前记录一致；未验证自由文字、问题覆盖度、来源真实性或工程合规。'}


def current_answer(domain, project_id, deliveries, reader=None):
    artifacts, statements, checks = [], [], []
    for saved in deliveries:
        request = Delivery.model_validate(saved)
        spec = inspection(request.kind)
        valid = False
        try:
            record = reader(spec, request.record_id) if reader else spec.service(domain).view(project_id, request.record_id)
            checked = check(record, request)
            artifacts.append(spec.artifact(record))
            statements.append({'record_id': request.record_id, 'name': record['input']['name'], 'facts': checked['statements']})
            valid = True
        except (ValueError, KeyError, OSError):
            # Historical outputs remain audit snapshots; stale values never enter this answer.
            pass
        checks.append({'record_id': request.record_id, 'passed': valid, 'meaning': '结构化数值、单位与期间对照当前记录'})
    return {'can_simulate': None, 'can_recommend': False, 'workflow_completed': True,
            'task_completion': 'partial' if any(c['passed'] for c in checks) else 'incomplete',
            'execution_scope': 'checked_professional_deliveries', 'artifacts': artifacts, 'checked_statements': statements,
            'verification': checks, 'summary': '已交付当前核验的专业事实；自由问题的完整覆盖度仍未评估。' if artifacts else '先前交付已失效或来源不可用，不能复用历史数值。',
            'task_notice': '模型选择记录与事实，应用核对字段；这不是对模型自由解释或整个复杂任务的认证。',
            'gaps': [] if all(c['passed'] for c in checks) else [{'message': '部分记录已变化或失效', 'action': '重新读取并核验当前记录'}],
            'limitations': ['未评估完整问题覆盖、来源真实性、规范合规、安全认证或可交易碳资产。'],
            'checked_at': core.now()}
