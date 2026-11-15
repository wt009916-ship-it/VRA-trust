"""Explicit model exits; never infer intent, grant permission or certify completion."""
from . import core


def submitted(record):
    return any(record.get(key) for key in (
        'professional_deliveries', 'professional_reviews', 'missing_deliveries',
        'availability_deliveries', 'capability_delivery', 'professional_comparisons'))


def calculation_scope(body):
    return {'allow_compute': body.allow_compute,
            'authorized_plan_keys': [p.plan_key for p in body.calculation_plans if p.execution_authorized],
            'historical_authorization_inherited': False}


def deferral(record, body, reason):
    reason = reason or 'unclear_outputs'
    scope = calculation_scope(body)
    if reason == 'calculation_not_authorized' and scope['allow_compute']:
        raise core.ValidationError('Current task permits computation; do not claim absent authorization')
    if reason == 'missing_calculation_plan' and scope['authorized_plan_keys']:
        raise core.ValidationError('Current authorized plans exist; do not claim no executable plans')
    result = {'question_hash': core.hash_json(record['question']),
              'origin': 'model_uncertainty' if reason == 'unclear_outputs' else 'model_selected_execution_gap',
              'reason': reason}
    if reason != 'unclear_outputs':
        result['calculation_scope'] = scope
    return result


def deferral_summary(item):
    if item.get('reason') == 'calculation_not_authorized':
        return '本轮未授权新建计算，历史授权不延续；请确认本轮计算权限及参数计划。未将旧记录当作本次新计算。'
    if item.get('reason') == 'missing_calculation_plan':
        return '本轮没有明确授权且锁定参数的计算计划；请提交并确认本轮所需计划。未新建计算，未用旧记录替代。'
    return '模型仍需明确问题中的目标或指标；未将不确定性当成资料缺失、能力结论或任务完成。'
