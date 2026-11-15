"""Current source-bound standard citations, never model-written compliance advice."""
from . import core
from .standards import Standards, query_identity


def searches(record):
    return [e for e in record.get('events', []) if e['tool'] == 'standards_search' and e['status'] == 'succeeded']


def attach(answer, domain, pid, record):
    events = searches(record)
    if not events:
        return answer
    answer = {**answer, 'checked_standards': [], 'standard_query_progress': []}
    try:
        snapshot = core.hash_json(Standards(domain).catalog(pid))
    except (ValueError, KeyError, OSError):
        snapshot = None
    for index, event in enumerate(events):
        result = event.get('result') or {}
        try:
            retriever = query_identity(result)
        except core.ValidationError:
            retriever = None
        current = (retriever is not None and snapshot is not None and result.get('catalog_hash') == snapshot and
                   result.get('retriever_hash') == retriever and
                   event.get('result_hash') == core.hash_json(result))
        answer['standard_query_progress'].append({'query_index': index + 1,
            'state': 'current' if current else 'source_unverified',
            'outcome': result.get('status') if current else None})
        if current:
            answer['checked_standards'].append({'query_index': index + 1, 'project_id': pid, 'result': result})
    answer['standard_query_coverage'] = 'all_selected_queries_current' if len(answer['checked_standards']) == len(events) else 'incomplete'
    answer['task_completion'] = 'partial' if answer['checked_standards'] else answer.get('task_completion', 'incomplete')
    answer['standard_query_notice'] = '仅核验模型实际选择的查询及当前索引，不证明原问题已完整覆盖，也不作规范适用性或工程合规结论。'
    if answer['checked_standards']:
        if not answer.get('checked_statements'):
            answer['summary'] = '已核验所选规范查询的当前来源；逐项查看引文、缺失或冲突，不代表原问题完整覆盖或合规。'
        answer['gaps'] = [g for g in answer.get('gaps', []) if g.get('message') != '本轮没有通过核验的专业交付']
    return answer
