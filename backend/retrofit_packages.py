"""Shared-scope procurement comparison. No inferred prices or additive energy savings."""
import math
from datetime import date
from typing import Literal

from fastapi import Body
from pydantic import Field, model_validator

from . import core
from .schema import Contract
from .sustainability import Declaration
from .epd import EpdReference

COSTS = {'material': '材料/设备', 'installation': '安装', 'demolition': '拆除清运',
         'access': '脚手/措施', 'disruption': '停用/搬迁'}
CHECKS = {'function': '同等功能与性能要求', 'fire': '防火适用性',
          'durability': '耐久与环境适用性', 'construction': '施工及现场适用性'}
CostKey = Literal['material', 'installation', 'demolition', 'access', 'disruption']
CheckKey = Literal['function', 'fire', 'durability', 'construction']


class Amount(Contract):
    total_cny: float | None = Field(default=None, ge=0, le=1e12, strict=True)
    evidence_id: str | None = None
    locator: str = Field(default='', max_length=1000)
    valid_until: date | None = None

    @model_validator(mode='after')
    def sourced(self):
        if self.total_cny is not None and (not self.evidence_id or len(self.locator) < 5):
            raise ValueError('费用含税总额（含0元）须关联依据及页码；未知费用留空')
        return self


class Scope(Contract):
    scope_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,40}$')
    name: str = Field(min_length=1, max_length=160)
    quantity: float = Field(gt=0, le=1e9, strict=True)
    unit: Literal['kg', 'm2', 'm3', 'item']
    requirements: str = Field(min_length=5, max_length=2000)
    evidence_id: str | None = None
    locator: str = Field(default='', max_length=1000)


class PackageItem(Contract):
    scope_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,40}$')
    product: str = Field(min_length=1, max_length=160)
    version: str = Field(min_length=1, max_length=100)
    costs: dict[CostKey, Amount] = Field(default_factory=dict, max_length=5)
    checks: dict[CheckKey, Declaration] = Field(default_factory=dict, max_length=4)
    annual_maintenance: Amount = Field(default_factory=Amount)
    service_life_years: int | None = Field(default=None, ge=1, le=100, strict=True)
    replacement: Amount = Field(default_factory=Amount)
    gwp_per_unit: float | None = Field(default=None, ge=-1e9, le=1e9, strict=True)
    gwp_unit: Literal['kg', 'm2', 'm3', 'item'] | None = None
    gwp_evidence_id: str | None = None
    gwp_locator: str = Field(default='', max_length=1000)
    epd_reference: EpdReference | None = None


class Package(Contract):
    package_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,40}$')
    name: str = Field(min_length=1, max_length=160)
    items: list[PackageItem] = Field(min_length=1, max_length=40)

    @model_validator(mode='after')
    def unique(self):
        if len({i.scope_id for i in self.items}) != len(self.items):
            raise ValueError('一个包内每个部位只能选择一个产品；替代产品请另建方案包')
        return self


class PackageComparison(Contract):
    name: str = Field(min_length=1, max_length=160)
    budget_cny: float = Field(ge=0, le=1e12, strict=True)
    horizon_years: int = Field(default=20, ge=1, le=100, strict=True)
    discount_rate: float = Field(default=0.0, ge=0, le=1, strict=True)
    carbon_boundary: Literal['A1-A3', 'A1-A5'] = 'A1-A3'
    scopes: list[Scope] = Field(min_length=1, max_length=40)
    packages: list[Package] = Field(min_length=1, max_length=12)

    @model_validator(mode='after')
    def coherent(self):
        ids = {s.scope_id for s in self.scopes}
        if len(ids) != len(self.scopes) or len({p.package_id for p in self.packages}) != len(self.packages):
            raise ValueError('部位ID及方案包ID须唯一')
        units = {s.scope_id: s.unit for s in self.scopes}
        for p in self.packages:
            for i in p.items:
                if i.scope_id not in ids:
                    raise ValueError('产品引用了不存在的工程部位')
                if i.gwp_per_unit is not None and (i.gwp_unit != units[i.scope_id] or not i.gwp_evidence_id or len(i.gwp_locator) < 5):
                    raise ValueError('材料GWP需与共同工程量单位一致、来源及定位完整；边界统一为本次比较声明值')
        return self


def evaluate(service, pid, body):
    service.store.get('project', pid)
    snapshots, rows = {}, []
    scopes = {s.scope_id: s for s in body.scopes}
    quantity_gaps = []
    for s in body.scopes:
        if not service.source(pid, s.evidence_id, snapshots) or len(s.locator) < 5:
            quantity_gaps.append(f'{s.name}：共同工程量/性能范围缺少复核来源或定位')

    def amount(value, label, gaps):
        sourced = service.source(pid, value.evidence_id, snapshots)
        if value.total_cny is None or not sourced:
            gaps.append(label + '：缺含税总额与来源（不适用也需有依据的0元）')
            return None
        if value.valid_until and value.valid_until < date.today():
            gaps.append(label + '：报价已过有效期')
            return None
        return value.total_cny

    for p in body.packages:
        gaps, cost_gaps, cash_gaps, carbon_gaps = list(quantity_gaps), [], [], []
        missing = set(scopes) - {i.scope_id for i in p.items}
        gaps += [scopes[s].name + '：包内缺少该部位产品' for s in sorted(missing)]
        details, cashflows = [], []
        for i in p.items:
            s = scopes[i.scope_id]
            prefix = s.name + ' / ' + i.product
            checks = []
            for key, label in CHECKS.items():
                d = i.checks.get(key, Declaration())
                sourced = service.source(pid, d.evidence_id, snapshots) and len(d.locator) >= 5
                state = 'FAIL' if d.satisfied is False else 'DECLARED_PASS' if d.satisfied is True and sourced else 'MISSING'
                checks.append({'key': key, 'label': label, 'state': state})
                if state != 'DECLARED_PASS':
                    gaps.append(prefix + '：' + label + ('不满足' if state == 'FAIL' else '待补证'))
            costs = {key: amount(i.costs.get(key, Amount()), prefix + ' / ' + label, cost_gaps) for key, label in COSTS.items()}
            initial = math.fsum(costs.values()) if all(v is not None for v in costs.values()) else None
            maintenance = amount(i.annual_maintenance, prefix + ' / 年维护', cash_gaps)
            years = list(range(i.service_life_years, body.horizon_years, i.service_life_years)) if i.service_life_years else None
            replacement = amount(i.replacement, prefix + ' / 每次完整更换', cash_gaps) if years else None
            if years is None:
                cash_gaps.append(prefix + '：寿命未知，无法确定更换时点')
            if initial is not None:
                cashflows.append({'year': 0, 'scope_id': s.scope_id, 'category': 'initial', 'cny': initial})
            if maintenance is not None:
                cashflows += [{'year': y, 'scope_id': s.scope_id, 'category': 'maintenance', 'cny': maintenance} for y in range(1, body.horizon_years + 1)]
            if replacement is not None:
                cashflows += [{'year': y, 'scope_id': s.scope_id, 'category': 'replacement', 'cny': replacement} for y in years]
            carbon_source = service.source(pid, i.gwp_evidence_id, snapshots)
            epd_result = None
            factor = i.gwp_per_unit
            if i.epd_reference:
                epd_result = service.epds.calculate(i.epd_reference, s.quantity, s.unit, body.carbon_boundary)
                factor = epd_result['gwp_per_unit']
                carbon_gaps += [prefix + '：' + gap for gap in epd_result['gaps']]
                if i.gwp_per_unit is not None and (factor is None or not math.isclose(i.gwp_per_unit, factor, rel_tol=1e-10, abs_tol=1e-10)):
                    raise core.ValidationError('手填材料碳因子与所绑定EPD原件不一致，请重新选择声明')
            carbon = s.quantity * factor if factor is not None and carbon_source and len(i.gwp_locator) >= 5 else None
            if carbon is None:
                carbon_gaps.append(prefix + '：材料碳因子或本工程适用性复核来源/定位不完整')
            details.append({'scope_id': s.scope_id, 'product': i.product, 'version': i.version,
                            'quantity': s.quantity, 'unit': s.unit, 'costs_cny': costs, 'initial_cost_cny': initial,
                            'checks': checks, 'initial_material_kgco2e': carbon, 'replacement_years': years,
                            'epd_calculation': epd_result})
        complete_scope = not missing and not quantity_gaps
        initial = math.fsum(d['initial_cost_cny'] for d in details) if complete_scope and not cost_gaps else None
        carbon = math.fsum(d['initial_material_kgco2e'] for d in details) if complete_scope and not carbon_gaps else None
        discounted = math.fsum(f['cny'] / (1 + body.discount_rate) ** f['year'] for f in cashflows) if initial is not None and not cash_gaps else None
        within = initial <= body.budget_cny if initial is not None else None
        rows.append({'package_id': p.package_id, 'name': p.name, 'items': details,
                     'initial_cost_cny': initial, 'within_budget': within, 'initial_material_kgco2e': carbon,
                     'discounted_declared_outlay_cny': discounted, 'cashflows': cashflows,
                     'engineering_gaps': gaps, 'cost_gaps': cost_gaps, 'cashflow_gaps': cash_gaps, 'carbon_gaps': carbon_gaps,
                     'carbon_state': 'NEEDS_EVIDENCE' if carbon_gaps else 'DECLARED_BOUNDARY_CALCULATED',
                     'state': 'NEEDS_EVIDENCE' if gaps or initial is None else 'OVER_BUDGET' if not within else 'READY_FOR_ENGINEER_REVIEW'})
    return {'name': body.name, 'scope_count': len(scopes), 'rows': rows, 'carbon_boundary': body.carbon_boundary,
            'horizon_years': body.horizon_years, 'discount_rate': body.discount_rate,
            'comparison_basis': '共同工程量及功能要求下比较整包；每包每部位仅选一个产品；费用为覆盖该部位全部工程量的含税总额。',
            'limitations': ['适用性为工程师声明及来源绑定，未自动验证检测报告条文；待专业复核，不自动选出获胜方案。',
                            '折现支出仅含已填初始、年维护及更换费用；年末维护、更换发生在寿命整数倍且小于比较年限；无残值、融资、能源费或收入，不是完整投资净现值。',
                            '材料碳仅初次采购的统一声明阶段；不含更换、运行和未声明阶段，不是完整LCA。',
                            '未将独立材料仿真相加为联合节能，也未将减排换算成可售碳信用。'],
            'issued_credits_t': None, 'credit_revenue_in_base_case': False}, snapshots


def register_packages(app, service):
    @app.post('/api/projects/{project_id}/sustainability/packages/preview')
    def preview(project_id: str, body: PackageComparison):
        result, _ = evaluate(service, project_id, body)
        return {**result, 'draft': body.model_dump(mode='json')}

    @app.post('/api/projects/{project_id}/sustainability/packages', status_code=201)
    def save(project_id: str, body: PackageComparison):
        result, snapshots = evaluate(service, project_id, body)
        return service.save(project_id, 'package', body, result, snapshots)

    @app.post('/api/projects/{project_id}/sustainability/package-quantities')
    def quantities(project_id: str, content: str = Body(media_type='text/plain', max_length=200000)):
        """Excel CSV intake is a draft; existing source IDs must still be reviewed."""
        import csv
        import io
        service.store.get('project', project_id)
        try:
            reader = csv.DictReader(io.StringIO(content.lstrip('\ufeff')), strict=True)
            columns = {'scope_id', 'name', 'quantity', 'unit', 'requirements', 'evidence_id', 'locator'}
            if not reader.fieldnames or len(reader.fieldnames) != len(columns) or set(reader.fieldnames) != columns:
                raise ValueError('CSV列须为 scope_id,name,quantity,unit,requirements,evidence_id,locator')
            scopes = []
            for line, row in enumerate(reader, 2):
                if line > 41:
                    raise ValueError('一次最多40个工程部位')
                if None in row or any(v is None for v in row.values()):
                    raise ValueError(f'第{line}行列数不正确')
                scopes.append(Scope.model_validate({**row, 'quantity': float(row['quantity']), 'evidence_id': row['evidence_id'] or None}))
            if not scopes or len({s.scope_id for s in scopes}) != len(scopes):
                raise ValueError('工程量不能为空，部位ID不得重复')
        except (ValueError, csv.Error) as exc:
            raise core.ValidationError('工程量CSV导入失败：' + str(exc)) from exc
        return {'scopes': [s.model_dump() for s in scopes], 'state': 'DRAFT_REQUIRES_REVIEW'}
