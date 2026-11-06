"""Model transport for native sizing; full domain results remain in the audit."""
from copy import deepcopy

from . import core


PAGE_SIZE = 5
NOTICE = ('这是分区显热设计工况，不是全楼同时峰值、总冷量或设备选型结论；'
          '原生倍率已应用，不再次相乘。设计日来源与当地适用性未独立验证。')


def summary(receipt, run_id):
    result = {key: deepcopy(receipt.get(key)) for key in (
        'status', 'reason', 'policy_version', 'parser_sha256', 'model_sha256', 'sql_sha256',
        'weather_sha256', 'site_comparison', 'site_applicability', 'tabular_crosscheck',
        'building_coincident_peak_W', 'limitations')}
    rows = receipt.get('rows')
    result.update(receipt_hash=core.hash_json(receipt), row_count=len(rows) if isinstance(rows, list) else None,
                  rows=None, details_delivered=False,
                  projection_notice='模型摘要未发送负荷行或完整IDF依据，不能声称已读取明细。完整结果保留在工具审计和报告JSON。' + NOTICE)
    if receipt.get('status') == 'calculated_model_scenario' and rows:
        result['detail_request'] = {'tool': 'simulation_result', 'arguments': {
            'run_id': run_id, 'zone_offset': 0, 'zone_hash': result['receipt_hash']}}
        result['page_size'] = PAGE_SIZE
    return result


def model_result(tool, result):
    """Project only known simulation envelopes, without mutating their audit snapshots."""
    def run(view, list_entry=False):
        if not isinstance(view, dict):
            return view
        if list_entry and isinstance(view.get('weather_quality'), dict):
            weather = view['weather_quality']
            view = {**view, 'weather_quality': {k: v for k, v in weather.items() if k != 'fields'},
                    'weather_projection': {'receipt_hash': core.hash_json(weather), 'field_statistics_delivered': False,
                        'notice': '列表摘要未发送逐字段天气统计；按run_id单独simulation_result可读取。完整回执保留在审计。'}}
        metrics = view.get('metrics')
        if not isinstance(metrics, dict) or not isinstance(metrics.get('zone_design_loads'), dict):
            return view
        return {**view, 'metrics': {**metrics,
            'zone_design_loads': summary(metrics['zone_design_loads'], view['run_id'])}}

    if tool in {'simulation_result', 'simulation_status'}:
        return [run(v, list_entry=True) for v in result] if isinstance(result, list) else run(result)
    if tool in {'report_generate', 'certificate_generate'} and isinstance(result, dict) and 'run' in result:
        return {**result, 'run': run(result['run'])}
    if tool == 'scheme_compare' and isinstance(result, dict) and 'results' in result:
        return {**result, 'results': [run(v) for v in result['results']]}
    return result


def page(view, offset, expected_hash):
    """Read one explicitly selected page of a currently validated run, never a cached row."""
    receipt = (view.get('metrics') or {}).get('zone_design_loads')
    if view.get('status') != 'succeeded' or not isinstance(receipt, dict):
        raise core.ValidationError('Current run has no valid sizing result; stale/failed rows are unavailable')
    if core.hash_json(receipt) != expected_hash:
        raise core.ValidationError('Sizing receipt changed; read the current simulation_result summary before paging')
    rows = receipt.get('rows')
    if receipt.get('status') != 'calculated_model_scenario' or not isinstance(rows, list) or not rows:
        raise core.ValidationError('Design loads unavailable; do not treat missing rows as zero load')
    if offset >= len(rows):
        raise core.ValidationError('Sizing page offset exceeds the current row count')
    selected = deepcopy(rows[offset:offset + PAGE_SIZE])
    day_names = {(row.get('peak') or {}).get('design_day', '').upper() for row in selected}
    days = [{k: deepcopy(v) for k, v in day.items() if k != 'raw_fields'}
            for day in receipt['basis']['design_days'] if day['name'].upper() in day_names]
    next_offset = offset + len(selected)
    return {'schema_version': 'vra.agent.design-load-page.v1', 'run_id': view['run_id'],
            'project_id': view['project_id'], 'status': receipt['status'], 'run_status': view['status'],
            'receipt_hash': expected_hash, 'source': {k: receipt[k] for k in (
                'model_sha256', 'sql_sha256', 'weather_sha256', 'parser_sha256', 'policy_version')},
            'row_count': len(rows), 'offset': offset, 'rows': selected,
            'next_offset': next_offset if next_offset < len(rows) else None,
            'entire_receipt_delivered': offset == 0 and next_offset == len(rows),
            'design_days': days, 'site_comparison': receipt['site_comparison'],
            'building_coincident_peak_W': None, 'limitations': deepcopy(receipt['limitations']),
            'notice': '仅交付当前页；next_offset为null只表示到达末尾，不证明此前各页已读取。完整IDF原始字段未发送，见报告JSON。' + NOTICE}
