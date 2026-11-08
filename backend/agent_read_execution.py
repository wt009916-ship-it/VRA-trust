"""Execute a frozen, user-scoped read plan. No model-generated numeric delivery."""
from . import core, agent_outputs, agent_reviews
from .agent_semantics import Statement, inspection, can_deliver_requested_facts
from .agent_recovery import RecordsUnavailable


def event_reserve(requests):
    # Each result: read + delivery + final read; a missing result uses read +
    # absence receipt + shared final catalog check. Availability has one batch
    # and one final recheck. No extra inference rounds or expanded event budget.
    return 3 * sum(r['purpose'] == 'results' for r in requests) + 2 * any(
        r['purpose'] == 'availability' for r in requests)


def execute(record, invoke, *, cancelled):
    rows = []
    for request in record['read_requests']:
        if cancelled():
            raise core.ValidationError('Task cancelled during declared read execution')
        if request['purpose'] != 'results':
            continue
        key, kind, ident = request['request_key'], request['kind'], request['record_id']
        wanted = agent_outputs.requirement(record, key)
        if wanted.get('clarification_question'):
            rows.append({'request_key': key, 'record_id': ident, 'state': 'needs_clarification'})
            continue
        spec = inspection(kind)
        row = {'request_key': key, 'record_id': ident, 'state': 'failed'}
        try:
            try:
                source = invoke(spec.read_tool, {spec.argument: ident})
            except RecordsUnavailable:
                invoke('professional_missing', {'missing': {'kinds': [kind], 'record_id': ident}})
                row['state'] = 'absence_submitted'
                rows.append(row)
                continue
            row['source_hash'] = source['hash']
            common = {'kind': kind, 'record_id': ident, 'record_hash': source['hash'], 'finish': False}
            required = wanted['fact_keys']
            if not required and wanted['explanation_topics']:
                invoke('professional_review', {'review': agent_reviews.reference(source, kind)})
                row['state'] = 'source_review_submitted'
            elif not can_deliver_requested_facts(source, kind, required):
                invoke('professional_limit', {'limitation': {**common, 'status': source['status']}})
                row['state'] = 'limitation_submitted'
            else:
                facts = {f['fact']: f for f in source['explanation_facts']}
                statements = [{field: facts[fact][field] for field in Statement.model_fields}
                              for fact in required if fact in facts]
                row['missing_fact_keys'] = [fact for fact in required if fact not in facts]
                if statements:
                    invoke('professional_deliver', {'delivery': {**common, 'statements': statements}})
                row['state'] = 'facts_submitted' if not row['missing_fact_keys'] else 'source_fields_unavailable'
        except (ValueError, KeyError, OSError):
            # Tool events retain the exact failure. Never reinterpret a refusal,
            # parser failure or permission failure as absence, or retry a write.
            row['error'] = 'See failed tool event; no substitute record or numeric fallback.'
        rows.append(row)
    keys = [r['request_key'] for r in record['read_requests'] if r['purpose'] == 'availability' and not agent_outputs.requirement(record, r['request_key']).get('clarification_question')]
    if keys:
        if cancelled():
            raise core.ValidationError('Task cancelled during declared read execution')
        try:
            invoke('requested_availability', {'request_keys': keys})
            state = 'availability_submitted'
        except (ValueError, KeyError, OSError):
            state = 'failed'
        rows.extend({'request_key': key, 'state': state} for key in keys)
    return {'origin': 'application_from_frozen_read_plan', 'requests': rows,
            'intent_verified': False, 'final_source_check_required': True,
            'notice': 'Application executes declared read scopes; this is not autonomous model tool selection, verified user intent, or an engineering certification.'}
