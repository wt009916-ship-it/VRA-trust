"""Declared read-only professional tasks; completed calculation is not certification."""
from dataclasses import dataclass

from . import core
from .agent_artifacts import material_cost_review, cost_answer
from .material_cost import Costs
from .thermal import Thermal
from .lifecycle import Lifecycle


def thermal_review(record):
    result = record['result']
    return {'kind': 'thermal_review', 'record_id': record['thermal_id'], 'project_id': record['project_id'],
            'record_hash': record['hash'], 'name': record['input']['name'], 'status': record['status'],
            'checked_at': core.now(), 'source_status': record['source_status'], 'source_notice': record['source_notice'],
            'input': record['input'], 'result': result,
            'verified': record['status'] == 'calculated' and result is not None and result['u_w_m2k'] is not None,
            'scope': '一维稳态不透明构造；不含热桥、结露或全年节能预测，不判定规范合规。',
            'stale_reasons': record['stale_reasons'],
            'report_path': f"/api/projects/{record['project_id']}/thermal/{record['thermal_id']}/report.html"}


def lifecycle_review(record):
    result = record['result']
    return {'kind': 'lifecycle_review', 'record_id': record['lifecycle_id'], 'project_id': record['project_id'],
            'record_hash': record['hash'], 'name': record['input']['name'], 'status': record['status'],
            'checked_at': core.now(), 'source_status': 'USER_DECLARED',
            'input': record['input'], 'result': result,
            'verified': record['status'] == 'calculated' and result is not None and result['boundary_total_kgco2e'] is not None,
            'scope': '声明边界内的阶段CO₂e清单；不是完整性认证、碳核证或可交易碳资产。',
            'report_path': f"/api/projects/{record['project_id']}/lifecycle/{record['lifecycle_id']}/report.html"}


def professional_answer(artifact, target, selection, *, spec, error=None):
    verified = bool(artifact and artifact['verified'])
    state = artifact['status'] if artifact else 'missing'
    return {'can_simulate': None, 'can_recommend': False, 'workflow_completed': True,
            'task_completion': 'verified' if verified else 'incomplete',
            'execution_scope': spec.kind + '_inspection', spec.target: target, 'selection_basis': selection,
            'artifact': artifact,
            'verification': [{'check': 'current_complete_' + spec.kind + '_read', 'passed': verified,
                              'record_id': target, 'state': state,
                              'meaning': spec.label + '已实际读取，当前来源与计算版本有效且结果完整'}],
            'summary': (spec.label + '核验完成；仅限所声明计算范围，不代表工程合规或认证。') if verified
                       else ('未取得当前完整的' + spec.label + '结果；任务尚未完成。'),
            'task_notice': '本任务只读核验' + spec.label + '，不执行写操作，不要求能耗仿真的IDF/EPW。',
            'gaps': [] if verified else [{'message': error or (spec.label + '状态：' + state),
                                         'action': '补齐记录或缺参，复核来源变化；不复用失效数值。'}],
            'limitations': [artifact['scope']] if artifact else ['未取得可核验记录，不能补造数值、来源或专业结论。']}


@dataclass(frozen=True)
class Inspection:
    kind: str
    record_key: str
    target: str
    argument: str
    list_tool: str
    read_tool: str
    selection: str
    label: str
    service: type
    artifact: object

    def answer(self, artifact, target, selection, *, error=None):
        if self.kind == 'cost':
            return cost_answer(artifact, target, selection, error=error)
        return professional_answer(artifact, target, selection, spec=self, error=error)


INSPECTIONS = {
    'inspect_material_cost': Inspection('cost', 'cost_id', 'target_cost_id', 'material_cost_id',
        'material_cost_list', 'material_cost_read', 'cost_selection_basis', '材料清单', Costs, material_cost_review),
    'inspect_thermal': Inspection('thermal', 'thermal_id', 'target_thermal_id', 'thermal_id',
        'thermal_list', 'thermal_read', 'thermal_selection_basis', '热工构造', Thermal, thermal_review),
    'inspect_lifecycle': Inspection('lifecycle', 'lifecycle_id', 'target_lifecycle_id', 'lifecycle_id',
        'lifecycle_list', 'lifecycle_read', 'lifecycle_selection_basis', '阶段碳清单', Lifecycle, lifecycle_review),
}
