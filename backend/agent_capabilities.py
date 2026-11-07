"""Versioned application scope, not a claim that a project or a model is certified."""
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from . import core
from .schema import Contract


CapabilityId = Literal[
    'thermal_resistance', 'energy_simulation', 'lifecycle_inventory', 'beam_analysis',
    'material_cost', 'schedule_cpm', 'operations_rules', 'standards_retrieval',
    'cad_bim_read', 'drawing_ocr', 'structural_safety_certification',
    'carbon_credit_issuance', 'energy_compliance_certification',
    'drawing_structural_reconstruction', 'equipment_fault_diagnosis', 'site_safety_approval',
]


class Claim(Contract):
    capability_id: CapabilityId
    assessment: Literal['supported_with_limits', 'not_supported']
    reason_code: Literal['implemented_bounded_method', 'outside_application_scope']


class Explanation(Contract):
    catalog_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    claims: list[Claim] = Field(min_length=1, max_length=16,
        description='Aggregate every requested capability actually read, across lookup batches of at most four. Never interpret a batch limit as lack of application support.')
    finish: bool = False

    @model_validator(mode='after')
    def unique(self):
        if len({c.capability_id for c in self.claims}) != len(self.claims):
            raise ValueError('Duplicate capability claim')
        return self


# Explicitly maintained scope of active modules. Hashes bind revisions, not proof of correctness.
ENTRIES = {
    'thermal_resistance': ('构造热阻与传热系数', 'thermal.py', True,
        '逐层厚度、导热系数、修正系数及表面热阻的一维稳态计算；不含热桥、结露和全年节能率。',
        '可在热工工作台提交有单位和来源的参数；缺参保留未知，输入有效性和来源需另行核验。'),
    'energy_simulation': ('建筑能耗仿真', 'core.py', True,
        '已接入真实EnergyPlus、全年能耗和限定9.0.1分区显热设计负荷原生SQL核验；分区峰值不能相加代替全楼同时峰值，也不等于设备总冷量。参考运行不是实楼校准或节能合规认证。',
        '需可用引擎、适用模型/天气及当前资料准入；本说明不证明当前依赖已就绪或该项目可运行。'),
    'lifecycle_inventory': ('声明边界的阶段碳清单', 'lifecycle.py', True,
        '按明确五阶段边界、活动量、因子、单位和期间核算CO₂e；不证明清单完整性或签发碳信用。',
        '可提交活动量、因子来源/版本、功能单位和年限；核算结果与核证、碳资产签发分开。'),
    'beam_analysis': ('限定线弹性梁分析', 'engineering.py', True,
        '等截面矩形、恒定EI、小挠度梁辅助分析；不含承载能力、屈曲、动力和完整结构安全评估。',
        '可在梁工作台明确几何、材料、荷载、支承和来源后计算；应力或挠度结果不能当作安全认证。'),
    'material_cost': ('材料清单成本', 'material_cost.py', True,
        '按声明净量、损耗、采购规则和有效报价逐行十进制核算；不等于工程总价或市场报价验证。',
        '可提交有单位和来源的数量、损耗、币种、税口径、报价日期及排除项。'),
    'schedule_cpm': ('限定施工关键路径', 'construction.py', True,
        '连续经过日、FS关系和非负间隔的关键路径及显式情景；不含资源调平或现场施工安全审批。',
        '可提交工序、工期、关系和来源；结果不保证施工履约，日历与现场约束需专业复核。'),
    'operations_rules': ('设备运行规则核查', 'operations.py', True,
        '对声明序列和阈值识别异常事件、缺测与检查建议；无告警不证明健康，告警不等于故障根因。',
        '可提交有来源的设备数据和规则；维修决策仍需现场诊断与专业复核。'),
    'standards_retrieval': ('项目规范条款检索', 'standards.py', True,
        '检索本项目已复核的条款索引，保留名称、版本与定位；未命中不证明条款不存在，也不自动判合规。',
        '需合法来源、有效版本和适用范围；没有原文依据时不得编造规范或条款。'),
    'cad_bim_read': ('限定CAD/BIM读取', 'cad.py', True,
        '已接入DXF/IFC的限定只读解析、属性、关系及部分几何；不支持原生DWG或任意无损格式转换。',
        '需受支持且有效的文件和解析依赖；几何近似、声明量、遗漏与单位必须分别核对。'),
    'drawing_ocr': ('图纸文字候选与人工复核', 'drawings.py', True,
        '支持图像/PDF页文字候选、人工更正、独立纠偏/过滤版本、坐标回溯与用户声明尺度冲突检查；OCR分数和线方向支持率不是正确概率。',
        '需可用OCR依赖与有效文件；不自动推断缺失墙体、尺寸、配筋或跨图工程关系。'),
    'structural_safety_certification': ('结构安全认证', 'engineering.py', False,
        '应用没有结构安全认证或完整承载能力评估能力。即使梁记录和全部资料齐全，也不能由本应用签发结构安全结论。',
        '可使用限定梁分析辅助复核；完整结构评估和认证需另行由具备相应能力与责任的专业流程完成。'),
    'carbon_credit_issuance': ('可交易碳信用签发', 'lifecycle.py', False,
        '应用不签发、登记或认证可交易碳信用。完整碳清单、排放因子或节能计算不能解除这个能力限制。',
        '可核算声明边界排放作为准备资料；项目资格、核证、登记与签发属于另行开展的外部专业流程。'),
    'energy_compliance_certification': ('建筑节能合规认证', 'thermal.py', False,
        '应用不出具整栋建筑的节能合规认证。U值、仿真结果或IDF/EPW准入通过均不能代替适用规范和完整工程审查。',
        '可提供热工/能耗计算及有来源条款检索辅助复核；不能承诺补齐输入后自动获得合规认证。'),
    'drawing_structural_reconstruction': ('缺失结构信息自动复原', 'drawings.py', False,
        '应用不能把原图中没有证据的承重墙、配筋或尺寸自动补成真实工程数据；人工确认也不把推测变成实测。',
        '保留原件与缺口，利用文字候选和人工复核整理已知信息；缺失结构信息需补证或现场调查。'),
    'equipment_fault_diagnosis': ('设备故障根因确诊', 'operations.py', False,
        '应用不能仅凭规则告警确诊故障根因，也不能保证维修方案有效；数据完整仍不等于具备自动确诊能力。',
        '可输出异常事件和检查建议，结合现场测量、设备资料与专业诊断决定维修措施。'),
    'site_safety_approval': ('现场施工安全审批', 'construction.py', False,
        '应用不执行现场施工安全审批；关键路径、无资源冲突或工序记录齐全不证明现场可安全施工。',
        '可用进度计算整理计划，专项施工方案和现场风险需要另行专业审查与管理。'),
}

RELATED = {
    'thermal_resistance': ['energy_compliance_certification'],
    'lifecycle_inventory': ['carbon_credit_issuance'],
    'beam_analysis': ['structural_safety_certification'],
    'schedule_cpm': ['site_safety_approval'],
    'operations_rules': ['equipment_fault_diagnosis'],
    'standards_retrieval': ['energy_compliance_certification'],
    'drawing_ocr': ['drawing_structural_reconstruction'],
    'equipment_fault_diagnosis': ['operations_rules'],
    'energy_compliance_certification': ['thermal_resistance', 'standards_retrieval'],
    'structural_safety_certification': ['beam_analysis'],
    'carbon_credit_issuance': ['lifecycle_inventory'],
    'site_safety_approval': ['schedule_cpm'],
    'drawing_structural_reconstruction': ['drawing_ocr'],
}


def initial_project_context(project):
    """Only initial routing context: raw metadata is retained in the audit and explicit reads."""
    return {'project_id': project['project_id'], 'revision': project['revision'],
            'declared_area_m2': project['building']['area_m2'],
            'projection_notice': '初始路由仅提供项目身份、修订和声明面积。名称、备注等自由文本未发送；完整项目保留在控制流程审计，必要时可显式project_get读取。不把项目文字当作应用权限或认证依据。'}


def catalog(ids):
    if not ids or len(ids) > 4 or len(set(ids)) != len(ids) or any(key not in ENTRIES for key in ids):
        raise ValueError('Select one to four distinct supported capability identifiers')
    root = Path(__file__).parent
    versions = {name: core.sha(root / name) for name in sorted({x[1] for x in ENTRIES.values()} | {Path(__file__).name, 'design_loads.py', 'drawing_processing.py', 'drawing_scale.py'})}
    digest = core.hash_json({'entries': ENTRIES, 'source_versions': versions})
    rows = []
    for key in ids:
        title, module, supported, scope, next_step = ENTRIES[key]
        rows.append({'capability_id': key, 'title': title,
            'assessment': 'supported_with_limits' if supported else 'not_supported',
            'reason_code': 'implemented_bounded_method' if supported else 'outside_application_scope',
            'scope': scope, 'next_step': next_step, 'source_module': 'backend/' + module,
            'source_hash': versions[module], 'project_readiness': 'NOT_ASSESSED',
            'related_capabilities': [{'capability_id': k, 'title': ENTRIES[k][0]} for k in RELATED.get(key, [])],
            'notice': '这是应用功能范围说明；不是本项目资料充分性、运行就绪、工程合规或认证结论。'})
    return {'catalog_hash': digest, 'capabilities': rows}


class CapabilityMismatch(ValueError):
    def __init__(self, corrections):
        super().__init__('Capability assessment/reason disagrees with the current application scope')
        self.corrections = corrections


def read_count(explanation):
    return (len(explanation['claims']) + 3) // 4 if explanation else 0


def collect(ids, reader=None):
    """Combine bounded reads only when every batch belongs to the same catalog."""
    if not ids or len(ids) > len(ENTRIES) or len(set(ids)) != len(ids) or any(k not in ENTRIES for k in ids):
        raise ValueError('Select distinct declared capabilities')
    reader = reader or catalog
    digest, rows = None, []
    for offset in range(0, len(ids), 4):
        batch = ids[offset:offset + 4]
        result = reader(batch)
        if digest is not None and result['catalog_hash'] != digest:
            raise ValueError('Capability catalog changed between read batches')
        digest = result['catalog_hash']
        if [r['capability_id'] for r in result['capabilities']] != batch:
            raise ValueError('Incomplete or unexpected capability read batch')
        rows.extend(result['capabilities'])
    return {'catalog_hash': digest, 'capabilities': rows}


def check(explanation, current=None):
    current = current or collect([c.capability_id for c in explanation.claims])
    if current['catalog_hash'] != explanation.catalog_hash:
        raise ValueError('Capability catalog version changed; read current scope before explaining')
    rows = {r['capability_id']: r for r in current['capabilities']}
    corrections = []
    for claim in explanation.claims:
        row = rows.get(claim.capability_id)
        if not row or any(getattr(claim, k) != row[k] for k in ('assessment', 'reason_code')):
            corrections.append({'capability_id': claim.capability_id,
                'expected': {k:row[k] for k in ('assessment','reason_code')} if row else None})
    if corrections:raise CapabilityMismatch(corrections)
    return {'status': 'verified', 'reference': explanation.model_dump(mode='json'),
            'capability_assessments': [rows[c.capability_id] for c in explanation.claims]}


def attach(answer, explanation, reader=None):
    """Revalidate at final delivery and history access; never overwrite the saved task."""
    answer = {**answer, 'verification': list(answer.get('verification', [])), 'gaps': list(answer.get('gaps', []))}
    rows, valid = [], False
    try:
        request = Explanation.model_validate(explanation)
        current = collect([c.capability_id for c in request.claims], reader)
        rows = check(request, current)['capability_assessments'];valid = True
    except (ValueError, KeyError, OSError):
        answer['gaps'].append({'message':'能力说明版本已变化或无法核验', 'action':'重新查询当前应用能力；不复用旧说明'})
    answer['capability_assessments'] = rows
    answer['verification'].append({'check':'current_application_capability_scope', 'passed':valid,
                                  'meaning':'所列能力分类及理由与当前版本功能范围一致；不代表工程任务已完成'})
    if valid:
        answer['task_completion'] = 'partial'
        answer['execution_scope'] = 'checked_capabilities_and_professional_deliveries'
        answer['summary'] = '已核验所列应用能力边界；实际工程结果、输入充分性和整个问题覆盖度分别评估。'
        answer['gaps'] = [g for g in answer['gaps'] if g.get('message') != '本轮没有通过核验的专业交付']
    answer['can_recommend'] = False
    return answer
