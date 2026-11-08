"""Model-inferred output plans and source-bound explanations, never proof of intent."""
import copy
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic.json_schema import SkipJsonSchema

from . import core, agent_intent_catalog as intent_catalog
from .schema import Contract
from .agent_scenarios import FACTS as SCENARIO_FACTS
from . import agent_scenarios, agent_intent_constraints

FACTS = {
    'scenario': SCENARIO_FACTS,
    'thermal': ['total_resistance_m2k_w', 'layer_resistance_m2k_w', 'u_w_m2k'],
    'lifecycle': ['boundary_total_kgco2e', 'kgco2e_m2_over_study_period'] +
                 ['stage.' + s for s in ['production', 'transport', 'construction', 'operation', 'end_of_life']],
    'cost': ['material_total'],
    'engineering': ['max_abs_moment_nm', 'max_abs_shear_n', 'max_deflection_m',
                    'max_elastic_bending_stress_pa', 'left_reaction_n', 'right_reaction_n',
                    'left_reaction_moment_nm'],
    'schedule': ['planned_duration_days', 'forecast_as_of_day', 'forecast_finish_day', 'forecast_finish_variance_days'],
    'operation': ['sample_count', 'cell_issue_count', 'gap_count', 'rule_event_sum', 'rule_unknown_sample_sum'],
}
Topic = Literal['meaning', 'area', 'period', 'scope', 'status', 'history']


class OutputItem(Contract):
    request_key: str = Field(pattern=r'^[A-Za-z0-9_-]{1,40}$')
    question_excerpt: SkipJsonSchema[str | None] = Field(default=None, min_length=1, max_length=500)
    question_fragment_ids: list[str] | None = Field(default=None, min_length=1, max_length=16,
        description='Select IDs from the application-provided original question fragments. Do not copy, rewrite or invent text.')
    fact_keys: list[str] = Field(max_length=12,
        description='Exact numeric fact keys requested by the user. Availability requests use []. Total R is total_resistance_m2k_w, not layer resistance.')
    explanation_topics: list[Topic] = Field(max_length=6,
        description='Requested explanation topics: meaning, area, period, scope, status, history. Availability supports history/status only.')


    @model_validator(mode='after')
    def source_anchor(self):
        if (self.question_excerpt is None) == (self.question_fragment_ids is None):
            raise ValueError('Provide either legacy exact excerpt or original question fragment IDs')
        if self.question_fragment_ids and len(set(self.question_fragment_ids)) != len(self.question_fragment_ids):
            raise ValueError('Question fragments must be distinct')
        return self


def version():
    return core.hash_json([core.sha(Path(__file__)), core.sha(Path(__file__).with_name('agent_semantics.py')), core.sha(Path(intent_catalog.__file__)), core.sha(Path(agent_scenarios.__file__)), core.sha(Path(agent_intent_constraints.__file__))])


def catalog(requests):
    return [{'request_key': r['request_key'], 'kind': r['kind'], 'purpose': r['purpose'],
             'available_fact_keys': FACTS[r['kind']] if r['purpose'] == 'results' else [],
             'available_explanation_topics': ['history', 'status'] if r['purpose'] == 'availability' else
                 ['meaning', 'scope', 'status', 'history'] + (['area', 'period'] if r['kind'] in {'thermal', 'lifecycle', 'scenario'} else [])}
            for r in requests]


def constrain_tool(tool, requests, question):
    tool = copy.deepcopy(tool)
    parameters = tool['function']['parameters']
    prototype = parameters['$defs']['OutputItem']
    variants = []
    for entry in catalog(requests):
        item = copy.deepcopy(prototype)
        props = item['properties']
        props['request_key'] = {'type': 'string', 'const': entry['request_key']}
        props['question_fragment_ids'] = {'type':'array','minItems':1,'maxItems':16,'uniqueItems':True,
            'items':{'type':'string','enum':[f['fragment_id'] for f in intent_catalog.fragments(question)]},
            'description':'Select original question fragment IDs supporting this request. The application retains their exact text.'}
        item['required'] = ['request_key','question_fragment_ids','fact_keys','explanation_topics']
        props['fact_keys'] = ({'type': 'array', 'minItems': 1, 'maxItems': 12, 'uniqueItems': True,
                               'items': {'type': 'string', 'enum': entry['available_fact_keys']},
                               'description': intent_catalog.meaning_description(entry['kind'])}
                              if entry['purpose'] == 'results' else {'type': 'array', 'maxItems': 0})
        props['explanation_topics'] = {'type': 'array', 'maxItems': 6, 'uniqueItems': True,
                                       'items': {'type': 'string', 'enum': entry['available_explanation_topics']},
                                       'description': 'Select only explanations requested by the user; allowed options are not requirements.'}
        request=next(r for r in requests if r['request_key']==entry['request_key'])
        constraints=agent_intent_constraints.analyze(question,request,requests)
        if entry['purpose']=='results':
            facts=props['fact_keys']
            facts['items']['enum']=[k for k in entry['available_fact_keys'] if k not in constraints['forbidden_facts']]
            if not facts['items']['enum']: facts['items']['enum']=entry['available_fact_keys']  # Validator will require clarification.
            facts['description']+='; Explicit original-question requirements: '+repr(constraints['required_facts'])
            if constraints['unsupported']:facts['description']+='; Unsupported or contradictory request: '+repr(constraints['unsupported'])
        forbidden=set(constraints['forbidden_topics'])
        topics=props['explanation_topics']
        topics['items']['enum']=[k for k in entry['available_explanation_topics'] if k not in forbidden]
        if not topics['items']['enum']:
            topics.pop('items');topics['maxItems']=0
        elif constraints['required_topics']:
            topics['description']+='; Explicit original-question requirements: '+repr(constraints['required_topics'])
        variants.append(item)
    parameters.pop('$defs')
    parameters['properties']['output_plan'] = {'type': 'array', 'minItems': len(requests),
                                              'maxItems': len(requests), 'items': {'oneOf': variants}}
    parameters['required'] = ['output_plan']
    return tool


def freeze(record, items):
    if record.get('output_plan'):
        raise core.ValidationError('Output plan is frozen; source data cannot rewrite the user task')
    requests = {r['request_key']: r for r in record['read_requests']}
    if len(items) != len(requests) or {i.request_key for i in items} != set(requests):
        raise core.ValidationError('Plan must cover every declared request exactly once; missing=' +
                                   repr(sorted(set(requests) - {i.request_key for i in items})) +
                                   '; unexpected=' + repr(sorted({i.request_key for i in items} - set(requests))))
    allowed = {r['request_key']: r for r in catalog(record['read_requests'])}
    anchors = {f['fragment_id']:f for f in intent_catalog.fragments(record['question'])}
    normalized = []
    for item in items:
        entry = allowed[item.request_key]
        saved = item.model_dump(mode='json', exclude_none=True)
        if item.question_fragment_ids is not None:
            if not set(item.question_fragment_ids) <= set(anchors):
                raise core.ValidationError('Question fragment IDs must belong to this original question')
            selected = sorted((anchors[k] for k in item.question_fragment_ids), key=lambda f:f['start'])
            saved['question_spans'] = selected
            saved['question_excerpt'] = '\n'.join(f['text'] for f in selected)
        elif item.question_excerpt not in record['question']:
            raise core.ValidationError('Quote an exact substring of the current user question, not source data')
        normalized.append(saved)
        if len(set(item.fact_keys)) != len(item.fact_keys) or not set(item.fact_keys) <= set(entry['available_fact_keys']):
            raise core.ValidationError('Unknown, duplicate or out-of-scope fact keys')
        if entry['purpose'] == 'results' and not item.fact_keys:
            raise core.ValidationError('Result output requires at least one requested numeric fact')
        if len(set(item.explanation_topics)) != len(item.explanation_topics) or not set(item.explanation_topics) <= set(entry['available_explanation_topics']):
            raise core.ValidationError('Unsupported or duplicate explanation topics')
        saved['explicit_request_constraints'] = agent_intent_constraints.validate(record['question'], requests[item.request_key],
            record['read_requests'], item.fact_keys, item.explanation_topics)
    return {'origin': 'model_inferred_from_user_question', 'version': version(),
            'question_hash': core.hash_json(record['question']),
            'items': normalized,
            'intent_verified': False,
            'notice': '模型解析的交付要求，尚未证明完整理解原问题；不扩大用户声明的记录范围或计算权限。'}


def requirement(record, key):
    return next((r for r in (record.get('output_plan') or {}).get('items', []) if r['request_key'] == key), None)


def missing_facts(record, request, deliveries):
    required = requirement(record, request['request_key'])
    if not required:
        return []
    actual = {s['fact'] for d in deliveries if d['record_id'] == request['record_id']
              for s in d.get('statements', [])}
    return sorted(set(required['fact_keys']) - actual)


def explain(topic, request, facts, state, artifact):
    """Application text from validated current facts; no model prose or source-name instructions."""
    if topic == 'history':
        return '这里只核验当前项目、指定范围的记录。记录缺失不能证明从未计算；记录存在也不是完整历史执行审计。'
    if state == 'fields_unavailable' and topic == 'status':
        return '；'.join(f['unavailable_reason'] for f in facts if f.get('unavailable_reason'))
    if topic == 'status':
        if state == 'record_unavailable':
            return '指定记录在当前项目不可用；无法交付其工程数值，不推断其他项目中的记录。'
        if state == 'availability_verified':
            return '已核验声明范围的记录可用性；该检查不验证工程数值是否有效。'
        if state == 'limitation_verified':
            reasons = artifact.get('stale_reasons') or []
            return '当前结果受限或失效，未交付旧数值。' + ('已观察到的失效原因：' + '；'.join(reasons) if reasons else '具体限制见同源记录。')
        return '所列字段已按当前记录核验，不表示工程合规、安全认证或整个自由问题已完成。'
    if state in {'record_unavailable', 'limitation_verified'}:
        return '当前来源不能支持所请求的数值解释；请先复核记录或来源限制，不使用历史数值。'
    if topic == 'scope':
        return artifact.get('scope', '仅核验所列字段，未作工程合规或认证判断。')
    if topic == 'area':
        if request['kind'] == 'thermal':
            return 'R为面积热阻（m²·K/W），U为单位面积传热系数（W/(m²·K)）；两者由构造决定，无需建筑总面积。area_m2为空表示没有另用面积分母，不是面积缺测。整体热阻R/A及传热导度UA另需构件面积，不能用建筑面积替代。'
        if request['kind']=='scenario':
            return '材料方案单位面积碳量使用项目建筑面积，不是所选墙面积；总量与金额不除以面积。分母仅为项目声明，未作实楼测量核证。'
        area_facts = [f for f in facts if f.get('area_m2') is not None]
        if area_facts:
            return '碳总量不以面积作分母；单位面积指标使用声明面积' + str(area_facts[0]['area_m2']) + ' m²作分母。总量字段的area_m2为空不表示建筑面积未知。'
        return '本次交付的是未按面积归一化的碳总量，area_m2为空不表示建筑面积未知；单位面积结果需另行交付相应事实。'
    if topic == 'period':
        if request['kind']=='scenario':
            return '材料金额对应声明报价日期；碳量与碳比例覆盖声明的'+str(artifact.get('input',{}).get('study_years','未知'))+'年评估期，不是年量。排除阶段不记零；功能等效及清单完整性未核证。'
        years = {f.get('study_years') for f in facts if f.get('study_years') is not None}
        return ('这些碳量覆盖声明的' + str(next(iter(years))) + '年评估期，不是每年排放。排除阶段不能记为零，不能据此称为完整生命周期核证。') if years else '本次为一维稳态热工量，不是逐年能耗或全年节能率。'
    return '；'.join(f"{f['label']}：{f['unavailable_reason']}" if f.get('unavailable_reason') else f"{f['label']}为{f['value']} {f['unit']}" for f in facts) + '。数值来自已读取并核验的记录，不由模型补算。'


def attach(answer, record):
    if not record.get('infer_outputs'):
        return answer
    plan = record.get('output_plan')
    answer['output_plan'] = plan
    answer['requested_outputs'] = []
    answer['output_contract_coverage'] = 'plan_missing'
    if not plan:
        return answer
    if plan['version'] != version() or plan['question_hash'] != core.hash_json(record['question']):
        answer['output_contract_coverage'] = 'contract_changed'
        return answer
    progress = {r['request_key']: r for r in answer.get('read_request_progress', [])}
    values = {r['record_id']: r['facts'] for r in answer.get('checked_statements', [])}
    artifacts = {r['record_id']: r for r in answer.get('artifacts', [])}
    limits = {r['record_id']: r for r in answer.get('checked_limitations', [])}
    outputs = []
    for r in record['read_requests']:
        needed = requirement(record, r['request_key'])
        state = progress.get(r['request_key'], {}).get('state', 'unfulfilled')
        facts = [f for f in values.get(r['record_id'], []) if f['fact'] in needed['fact_keys']]
        missing = sorted(set(needed['fact_keys']) - {f['fact'] for f in facts})
        blocked = state in {'record_unavailable', 'limitation_verified', 'fields_unavailable'}
        ready = state in {'result_verified', 'availability_verified'} and not missing
        artifact = artifacts.get(r['record_id']) or limits.get(r['record_id']) or {}
        source_hash = artifact.get('record_hash')
        if r['purpose'] == 'availability' and ready:
            source_hash = next((v['catalog_hash'] for v in record.get('availability_deliveries', [])
                                if v['request']['request_key'] == r['request_key']), None)
        elif state == 'record_unavailable':
            source_hash = next((v['catalog_hash'] for v in record.get('missing_deliveries', [])
                                if v['request'].get('record_id') == r['record_id']), None)
        texts = [{'topic': topic, 'text': explain(topic, r, facts, state, artifact)}
                 for topic in needed['explanation_topics']] if ready or blocked else []
        outputs.append({'request_key': r['request_key'], 'record_id': r['record_id'], 'missing_fact_keys': missing,
                        'state': 'source_limited' if blocked else 'fulfilled' if ready else 'incomplete',
                        'unknown_fact_keys': sorted(f['fact'] for f in facts if f['value'] is None),
                        'explanations': texts, 'explanation_origin': 'application_from_current_verified_sources',
                        'source_hash': source_hash, 'explanation_version': plan['version']})
    answer['requested_outputs'] = outputs
    answer['output_contract_coverage'] = ('fulfilled' if all(o['state'] == 'fulfilled' for o in outputs) else
        'addressed_with_source_limits' if all(o['state'] in {'fulfilled', 'source_limited'} for o in outputs) else 'incomplete')
    answer['output_contract_notice'] = '仅检查模型解析计划中的指标和解释主题是否交付；计划对原始问题的理解仍需核对。解释由应用按当前来源生成，模型自由原文未获语义认证。'
    return answer
