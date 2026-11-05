"""Current, source-bound task deliverables. Model prose supplies no values or methods."""
from decimal import Decimal

from . import core


def material_cost_review(record):
    """Only pass a record obtained from Costs.view, never a saved unchecked snapshot."""
    base = {'kind': 'material_cost_review', 'cost_id': record['cost_id'], 'project_id': record['project_id'], 'name': record['input']['name'],
            'record_hash': record['hash'], 'status': record['status'], 'checked_at': core.now(),
            'scope': '已声明材料清单核算；不是市场报价验证、工程总价或招投标认证。',
            'currency': record['input']['currency'], 'functional_scope': record['input']['functional_scope'],
            'exclusions': record['input']['exclusions'], 'as_of': record['input']['as_of'],
            'tax_basis': record['input']['tax_basis'], 'source_status': 'USER_DECLARED',
            'material_total': None, 'rows': [], 'missing_lines': [], 'verified': False}
    result = record['result']
    if not result:
        return {**base, 'notice': '来源、项目或计算版本已变化，历史数值不可作为当前结果。'}
    inputs = {x['line_id']: x for x in record['input']['lines']}
    rows = []
    for row in result['rows']:
        line = inputs[row['line_id']]
        item = row['unit'] == 'item'
        rows.append({k: row[k] for k in ('line_id', 'material_id', 'name', 'unit', 'net_quantity',
                    'purchase_quantity', 'quantity_in_quote_unit', 'quote_unit', 'amount', 'missing')} | {
            'quantity_method': 'item_ceiling' if item else 'net_times_waste',
            'quantity_method_text': '净量×(1+损耗率)，按件逐行向上取整' if item else '净量×(1+损耗率)，此计量单位不向上取整',
            'waste_ratio': None if line['waste_ratio'] is None else str(Decimal(str(line['waste_ratio']))),
            'unit_price': None if line['quote']['unit_price'] is None else str(Decimal(str(line['quote']['unit_price']))),
            'money_method': '计价数量×单价，每行HALF_UP保留两位小数后求和',
            'quantity_source': line['measure']['source'], 'waste_source': line['waste_basis'],
            'price_source': line['quote']['source'], 'price_version': line['quote']['version'],
            'price_valid_from': line['quote']['valid_from'], 'price_valid_until': line['quote']['valid_until'],
            'density_kg_m3': line['density_kg_m3'], 'density_source': line['density_source'],
            'source_pointers': {'result': '/result/rows/' + str(len(rows)),
                                'input_line_id': row['line_id']}})
    return {**base, 'material_total': result['material_total'], 'rows': rows,
            'missing_lines': result['missing_lines'],
            'verified': record['status'] == 'calculated' and result['material_total'] is not None,
            'notice': '数值及方法来自当前核验后的清单，不采纳模型自由文字作为计算依据。'}


def cost_answer(artifact, target, selection, *, error=None):
    verified = bool(artifact and artifact['verified'])
    state = artifact['status'] if artifact else 'missing'
    return {'can_simulate': None, 'can_recommend': False, 'workflow_completed': True,
            'task_completion': 'verified' if verified else 'incomplete',
            'execution_scope': 'material_cost_inspection', 'target_cost_id': target, 'selection_basis': selection,
            'artifact': artifact,
            'verification': [{'check': 'current_complete_material_cost_read', 'passed': verified, 'cost_id': target,
                              'state': state, 'meaning': '指定材料清单已实际读取，当前来源与计算版本有效且合计完整'}],
            'summary': '材料清单核验完成；仅限声明范围与来源，不是工程总造价或价格认证。' if verified
                       else '未取得当前完整的材料清单结果；任务尚未完成。',
            'task_notice': '目标是实际读取并核验材料清单；不要求能耗IDF/EPW，不执行计算写操作。',
            'gaps': [] if verified else [{'message': error or ('材料清单状态：' + state),
                'action': '请创建清单、补齐缺参或核对已变化的来源；不会复用失效数值。'}],
            'limitations': ['数量、损耗、价格及其来源由用户声明。', '材料功能等效、市场真实性、工程安全和认证未评估。']}
