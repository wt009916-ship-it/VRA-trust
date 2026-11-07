"""Check structured explanations against current records; never certify model prose."""
import copy
from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from .schema import Contract
from .agent_inspections import INSPECTIONS, record_name
from . import agent_scenarios
from . import core


class Statement(Contract):
    fact: str = Field(min_length=1, max_length=100, description='Copy the exact machine key from explanation_facts.fact, never its human-readable label or a translated name.')
    value: str | None = Field(max_length=80, pattern=r'^-?([0-9]+(\.[0-9]*)?|\.[0-9]+)([eE][+-]?[0-9]{1,4})?$',
                             description='Required. Copy a known explanation_facts numeric value as a string. Copy null only for an explicit source_undefined fact with an unavailable_reason. Never invent zero or null. For an incomplete/stale record use professional_limit.')
    unit: str = Field(min_length=1, max_length=40)
    period: Literal['steady_state', 'study_period', 'quote_date', 'static_load_case', 'elapsed_days', 'observed_window']
    study_years: int | None = Field(ge=1, le=200, description='Required: copy the fact study_years; null for a non-period calculation.')
    area_m2: float | None = Field(gt=0, allow_inf_nan=False, description='Required: copy fact area_m2. Null means no explicit area denominator; see area_basis. R/U are intrinsic area-normalized properties, not totals.')


class Delivery(Contract):
    kind: Literal['thermal', 'lifecycle', 'cost', 'engineering', 'schedule', 'operation', 'scenario']
    record_id: str = Field(pattern=r'^(?:thermal|lifecycle|cost|engineering|schedule|operation|scenario)_[a-f0-9]{32}$')
    record_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    statements: list[Statement] = Field(default_factory=list, max_length=12)
    limitation_status: Literal['incomplete','outside_model_screen','constraints_unresolved','incomplete_progress','insufficient_evidence','events_detected','stale'] | None = Field(default=None,
        description='For a currently incomplete/inapplicable/stale record, copy its status here and use statements: []. This verifies the limitation only, never revives stale numbers or changes record status.')
    finish: bool = Field(default=False, description='True only for the last professional record you intend to deliver in this task. Ends model calls after successful validation; no extra prose turn needed.')

    @model_validator(mode='after')
    def consistent(self):
        if not self.record_id.startswith(self.kind + '_'):
            raise ValueError('Record kind and ID disagree')
        if len({s.fact for s in self.statements}) != len(self.statements):
            raise ValueError('Duplicate fact statements')
        if bool(self.statements) == bool(self.limitation_status):
            raise ValueError('Deliver either numeric statements or a current limitation status, not both or neither')
        return self


class NumericDelivery(Contract):
    """The model-facing numeric contract matches server validation exactly."""
    kind: Literal['thermal', 'lifecycle', 'cost', 'engineering', 'schedule', 'operation', 'scenario']
    record_id: str = Field(pattern=r'^(?:thermal|lifecycle|cost|engineering|schedule|operation|scenario)_[a-f0-9]{32}$')
    record_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    statements: list[Statement] = Field(min_length=1, max_length=12)
    finish: bool = Field(default=False, description='True only for the last professional record you intend to deliver in this task. Ends model calls after successful validation; no extra prose turn needed.')

    @model_validator(mode='after')
    def consistent(self):
        self.delivery()
        return self

    def delivery(self):
        return Delivery(**self.model_dump(mode='json'))


class Limitation(Contract):
    kind: Literal['thermal', 'lifecycle', 'cost', 'engineering', 'schedule', 'operation', 'scenario']
    record_id: str = Field(pattern=r'^(?:thermal|lifecycle|cost|engineering|schedule|operation|scenario)_[a-f0-9]{32}$')
    record_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    status: Literal['incomplete','outside_model_screen','constraints_unresolved','incomplete_progress','insufficient_evidence','events_detected','stale']
    finish: bool = False

    def delivery(self):
        return Delivery(kind=self.kind,record_id=self.record_id,record_hash=self.record_hash,
                        limitation_status=self.status,statements=[],finish=self.finish)


def inspection(kind):
    return next(s for s in INSPECTIONS.values() if s.kind == kind)


def facts(record, kind):
    """Explicit meanings from calculator fields, not free-text source descriptions."""
    result = record.get('result')
    if result is None or record['status'] == 'stale' or (kind == 'engineering' and record['status'] == 'outside_model_screen'):
        return []
    body = record['input']
    rows = []

    def add(key, label, value, unit, period, *, years=None, area=None, path=None, unavailable_reason=None):
        if value is None and not unavailable_reason:
            return  # Only explicitly explained source-null fields may be acknowledged.
        # Match the established 12-significant-digit engineering display, not binary float tails.
        raw = None if value is None else str(value)
        display = format(value, '.12g') if isinstance(value, float) else raw
        rows.append({'fact': key, 'label': label, 'value': display, 'source_value': raw,
                     'value_policy': 'source_undefined' if value is None else ('12_significant_digits_display' if isinstance(value, float) else 'exact_decimal'),
                     'unit': unit, 'period': period, 'study_years': years, 'area_m2': area,
                     'area_basis': 'intrinsic_area_normalized_property' if kind == 'thermal' else (
                         'explicit_area_denominator' if area is not None else 'no_area_normalization'),
                     'time_basis': 'whole_study_period_not_annual' if period == 'study_period' else 'not_a_study_duration',
                     'source_path': path or '/result/' + key})
        if value is None:
            rows[-1]['unavailable_reason'] = unavailable_reason

    if kind == 'scenario':
        agent_scenarios.append_facts(record,add)
    elif kind == 'thermal':
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
    elif kind == 'engineering':
        metrics = result.get('metrics') or {}
        for key,label,unit in [('max_abs_moment_nm','最大绝对弯矩','N m'),
            ('max_abs_shear_n','最大绝对剪力','N'),('max_deflection_m','最大向下挠度','m'),
            ('max_elastic_bending_stress_pa','线弹性最大弯曲应力（非强度验算）','Pa'),
            ('left_reaction_n','左支反力','N'),('right_reaction_n','右支反力','N'),
            ('left_reaction_moment_nm','左端支反力矩','N m')]:
            add(key,label,metrics.get(key),unit,'static_load_case',path='/result/metrics/'+key)
    elif kind == 'schedule':
        planned = result.get('planned') or {}
        add('planned_duration_days','声明计划总工期',planned.get('duration_days'),'day','elapsed_days',path='/result/planned/duration_days')
        if result.get('forecast'):
            for key,label in [('as_of_day','进度记录截至日'),('finish_day','显式情景完工日'),('finish_variance_days','情景相对计划的完工偏差')]:
                add('forecast_'+key,label,result['forecast'][key],'day','elapsed_days',path='/result/forecast/'+key)
    elif kind == 'operation':
        for key,label in [('sample_count','CSV样本数'),('cell_issue_count','缺失或无效数值单元数'),('gap_count','超出最大间隔的采样缺口数')]:
            add(key,label,result['quality'][key],'count','observed_window',path='/result/quality/'+key)
        add('rule_event_sum','各规则事件次数之和（可能重叠，非故障数）',sum(r['event_count'] for r in result['rules']),
            'count','observed_window',path='derived:sum(/result/rules/*/event_count)')
        add('rule_unknown_sample_sum','各规则未知样本次数之和（可能重复）',sum(r['unknown_samples'] for r in result['rules']),
            'count','observed_window',path='derived:sum(/result/rules/*/unknown_samples)')
    return rows


def readable(record, kind):
    return {**record, 'explanation_facts': facts(record, kind),
            'explanation_instruction': '开放问答需用professional_deliver提交所需事实的value/unit/period/study_years/area_m2及当前hash。'
            '只核验这些结构化字段；没有的节能率、安全、合规、认证及信用不得作为事实交付。原记录未知值保持null。仅带unavailable_reason的明确无定义字段可照抄null并说明原因，不能视为数值答案；整条记录受限时用professional_limit。排除阶段没有事实项。'}


def model_projection(record, kind):
    """Explicit fact projection for delivery, with full source retained in the tool audit."""
    spec = inspection(kind)
    artifact = spec.artifact(record)
    return {spec.record_key: record[spec.record_key], 'hash': record['hash'], 'name': record_name(record),
            'status': record['status'], 'source_status': artifact['source_status'], 'scope': artifact['scope'],
            'explanation_facts': facts(record, kind),
            'limitation_delivery': None if artifact['verified'] else {
                'limitation_status':record['status'], 'statements':[],
                'stale_details':record.get('stale_details', []) if record['status']=='stale' else [],
                'stale_reasons':record.get('stale_reasons', []) if record['status']=='stale' else [],
                'instruction':'用professional_limit正式说明当前限制：status复制limitation_status，附kind/record_id/record_hash，不提供statements。stale只可依据stale_details说明已观察到的变化；scope是方法范围，不是失效原因。不得推测额外原因、恢复旧数值或改变原记录状态。'},
            'calculation_context': calculation_context(record, kind),
            'explanation_instruction': record['explanation_instruction'],
            'projection_notice': '这是正式交付事实的显式投影，不是完整输入。完整来源、逐层/逐项计算及排除项保存在本次工具审计和同源记录中；不能据此假定未列字段已核验。'}


def calculation_context(record, kind):
    result = record.get('result') or {}
    if kind == 'scenario':return agent_scenarios.context(record)
    if kind == 'thermal':
        return {'method': 'one_dimensional_steady_state_opaque_assembly',
                'resistance_definition': 'R=sum(d/lambda_effective)+Rsi+Rse; m2 K/W',
                'transmittance_definition': 'U=1/R; W/(m2 K)',
                'area_basis': 'intrinsic_area_normalized_property',
                'notice': 'R是面积热阻，U是单位面积传热系数；两者不需要建筑总面积。area_m2=null不是面积缺测，也不妨碍本记录的R/U计算。构件整体热阻为R/A（K/W），整体传热导度UA为W/K，需另有构件面积；不能用建筑面积代替。未计算全年能耗或节能率。'}
    if kind == 'lifecycle':
        return {'study_years': record['input']['study_years'], 'area_m2': record['input']['area_m2'],
                'excluded_stages': [b['stage'] for b in record['input']['boundaries'] if not b['included']],
                'notice': '阶段量及边界总量均覆盖声明评估期，不是年量。只有单位面积指标使用声明面积作分母；总量事实area_m2=null不表示建筑面积未知。排除阶段未知，不能视为零或完整生命周期；不签发碳资产。'}
    if kind == 'engineering':
        return {'support':record['input']['support'], 'model_screening':result.get('model_screening', []),
                'missing':result.get('missing', []), 'notice':'超出模型筛查范围时不交付工程数值；无安全结论。'}
    if kind == 'schedule':
        return {'calendar':record['input']['calendar'], 'time_origin':record['input']['time_origin'],
                'critical_tasks':(result.get('planned') or {}).get('critical_tasks'),
                'resource_status':((result.get('planned') or {}).get('resources') or {}).get('status'),
                'forecast_status':(result.get('forecast') or {}).get('status'),
                'notice':'连续经过日；关键任务集合不等于唯一串行路径，情景不是履约保证。'}
    if kind == 'operation':
        quality = result.get('quality') or {}
        return {'first_time':quality.get('first_time'), 'last_time':quality.get('last_time'),
                'data_nature':record['input']['data_nature'], 'clock_basis':record['input']['clock_basis'],
                'rule_states':[{'rule_id':r['rule_id'],'state':r['state'],'event_count':r['event_count'],
                    'unknown_samples':r['unknown_samples']} for r in result.get('rules',[])],
                'notice':'事件合计按规则求和，可能重复，不是故障数量；缺测不当作正常或零能耗。完整行号和事件跨度见同源报告。'}
    return None


class SemanticMismatch(ValueError):
    def __init__(self, corrections):
        super().__init__('Structured explanation disagrees with current facts; correct units, values and periods before delivery')
        self.corrections = corrections


def check(record, delivery):
    if record['hash'] != delivery.record_hash:
        raise ValueError('Record changed; read the current record again')
    if delivery.limitation_status:
        artifact = inspection(delivery.kind).artifact(record)
        if delivery.limitation_status != record['status'] or artifact['verified']:
            raise ValueError('Limitation does not match the current incomplete or inapplicable record')
        return {'status':'verified', 'reference':delivery.model_dump(mode='json'), 'statements':[],
                'limitation':{'record_id':delivery.record_id, 'state':record['status'], 'scope':artifact['scope'],
                              'stale_details':record.get('stale_details', []) if record['status']=='stale' else [],
                'stale_reasons':record.get('stale_reasons', []) if record['status']=='stale' else []},
                'notice':'只核验当前结果不完整或不适用的状态，不把限制说明当作有效工程数值。'}
    if record['status'] == 'stale':
        raise ValueError('Record is stale; numeric delivery remains unavailable')
    available = {f['fact']: f for f in facts(record, delivery.kind)}
    corrections, accepted = [], []
    for claim in delivery.statements:
        fact = available.get(claim.fact)
        if fact is None:
            corrections.append({'fact': claim.fact, 'error': 'Not an available calculated fact; copy an exact fact key, not a translated label',
                                'available_fact_keys':sorted(available)})
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


def accumulate(previous, reference):
    """Retain verified partial facts only within the exact same source identity.

    Called after the incoming delivery passed current-source semantic checks.
    A new source hash or limitation replaces prior numeric facts. Historical
    events remain separate; final/current reads still revalidate every fact.
    """
    merged = copy.deepcopy(reference)
    for saved in previous:
        if (all(saved.get(key) == merged.get(key) for key in ('kind', 'record_id', 'record_hash'))
                and not saved.get('limitation_status') and not merged.get('limitation_status')):
            statements = {item['fact']: item for item in saved['statements']}
            statements.update({item['fact']: item for item in merged['statements']})
            merged['statements'] = copy.deepcopy(list(statements.values()))
    Delivery.model_validate(merged)  # Preserve the existing maximum and field contract.
    return [item for item in previous if item['record_id'] != merged['record_id']] + [merged]


def current_answer(domain, project_id, deliveries, reader=None):
    artifacts, statements, checks, limitations = [], [], [], []
    for saved in deliveries:
        request = Delivery.model_validate(saved)
        spec = inspection(request.kind)
        valid = False
        try:
            record = reader(spec, request.record_id) if reader else spec.service(domain).view(project_id, request.record_id)
            checked = check(record, request)
            artifacts.append({**spec.artifact(record), 'record_id': request.record_id})
            if checked['statements']:
                statements.append({'record_id': request.record_id, 'name': record_name(record), 'facts': checked['statements']})
            if checked.get('limitation'):
                limitations.append(checked['limitation'])
            valid = True
        except (ValueError, KeyError, OSError):
            # Historical outputs remain audit snapshots; stale values never enter this answer.
            pass
        checks.append({'record_id': request.record_id, 'passed': valid, 'meaning': '当前记录限制已核对，不代表可用工程结果' if request.limitation_status else '结构化数值、单位与期间对照当前记录'})
    return {'can_simulate': None, 'can_recommend': False, 'workflow_completed': True,
            'task_completion': 'partial' if any(c['passed'] for c in checks) else 'incomplete',
            'execution_scope': 'checked_professional_deliveries', 'artifacts': artifacts, 'checked_statements': statements,
            'checked_limitations':limitations,
            'verification': checks, 'summary': '已核验所选结果或限制；自由问题的完整覆盖度仍未评估。' if artifacts else '先前交付已失效或来源不可用，不能复用历史数值。',
            'task_notice': '模型选择记录与事实，应用核对字段；这不是对模型自由解释或整个复杂任务的认证。',
            'gaps': ([{'record_id':r['record_id'], 'message':'当前记录来源或版本已失效，历史数值不可交付',
                       'action':'复核变化来源后另行提交计算；本次限制核验不会重算或恢复旧结果'} for r in limitations if r['state']=='stale']
                     + ([] if all(c['passed'] for c in checks) else [{'message': '部分记录已变化或失效', 'action': '重新读取并核验当前记录'}])),
            'limitations': ['未评估完整问题覆盖、来源真实性、规范合规、安全认证或可交易碳资产。'],
            'checked_at': core.now()}
