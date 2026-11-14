"""Bounded post-work rule comparison; never a diagnosis or equipment-health certificate.

The workflow service must supply CURRENT Operations.view records and bind their
sources transactionally before persisting a recheck. This module performs no write.
"""
from datetime import datetime
from . import core


def instant(value):
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if result.tzinfo is None or result.utcoffset() is None:
            raise ValueError('Offset required')
        return result
    except (ValueError, TypeError, AttributeError) as exc:
        raise core.ValidationError('Recheck requires explicit offset-aware times') from exc


def select_event(record, rule_id, event_index):
    if record.get('status') == 'stale' or record.get('result') is None:
        raise core.ValidationError('Current operation evidence required')
    rule = next((r for r in record['result']['rules'] if r['rule_id'] == rule_id), None)
    if rule is None or isinstance(event_index, bool) or not isinstance(event_index, int) or not 0 <= event_index < len(rule['events']):
        raise core.ValidationError('Select one available source-bound rule event')
    return rule, rule['events'][event_index]


def assess(before, after, rule_id, event_index, work_completed_at, minimum_observation_seconds):
    """A no-event result alone is insufficient: require comparable, fresh coverage."""
    _, event = select_event(before, rule_id, event_index)
    if after.get('status') == 'stale' or after.get('result') is None:
        raise core.ValidationError('Current recheck evidence required')
    if before['project_id'] != after['project_id']:
        raise core.ValidationError('Cross-project recheck rejected')
    if before['operation_id'] == after['operation_id'] or before['file_snapshot']['hash'] == after['file_snapshot']['hash']:
        raise core.ValidationError('Recheck requires a different source, not a duplicate record or file')
    original, new = before['input'], after['input']
    if original['clock_basis'] != 'offset_aware' or new['clock_basis'] != 'offset_aware':
        raise core.ValidationError('Post-work chronology requires offset-aware source timestamps')
    for field in ('equipment', 'data_nature', 'channels', 'expected_interval_seconds', 'maximum_gap_seconds'):
        if original[field] != new[field]:
            raise core.ValidationError('Incomparable recheck channel, unit or cadence declaration')
    source_rule = next(r for r in original['rules'] if r['rule_id'] == rule_id)
    next_rule = next((r for r in new['rules'] if r['rule_id'] == rule_id), None)
    if source_rule != next_rule:
        raise core.ValidationError('Recheck rule changed; relaxing thresholds cannot prove recovery')
    if isinstance(minimum_observation_seconds, bool) or not isinstance(minimum_observation_seconds, (float, int)) or not 0 < minimum_observation_seconds <= 604800:
        raise core.ValidationError('Declare a positive bounded observation requirement')
    completed = instant(work_completed_at)
    if completed < instant(event['end']):
        raise core.ValidationError('Work completion cannot precede the selected event')
    q = after['result']['quality']
    start, end = instant(q['first_time']), instant(q['last_time'])
    if start <= completed or start <= instant(before['result']['quality']['last_time']):
        raise core.ValidationError('Recheck window must follow work and must not overlap the original window')
    result = next((r for r in after['result']['rules'] if r['rule_id'] == rule_id), None)
    if result is None:
        raise core.ValidationError('Selected rule result missing')
    span = (end - start).total_seconds()
    required = max(minimum_observation_seconds, source_rule['minimum_duration_seconds'])
    gaps = []
    if span < required:
        gaps.append('observation_window_too_short')
    if q['cell_issue_count'] or q['gap_count'] or q['irregular_intervals']:
        gaps.append('source_quality_or_cadence')
    # A derivative has one unavailable first sample by definition. Permit only
    # that exact unknown count when all source cells and cadence are valid.
    expected_unknown = 1 if source_rule['kind'] == 'rate' else 0
    if result['unknown_samples'] != expected_unknown or result['excluded_by_gate_samples']:
        gaps.append('unknown_or_gated_samples')
    if result['evaluated_samples'] != q['sample_count'] - expected_unknown or result['evaluated_samples'] < 2:
        gaps.append('insufficient_evaluated_coverage')
    violating = result['violating_samples'] > 0 or result['event_count'] > 0
    outcome = 'rule_violation_remains' if violating else 'inconclusive' if gaps else 'no_violation_in_observed_window'
    return {'outcome': outcome, 'eligible_for_human_closure': outcome == 'no_violation_in_observed_window',
            'gaps': gaps, 'observed_seconds': span, 'required_seconds': required,
            'evaluated_samples': result['evaluated_samples'], 'violating_samples': result['violating_samples'],
            'before_id': before['operation_id'], 'after_id': after['operation_id'],
            'rule_id': rule_id, 'source_event': event, 'work_completed_at': work_completed_at,
            'data_nature': new['data_nature'], 'source_status': 'USER_DECLARED',
            'cause_confirmed': False, 'equipment_health': 'NOT_ASSESSED',
            'limitations': ['只证明声明测点、规则和新观测窗口；不是设备健康或根因确诊。',
                            '设备身份、维修事实与工况可比性仍须有人工记录和依据；不自动下发控制。']}
