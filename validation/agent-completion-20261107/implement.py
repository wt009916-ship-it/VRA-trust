HELPER = "\ndef next_actions(record):\n    \"\"\"Suggestions from declared scopes and observed reads; never execute or infer scope.\"\"\"\n    waiting = set(pending(record))\n    reads = {}\n    unavailable = set()\n    for event in record.get('events', []):\n        unavailable.update(event.get('recovery', {}).get('unavailable_record_ids', []))\n        if event['status'] != 'succeeded':\n            continue\n        for request in record.get('read_requests', []):\n            spec = inspection(request['kind'])\n            if event['tool'] == spec.read_tool:\n                current = event['result']\n                reads[current[spec.record_key]] = current\n    actions = []\n    availability_keys = []\n    for request in record.get('read_requests', []):\n        if request['request_key'] not in waiting:\n            continue\n        if request['purpose'] == 'availability':\n            availability_keys.append(request['request_key'])\n            continue\n        ident = request['record_id']; kind = request['kind']; spec = inspection(kind)\n        current = reads.get(ident)\n        action = {'request_key': request['request_key'], 'record_id': ident}\n        if current is not None:\n            if not spec.artifact(current)['verified']:\n                action.update(tool='professional_limit', arguments={'limitation': {\n                    'kind': kind, 'record_id': ident, 'record_hash': current['hash'],\n                    'status': current['status'], 'finish': False}})\n            else:\n                action.update(tool='professional_deliver', arguments={'delivery': {\n                    'kind': kind, 'record_id': ident, 'record_hash': current['hash'], 'finish': False}},\n                    required_fields=['delivery.statements'],\n                    available_facts=current.get('explanation_facts', []))\n        elif ident in unavailable:\n            action.update(tool='professional_missing', arguments={'missing': {\n                'kinds': [kind], 'record_id': ident, 'finish': False}})\n        else:\n            action.update(tool=spec.read_tool, arguments={spec.argument: ident})\n        actions.append(action)\n    if availability_keys:\n        actions.append({'tool': 'requested_availability',\n                        'arguments': {'request_keys': availability_keys, 'finish': False}})\n    return actions\n\n\ndef commentary_review(record, text):\n    \"\"\"Exact identifier membership only, not validation of numerical or semantic prose.\"\"\"\n    allowed = {r['record_id'] for r in record.get('read_requests', []) if r.get('record_id')}\n    mentioned = set(re.findall(\n        r'\\b(?:thermal|lifecycle|cost|engineering|schedule|operation)_[A-Za-z0-9_-]+\\b', text or ''))\n    unknown = sorted(mentioned - allowed)\n    return {'status': 'reference_mismatch' if unknown else 'references_match',\n            'unknown_record_ids': unknown, 'allowed_record_ids': sorted(allowed),\n            'scope': 'declared_record_identifiers_only', 'semantics_verified': False}\n"
from pathlib import Path
p=Path('backend/agent_requests.py');s=p.read_text(encoding='utf-8').replace('from pathlib import Path','import re\nfrom pathlib import Path',1)
s+=HELPER
old="    answer['checked_availability']=checked"
new="""    if record.get('termination'):
        answer['termination'] = record['termination']
    answer['checked_availability']=checked"""
assert s.count(old)==1;s=s.replace(old,new)
p.write_text(s,encoding='utf-8',newline='\n')
p=Path('backend/agent.py');s=p.read_text(encoding='utf-8')
old="                        if body.read_requests:pending['declared_read_requests_without_delivery']=requested_scopes.pending(record)"
new="""                        if body.read_requests:
                            pending['declared_read_requests_without_delivery'] = requested_scopes.pending(record)
                            pending['declared_next_actions'] = requested_scopes.next_actions(record)"""
assert s.count(old)==1;s=s.replace(old,new)
old="                        record['llm_commentary'] = answer.get('content')"
new="""                        record['llm_commentary'] = answer.get('content')
                        if body.read_requests:
                            review = requested_scopes.commentary_review(record, answer.get('content'))
                            record['llm_commentary_review'] = review
                            provider_event.update(commentary_review=review, model_commentary=answer.get('content'))
                            if review['status'] == 'reference_mismatch' and turn < 4:
                                messages[-1] = {'role': 'assistant', 'content': '上一段文字含不匹配的记录编号，原文已保留审计；不能当作正确引用。'}
                                messages.append({'role': 'user', 'content': '请按本轮声明逐字核对引用编号：' + json.dumps(review, ensure_ascii=False)
                                    + '。不得自行纠正为另一个未声明记录。还未正式交付的目标请按declared_next_actions执行；不增加范围或预算。'})
                                continue"""
assert s.count(old)==1;s=s.replace(old,new)
old="'。按声明目的逐项核验；不得替换编号、扩展范围或计算。'"
new="'。按当前控制流程状态的declared_next_actions选择对应工具；失效记录须professional_limit正式交付，不能只写解释。建议未执行不算完成；不得替换编号、扩展范围或计算。'"
assert s.count(old)==1;s=s.replace(old,new)
old="""                else:
                    raise core.ValidationError('Provider iteration budget exhausted')
            # Authoritative decision fields"""
new="""                else:
                    if not body.read_requests:
                        raise core.ValidationError('Provider iteration budget exhausted')
                    # A stopped model is not a completed task. Recheck submitted
                    # receipts within the reserved budget; missing goals stay visible.
                    record['termination'] = {
                        'reason': 'response_budget_exhausted', 'model_declared_finished': False,
                        'pending_request_keys': requested_scopes.pending(record)}
                if body.read_requests:
                    record.setdefault('termination', {
                        'reason': 'model_finish' if record.get('model_finished_delivery') else 'model_commentary',
                        'model_declared_finished': bool(record.get('model_finished_delivery')),
                        'pending_request_keys': requested_scopes.pending(record)})
            # Authoritative decision fields"""
assert s.count(old)==1;s=s.replace(old,new)
p.write_text(s,encoding='utf-8',newline='\n')
