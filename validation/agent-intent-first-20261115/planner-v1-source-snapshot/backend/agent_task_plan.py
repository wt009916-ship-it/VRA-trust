"""Source-free task contracts. Planning never reads records or authorizes execution.

This module is not yet wired into the active Agent. The caller must supply
server-derived history and the current request's frozen calculation plans.
"""
import copy

from jsonschema import Draft202012Validator

from . import core, agent_intent_catalog, agent_outputs, agent_metric_reads, agent_capabilities


def context(question, history=(), *, allow_compute=False, calculation_plans=()):
    references = []
    previous_questions = []
    for turn in history[-3:]:
        previous_questions.append(turn['question'])
        references.extend(r['record_id'] for r in turn.get('professional_references', []))
        references.extend(r['record_id'] for r in turn.get('missing_references', []) if r.get('record_id'))
    ids = sorted(set(agent_metric_reads.identifiers(question) + references))
    plans = [{'plan_key': p['plan_key'], 'kind': p['kind'], 'execution_authorized': p['execution_authorized']}
             for p in calculation_plans]
    return {'question': question, 'question_hash': core.hash_json(question),
            'fragments': agent_intent_catalog.fragments(question),
            'previous_questions': previous_questions, 'known_record_ids': ids,
            'current_authorization': {'allow_compute': allow_compute, 'plans': plans,
                                      'historical_authorization_inherited': False},
            'notice': '这里只提供原问题、历史问题与编号，不提供项目目录、工程数值或来源正文。计划是模型理解，尚未执行或核验意图。'}


def object_schema(properties):
    return {'type': 'object', 'properties': properties, 'required': list(properties), 'additionalProperties': False}


def choices(values, *, minimum=0, maximum=12, description=None):
    result = {'type': 'array', 'items': {'type': 'string', 'enum': list(values)},
              'minItems': minimum, 'maxItems': maximum, 'uniqueItems': True}
    if description: result['description'] = description
    return result


def tool(context):
    fragments = [f['fragment_id'] for f in context['fragments']]
    anchors = choices(fragments, minimum=1, maximum=24,
                      description='原问题中支持本项任务的片段；约束可另记constraint_fragment_ids。覆盖片段不证明已正确理解。')
    common = {'item_key': {'type': 'string', 'pattern': '^[A-Za-z][A-Za-z0-9_-]{0,31}$'},
              'question_fragment_ids': anchors}
    variants = []
    def variant(operation, fields, description):
        variants.append({**object_schema({**common, 'operation': {'const': operation}, **fields}), 'description': description})
    for ident in context['known_record_ids']:
        kind = ident.split('_', 1)[0]
        if kind not in agent_outputs.FACTS:
            continue
        variant('read_record', {
            'record_id': {'const': ident},
            'fact_keys': choices(agent_outputs.FACTS[kind], description=agent_intent_catalog.meaning_description(kind)),
            'explanation_topics': choices(['meaning', 'area', 'period', 'scope', 'status', 'history', 'energy_relationship'], maximum=6)},
            '读取已有指定记录。仅选原问题要求的指标，不加可选阶段或已知部分来代替完整总量；来源是否有效由执行时检查。不能用于新建要求。')
        variant('record_availability', {'record_id': {'const': ident}},
                '只核查这个指定编号在当前项目是否可用；不读取外项目，也不交付数值。')
    plans = context['current_authorization']['plans']
    variant('create_calculation', {
        'kind': {'enum': ['thermal', 'lifecycle', 'cost', 'engineering', 'schedule', 'operation']},
        'plan_key': {'enum': [None, *[p['plan_key'] for p in plans]]}},
        '用户要求新建或再次计算时必须保留创建任务，即使当前无权限或无计划；不能改为读取旧结果。没有当前锁定计划用null，执行器会明确前提缺口。不可填写或猜测工程参数。')
    variant('compare_records', {
        'baseline_id': {'enum': context['known_record_ids']}, 'candidate_id': {'enum': context['known_record_ids']},
        'fact_key': {'enum': ['u_w_m2k', 'total_resistance_m2k_w', 'material_total', 'boundary_total_kgco2e', 'kgco2e_m2_over_study_period']},
        'outputs': choices(['difference', 'relative_change_percent'], minimum=1, maximum=2)},
        '仅用户要求的两条已有记录同指标比较；对照减基准，百分比以基准为分母。不得代替新建、认证或全年节能判断。')
    if len(context['known_record_ids']) < 2:
        variants.pop()  # No invented comparison source.
    variant('explain_capabilities', {'capability_ids': choices(agent_capabilities.ENTRIES, minimum=1, maximum=16)},
            '要求认证、签发或询问能力边界时，列出全部相关能力；能力说明不能代替用户另行要求的实际读取或计算。')
    variant('locate_record', {'kind': {'enum': list(agent_outputs.FACTS)},
                             'selection': {'enum': ['named', 'latest', 'unspecified']},
                             'name_from_question': {'type': ['string', 'null'], 'maxLength': 120}},
            '确实要求已有记录但尚无明确编号时定位。只能按原问题指定名称/最新/待澄清；不因新建缺授权而改用此项。')
    variant('other_request', {'domain': {'enum': ['standards', 'files_drawings', 'simulation', 'other']}},
            '保留上述动作未覆盖的真实请求，后续单独处理；不得悄悄丢弃或假称完成。')
    variant('clarify_request', {'reason': {'enum': ['ambiguous_target', 'ambiguous_metric', 'contradictory_request']}},
            '原用户目标本身不明确或矛盾才澄清。数据缺失、stale、无计算权限不是指标不明确，应保留原读取/新建任务。')
    schema = object_schema({'items': {'type': 'array', 'minItems': 1, 'maxItems': 6, 'items': {'oneOf': variants}},
                            'constraint_fragment_ids': choices(fragments, maximum=24),
                            'unassigned_fragment_ids': choices(fragments, maximum=24)})
    return {'type': 'function', 'function': {'name': 'task_plan',
        'description': '在读取资料前，将原问题拆成完整任务清单，明确读取与新建及精确指标；保留全部要求与排除项。不执行、不授权、不输出计算数值。',
        'parameters': schema}}


def freeze(arguments, planning_context):
    schema = tool(planning_context)['function']['parameters']
    errors = list(Draft202012Validator(schema).iter_errors(arguments))
    if errors:
        raise core.ValidationError('Task plan violates the offered source-free contract')
    items = copy.deepcopy(arguments['items'])
    if len({i['item_key'] for i in items}) != len(items):
        raise core.ValidationError('Task item keys must be distinct')
    covered = set(arguments['constraint_fragment_ids']) | set(arguments['unassigned_fragment_ids'])
    for item in items:
        covered.update(item['question_fragment_ids'])
        if item['operation'] == 'read_record' and not (item['fact_keys'] or item['explanation_topics']):
            raise core.ValidationError('A read task must name its requested output')
        if item['operation'] == 'compare_records':
            first, second = item['baseline_id'], item['candidate_id']
            kind = first.split('_', 1)[0]
            if first == second or kind != second.split('_', 1)[0] or item['fact_key'] not in agent_outputs.FACTS.get(kind, []):
                raise core.ValidationError('Comparison requires two distinct compatible source kinds and metric')
        if item['operation'] == 'locate_record':
            if (item['selection'] == 'named') != bool(item['name_from_question']):
                raise core.ValidationError('Named selection requires a name; other selection must not invent one')
            if item['name_from_question'] and item['name_from_question'] not in planning_context['question']:
                raise core.ValidationError('Record name must occur in the original question')
        if item['operation'] == 'create_calculation':
            authorization = planning_context['current_authorization']
            plan = next((p for p in authorization['plans'] if p['plan_key'] == item['plan_key']), None)
            if plan and plan['kind'] != item['kind']:
                raise core.ValidationError('Plan kind mismatch; no substitution')
            item['execution_requirements'] = []
            if not authorization['allow_compute']:
                item['execution_requirements'].append('current_computation_authorization')
            if plan is None:
                item['execution_requirements'].append('current_locked_parameter_plan')
            elif not plan['execution_authorized']:
                item['execution_requirements'].append('current_plan_authorization')
    expected = {f['fragment_id'] for f in planning_context['fragments']}
    if covered != expected:
        raise core.ValidationError('Every original question fragment must remain assigned, constrained or explicitly unassigned')
    result = {'version': 'source_free_task_plan_v1', 'origin': 'model_inferred',
              'question_hash': planning_context['question_hash'], 'context_hash': core.hash_json(planning_context),
              'items': items, 'constraint_fragment_ids': arguments['constraint_fragment_ids'],
              'unassigned_fragment_ids': arguments['unassigned_fragment_ids'],
              'intent_verified': False, 'executed': False,
              'notice': '任务清单保留模型解析，不证明理解完整正确。工程数值、权限、来源及交付必须另行执行核验。'}
    result['hash'] = core.hash_json(result)
    return result
