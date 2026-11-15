"""Nonnumeric source reviews, separate from numerical delivery and certification."""
from typing import Literal

from pydantic import Field, model_validator

from . import core, agent_energy
from .schema import Contract
from .agent_semantics import inspection, facts


class SourceReview(Contract):
    kind: Literal['thermal', 'lifecycle', 'cost', 'engineering', 'schedule', 'operation', 'scenario', 'enduse', 'utility']
    record_id: str = Field(pattern=r'^(?:thermal|lifecycle|cost|engineering|schedule|operation|scenario|enduse|utility)_[a-f0-9]{32}$')
    record_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    view_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    finish: bool = False

    @model_validator(mode='after')
    def consistent(self):
        if not self.record_id.startswith(self.kind + '_'):
            raise ValueError('Review kind and record ID disagree')
        return self


def view_hash(record, kind):
    # Include dynamic source status; a persisted record hash alone does not
    # change when its external file or project dependency becomes stale.
    return core.hash_json({'record_hash': record['hash'], 'status': record['status'],
        'stale_reasons': record.get('stale_reasons', []),
        'stale_details': record.get('stale_details', []),
        'whole_record_verified': inspection(kind).artifact(record)['verified']})


def reference(record, kind):
    return {'kind': kind, 'record_id': record[inspection(kind).record_key],
            'record_hash': record['hash'], 'view_hash': view_hash(record, kind), 'finish': False}


def check(record, review):
    if record['hash'] != review.record_hash or view_hash(record, review.kind) != review.view_hash:
        raise core.ValidationError('Review source changed; read the current status again')
    return {'status': 'verified', 'reference': review.model_dump(mode='json'),
            'scope': 'current_source_status_and_declared_method_only',
            'notice': 'This review delivers no numerical facts and does not certify engineering validity.'}


def explanation(topic, record, kind):
    artifact = inspection(kind).artifact(record)
    if kind in agent_energy.KINDS and topic in {'period','scope','status'}:return agent_energy.explanation(topic,artifact)
    if topic == 'history':
        return '这里只复核指定记录当前的状态与声明范围，不是完整历史执行审计；存在记录不证明已获工程认证。'
    if topic == 'status':
        labels = {'calculated':'已计算', 'stale':'来源或版本已失效', 'incomplete':'资料不完整',
            'insufficient_evidence':'证据不充分', 'events_detected':'检出规则事件',
            'no_rule_event':'未检出声明规则事件', 'constraints_unresolved':'资源约束未解决',
            'incomplete_progress':'进度情景不完整', 'outside_model_screen':'超出计算模型适用范围'}
        return ('当前记录状态：' + labels.get(record['status'], record['status']) + '。' +
            ('记录满足当前方法的完整性检查；' if artifact['verified'] else '整体记录仍未通过当前方法的完整性检查；') +
            '本次只核验状态，未交付计算数值，不表示安全、合规、健康或碳资产认证。')
    if record['status'] == 'stale':
        return '当前来源已失效；本次不能以旧记录支持所请求的范围或指标解释，请先复核来源。'
    if topic == 'scope':
        return artifact['scope']
    if topic == 'area':
        if kind == 'thermal':
            return '面积热阻和单位面积传热系数由材料构造及表面条件决定，不需要建筑总面积作输入；整体构件传热另需构件面积。本次不交付热阻或传热系数数值。'
        if kind == 'scenario':
            return '材料方案单位面积碳量以项目声明建筑面积为分母，不是所选构件面积；金额和碳总量不除以面积。面积未获实楼测量核证。'
        return '清单的单位面积碳指标以声明建筑面积为分母；声明边界总量和各阶段总量不按面积归一化。本次不交付排放数值。'
    if topic == 'period':
        if kind == 'thermal':
            return '本记录为一维稳态热工计算，不是逐时能耗、年度能耗或全年节能率。'
        if kind == 'scenario':
            return '金额对应声明报价日期，碳量覆盖声明评估期；评估期累计量不能称为年量，排除阶段不能记作零。'
        return '清单及阶段碳量覆盖声明评估期；标为年度活动的输入按评估年数累计，结果不能直接称为年排放。排除阶段不记为零。'
    # Meaning-only review lists field semantics and units, never source values.
    rows = facts(record, kind)
    return ('；'.join(f"{f['label']}（{f['unit']}）" for f in rows) +
            '。仅说明当前可用字段的含义和单位，不交付数值或诊断结论。') if rows else '当前记录没有可支持指标含义解释的数值字段，不能补造。'


def attach(answer, domain, pid, record, reader=None):
    answer = {**answer, 'verification': list(answer.get('verification', [])),
              'checked_reviews': [], 'review_failures': []}
    from .agent_outputs import version
    plan = record.get('output_plan') or {}
    if record.get('professional_reviews') and (plan.get('version') != version() or
            plan.get('question_hash') != core.hash_json(record['question'])):
        answer['review_failures'] = [{'record_id': r['record_id'],
            'notice': '复核契约或问题已变化；旧说明已撤下，请重新读取。'} for r in record['professional_reviews']]
        return answer
    for saved in record.get('professional_reviews', []):
        review = SourceReview.model_validate(saved); spec = inspection(review.kind)
        try:
            current = reader(spec, review.record_id) if reader else spec.service(domain).view(pid, review.record_id)
            if current['project_id'] != pid:
                raise core.ValidationError('Cross-project source review rejected')
            check(current, review)
            item = next(i for i in record['output_plan']['items']
                if any(r['request_key'] == i['request_key'] and r['record_id'] == review.record_id
                       for r in record['read_requests']))
            if item['fact_keys'] or item.get('clarification_question'):
                raise core.ValidationError('Review does not match a nonnumeric output plan')
            artifact = spec.artifact(current)
            answer['checked_reviews'].append({'record_id': review.record_id, 'kind': review.kind,
                'record_hash': current['hash'], 'view_hash': review.view_hash,
                'status': current['status'], 'whole_record_verified': artifact['verified'],
                'checked_at': core.now(), 'report_path': artifact['report_path'],
                'explanations': [{'topic': t, 'text': explanation(t, current, review.kind)} for t in item['explanation_topics']],
                'scope': 'nonnumeric_source_review', 'numeric_values_delivered': False})
            passed = True
        except (ValueError, KeyError, OSError, StopIteration):
            passed = False
            answer['review_failures'].append({'record_id': review.record_id,
                'notice': '来源状态或复核契约已变化；旧说明已撤下，请重新读取。'})
        answer['verification'].append({'record_id': review.record_id,
            'check': 'current_nonnumeric_source_review', 'passed': passed})
    if answer['checked_reviews']:
        answer['task_completion'] = 'partial'
        if not answer.get('checked_statements'):
            answer['summary'] = '已复核所选记录的当前状态或声明口径；本次未交付计算数值。'
            answer['execution_scope'] = 'checked_nonnumeric_source_reviews'
        answer['gaps'] = [g for g in answer.get('gaps', []) if g.get('message') != '本轮没有通过核验的专业交付']
    return answer
