"""Declared read-only professional tasks; completed calculation is not certification."""
from dataclasses import dataclass

from . import core, agent_energy
from .agent_artifacts import material_cost_review, cost_answer
from .material_cost import Costs
from .thermal import Thermal
from .lifecycle import Lifecycle
from .engineering import Engineering
from .construction import Schedules
from .operations import Operations
from .agent_scenarios import ScenarioReads, review as scenario_review, name as scenario_name


def record_name(record):
    return scenario_name(record) if "scenario_id" in record else record["input"]["name"]


def engineering_review(record):
    return bounded_review(record, 'engineering', 'engineering_id',
        '矩形等截面、恒定EI、小挠度线弹性梁；仅辅助分析，不评估承载能力、结构安全或合规。')


def schedule_review(record):
    return bounded_review(record, 'schedule', 'schedule_id',
        '连续经过日、FS关系的关键路径及显式剩余工期情景；资源冲突未调平，不是施工安全审批或履约保证。')


def operation_review(record):
    return bounded_review(record, 'operation', 'operation_id',
        '声明CSV、时钟与阈值下的规则筛查；事件可跨规则重叠，不是故障数量或根因确诊，无事件不证明健康。')


def bounded_review(record, kind, key, scope):
    result = record['result']
    complete = record['status'] == 'calculated'
    if kind == 'operation' and result:
        complete = not (result['quality']['cell_issue_count'] or result['quality']['gap_count']) and all(
            r['evaluated_samples'] > 0 and r['unknown_samples'] == 0 for r in result['rules'])
    route = {'engineering':'beam-analyses', 'schedule':'schedules', 'operation':'operations'}[kind]
    return {'kind':kind + '_review', 'record_id':record[key], 'project_id':record['project_id'],
            'record_hash':record['hash'], 'name':record['input']['name'], 'status':record['status'], 'stale_reasons':record.get('stale_reasons', []), 'stale_details':record.get('stale_details', []),
            'checked_at':core.now(), 'source_status':'USER_DECLARED', 'scope':scope,
            'input':record['input'], 'result':result, 'verified':bool(result and complete),
            'report_path':f"/api/projects/{record['project_id']}/{route}/{record[key]}/report.html"}


def thermal_review(record):
    result = record['result']
    return {'kind': 'thermal_review', 'record_id': record['thermal_id'], 'project_id': record['project_id'],
            'record_hash': record['hash'], 'name': record['input']['name'], 'status': record['status'], 'stale_reasons':record.get('stale_reasons', []), 'stale_details':record.get('stale_details', []),
            'checked_at': core.now(), 'source_status': record['source_status'], 'source_notice': record['source_notice'],
            'input': record['input'], 'result': result,
            'verified': record['status'] == 'calculated' and result is not None and result['u_w_m2k'] is not None,
            'scope': '一维稳态不透明构造；不含热桥、结露或全年节能预测，不判定规范合规。',
            'report_path': f"/api/projects/{record['project_id']}/thermal/{record['thermal_id']}/report.html"}


def lifecycle_review(record):
    result = record['result']
    return {'kind': 'lifecycle_review', 'record_id': record['lifecycle_id'], 'project_id': record['project_id'],
            'record_hash': record['hash'], 'name': record['input']['name'], 'status': record['status'], 'stale_reasons':record.get('stale_reasons', []), 'stale_details':record.get('stale_details', []),
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
    'inspect_enduse': Inspection('enduse','enduse_id','target_enduse_id','enduse_id','end_use_list','end_use_read','enduse_selection_basis','原生设备用途账',agent_energy.EndUseReads,lambda r:agent_energy.review(r,'enduse')),
    'inspect_utility': Inspection('utility','utility_id','target_utility_id','utility_id','utility_comparison_list','utility_comparison_read','utility_selection_basis','账单模拟比较',agent_energy.UtilityReads,lambda r:agent_energy.review(r,'utility')),
    'inspect_material_scenarios': Inspection('scenario', 'scenario_id', 'target_scenario_id', 'scenario_id',
        'material_scenarios_list', 'material_scenarios_read', 'scenario_selection_basis', '材料两方案对照', ScenarioReads, scenario_review),
    'inspect_material_cost': Inspection('cost', 'cost_id', 'target_cost_id', 'material_cost_id',
        'material_cost_list', 'material_cost_read', 'cost_selection_basis', '材料清单', Costs, material_cost_review),
    'inspect_thermal': Inspection('thermal', 'thermal_id', 'target_thermal_id', 'thermal_id',
        'thermal_list', 'thermal_read', 'thermal_selection_basis', '热工构造', Thermal, thermal_review),
    'inspect_lifecycle': Inspection('lifecycle', 'lifecycle_id', 'target_lifecycle_id', 'lifecycle_id',
        'lifecycle_list', 'lifecycle_read', 'lifecycle_selection_basis', '阶段碳清单', Lifecycle, lifecycle_review),
    'inspect_engineering': Inspection('engineering', 'engineering_id', 'target_engineering_id', 'engineering_id',
        'beam_analysis_list', 'beam_analysis_read', 'engineering_selection_basis', '限定梁分析', Engineering, engineering_review),
    'inspect_schedule': Inspection('schedule', 'schedule_id', 'target_schedule_id', 'schedule_id',
        'schedule_list', 'schedule_read', 'schedule_selection_basis', '施工进度', Schedules, schedule_review),
    'inspect_operations': Inspection('operation', 'operation_id', 'target_operation_id', 'operation_id',
        'operations_list', 'operations_read', 'operation_selection_basis', '设备规则核查', Operations, operation_review),
}
