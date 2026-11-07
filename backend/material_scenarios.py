"""IFC-bound material alternatives using existing cost and carbon calculators."""
import html
import json
from datetime import date
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Literal

from fastapi.responses import HTMLResponse
from pydantic import Field, StrictFloat, StrictInt, ValidationError as SchemaError, field_validator, model_validator

from . import core, lifecycle, material_cost
from .calculation_provenance import persist, validity
from .domain import identifier
from .schema import Contract


class LayerExclusion(Contract):
    layer_id: StrictInt = Field(gt=0)
    reason: str = Field(min_length=5, max_length=1000)


class LayerMaterial(Contract):
    layer_id: StrictInt = Field(gt=0)
    material_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    solid_fraction: StrictFloat | None = Field(default=None, gt=0, le=1)
    fraction_source: str = Field(min_length=5, max_length=2000)
    waste_ratio: StrictFloat | None = Field(default=None, ge=0, le=1)
    waste_basis: str = Field(min_length=5, max_length=1000)
    density_kg_m3: StrictFloat | None = Field(default=None, gt=0, le=100000)
    density_source: str | None = Field(default=None, min_length=5, max_length=2000)
    quote: material_cost.Quote
    factor: lifecycle.EmissionFactor
    evidence_ids: list[str] = Field(default_factory=list, max_length=30)

    @model_validator(mode='after')
    def units(self):
        if self.quote.per_unit not in {'kg', 't', 'm3'}:
            raise ValueError('Layer volume requires a volume or mass quote')
        if self.factor.stage != 'production' or self.factor.denominator not in {'kg', 't', 'm3'}:
            raise ValueError('Mapped layers require production factors per mass or volume')
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError('Duplicate mapping evidence')
        if (self.density_kg_m3 is None) != (self.density_source is None):
            raise ValueError('Density and its source must be provided together')
        return self


class Alternative(Contract):
    name: str = Field(min_length=1, max_length=160)
    layers: list[LayerMaterial] = Field(min_length=1, max_length=32)
    other_activities: list[lifecycle.Activity] = Field(default_factory=list, max_length=300)

    @model_validator(mode='after')
    def unique(self):
        if len({r.layer_id for r in self.layers}) != len(self.layers):
            raise ValueError('Duplicate material layer; double counting rejected')
        if any(a.stage == 'production' for a in self.other_activities):
            raise ValueError('Production is derived from mapped layers, not extra manual activities')
        return self


class ScenarioRequest(Contract):
    takeoff_id: str = Field(pattern=r'^takeoff_[a-f0-9]{32}$')
    functional_scope: str = Field(min_length=10, max_length=1000)
    region: str = Field(min_length=1, max_length=100)
    currency: Literal['CNY', 'USD', 'EUR']
    tax_basis: Literal['included', 'excluded']
    as_of: date
    exclusions: list[str] = Field(min_length=1, max_length=30)
    excluded_layers: list[LayerExclusion] = Field(default_factory=list, max_length=31)
    study_years: StrictInt = Field(gt=0, le=200)
    method: str = Field(min_length=3, max_length=300)
    boundaries: list[lifecycle.Boundary] = Field(min_length=5, max_length=5)
    alternatives: list[Alternative] = Field(min_length=2, max_length=2)

    @field_validator('as_of', mode='before')
    @classmethod
    def explicit_date(cls, value):
        return material_cost.Quote.explicit_dates(value)

    @model_validator(mode='after')
    def coherent(self):
        if self.alternatives[0].name == self.alternatives[1].name:
            raise ValueError('Distinct alternative names required')
        if len({r.layer_id for r in self.excluded_layers}) != len(self.excluded_layers):
            raise ValueError('Duplicate excluded layer')
        if {b.stage for b in self.boundaries} != lifecycle.STAGES:
            raise ValueError('Declare each of the five carbon stages exactly once')
        if not any(b.stage == 'production' and b.included for b in self.boundaries):
            raise ValueError('Material alternatives must include production')
        factors, quotes = {}, {}
        for alt in self.alternatives:
            for factor in [r.factor for r in alt.layers] + [a.factor for a in alt.other_activities]:
                data = factor.model_dump(mode='json')
                if factor.factor_id in factors and factors[factor.factor_id] != data:
                    raise ValueError('Same factor ID has conflicting source/value/version across alternatives')
                factors[factor.factor_id] = data
            for row in alt.layers:
                q = row.quote.model_dump(mode='json')
                if row.quote.quote_id in quotes and quotes[row.quote.quote_id] != q:
                    raise ValueError('Same quote ID conflicts across alternatives')
                quotes[row.quote.quote_id] = q
        return self


def calculator_version():
    return core.hash_json({name: core.sha(Path(__file__).with_name(name)) for name in
        ['material_scenarios.py', 'material_cost.py', 'lifecycle.py', 'schema.py', 'calculation_provenance.py']})


def calculate(body, takeoff, project):
    source = {r['layer_id']: r for r in takeoff['result']['layers']}
    excluded = {r.layer_id for r in body.excluded_layers}
    if not excluded <= source.keys():
        raise core.ValidationError('Excluded layer does not exist in source')
    results = []
    with localcontext() as ctx:
        ctx.prec = 80
        for alternative in body.alternatives:
            if {r.layer_id for r in alternative.layers} != source.keys() - excluded:
                raise core.ValidationError('Each non-excluded source layer must be mapped exactly once in both alternatives')
            costs, activities, derivations = [], list(alternative.other_activities), []
            for mapping in alternative.layers:
                row = source[mapping.layer_id]
                envelope = Decimal(str(row['envelope_volume_m3']))
                net = None if mapping.solid_fraction is None else envelope * Decimal(str(mapping.solid_fraction))
                purchase = None if net is None or mapping.waste_ratio is None else net * (1 + Decimal(str(mapping.waste_ratio)))
                key = 'layer_' + str(mapping.layer_id)
                locator = f"{takeoff['takeoff_id']} / IFC #{takeoff['product_id']} / layer #{mapping.layer_id} / {takeoff['hash']}"
                mass_quote = mapping.quote.per_unit != 'm3'
                costs.append(material_cost.MaterialLine(line_id=key, material_id=mapping.material_id, name=mapping.name,
                    measure=material_cost.Measure(mode='direct', unit='m3', quantity=None if net is None else float(net), source=locator),
                    waste_ratio=mapping.waste_ratio, waste_basis=mapping.waste_basis,
                    density_kg_m3=mapping.density_kg_m3 if mass_quote else None,
                    density_source=mapping.density_source if mass_quote else None, quote=mapping.quote))
                carbon_quantity = purchase
                if mapping.factor.denominator in {'kg', 't'}:
                    carbon_quantity = None if purchase is None or mapping.density_kg_m3 is None else purchase * Decimal(str(mapping.density_kg_m3))
                    if carbon_quantity is not None and mapping.factor.denominator == 't':
                        carbon_quantity /= Decimal(1000)
                activities.append(lifecycle.Activity(activity_id=key, name=mapping.name, stage='production',
                    quantity=None if carbon_quantity is None else float(carbon_quantity), unit=mapping.factor.denominator,
                    period='whole_period', source=locator, factor=mapping.factor))
                derivations.append({'layer_id':mapping.layer_id, 'source_material_id':row['material_id'],
                    'source_material_name':row['material_name'], 'proposed_material_id':mapping.material_id,
                    'envelope_volume_m3':str(envelope), 'solid_fraction':mapping.solid_fraction,
                    'net_material_volume_m3':None if net is None else str(net),
                    'purchase_volume_m3':None if purchase is None else str(purchase),
                    'production_quantity':None if carbon_quantity is None else str(carbon_quantity),
                    'production_unit':mapping.factor.denominator, 'source_locator':locator,
                    'formula':'envelope * declared solid_fraction; purchase = net * (1+waste); mass = purchase * density',
                    'source_status':'MODEL_GEOMETRY_WITH_USER_DECLARED_MAPPING'})
            cost_input = material_cost.Estimate(name=alternative.name, region=body.region, currency=body.currency,
                tax_basis=body.tax_basis, as_of=body.as_of, functional_scope=body.functional_scope,
                exclusions=body.exclusions, lines=costs)
            carbon_input = lifecycle.Inventory(name=alternative.name, region=body.region,
                area_m2=project['building']['area_m2'], study_years=body.study_years, method=body.method,
                functional_unit=body.functional_scope, boundaries=body.boundaries, activities=activities)
            cost, carbon = material_cost.calculate(cost_input), lifecycle.calculate(carbon_input)
            results.append({'name':alternative.name, 'derivations':derivations, 'cost':cost, 'carbon':carbon,
                'cost_input':cost_input.model_dump(mode='json'), 'carbon_input':carbon_input.model_dump(mode='json')})
        complete = all(r['cost']['status'] == r['carbon']['status'] == 'calculated' for r in results)
        comparison = None
        if complete:
            a, b = results
            base_cost, alt_cost = Decimal(a['cost']['material_total']), Decimal(b['cost']['material_total'])
            base_carbon = Decimal(str(a['carbon']['boundary_total_kgco2e']))
            alt_carbon = Decimal(str(b['carbon']['boundary_total_kgco2e']))
            comparison = {'baseline':a['name'], 'alternative':b['name'],
                'cost_difference':str(alt_cost-base_cost), 'currency':body.currency,
                'carbon_reduction_kgco2e':str(base_carbon-alt_carbon),
                'cost_reduction_pct':None if base_cost == 0 else str((base_cost-alt_cost)/base_cost*100),
                'carbon_reduction_pct':None if base_carbon == 0 else str((base_carbon-alt_carbon)/base_carbon*100)}
    return {'status':'calculated' if complete else 'incomplete', 'alternatives':results, 'comparison':comparison,
        'functional_equivalence':'NOT_ASSESSED', 'certification':'NOT_ASSESSED', 'issued_credits_t':None,
        'limitations':['限定同一构件及相同声明边界；材料功能等效、耐火、结构和节能效果未验证。',
            '层包络乘显式实体比例得到条件材料量；比例、密度、损耗、价格和因子来源仍需专业复核。',
            '生产碳按含损耗采购量计；其他阶段仅使用明确录入的活动，不自动补齐全生命周期。',
            '单位面积分母来自项目建筑面积，不是所选墙面积；材料成本不等于工程总造价。']}


class MaterialScenarios:
    def __init__(self, takeoffs):
        self.takeoffs, self.domain, self.store = takeoffs, takeoffs.domain, takeoffs.store

    def create(self, pid, body):
        takeoff = self.takeoffs.view(pid, body.takeoff_id)
        if takeoff['status'] != 'measured':
            raise core.ValidationError('A current measured layer takeoff is required')
        project = self.store.get('project', pid)
        if project['building']['region'] != body.region:
            raise core.ValidationError('Scenario region must match current project')
        version = calculator_version()
        evidence_ids = set()
        for alt in body.alternatives:
            for row in alt.layers:
                evidence_ids.update(row.evidence_ids)
                if row.factor.evidence_id: evidence_ids.add(row.factor.evidence_id)
            evidence_ids.update(a.factor.evidence_id for a in alt.other_activities if a.factor.evidence_id)
        evidence = []
        for eid in sorted(evidence_ids):
            ev = self.store.get('evidence', eid)
            if ev['project_id'] != pid or ev['review_state'] == 'rejected':
                raise core.ValidationError('Foreign or rejected scenario evidence')
            evidence.append(ev)
        file_record, _ = self.domain.file_record(pid, takeoff['source']['file_id'])
        try:
            result = calculate(body, takeoff, project)
        except SchemaError as error:
            raise core.ValidationError("Inconsistent scenario inputs: " + "; ".join(e["msg"] for e in error.errors())[:1000]) from error
        current = self.takeoffs.view(pid, body.takeoff_id)
        if current['status'] != 'measured' or current['hash'] != takeoff['hash'] or version != calculator_version():
            raise core.ValidationError('Scenario source changed during calculation')
        record = {'scenario_id':identifier('scenario'), 'project_id':pid, 'project_revision':project['revision'],
            'takeoff_id':body.takeoff_id, 'takeoff_hash':takeoff['hash'], 'calculator_hash':version,
            'input':body.model_dump(mode='json'), 'result':result, 'source_snapshot':evidence,
            'import_source':file_record, 'created_at':core.now()}
        record['hash'] = core.hash_json(record)
        persist(self.domain, 'scenario', record)
        return self.view(pid, record['scenario_id'])

    def view(self, pid, ident):
        record = self.store.get('scenario', ident)
        if record['project_id'] != pid:
            raise core.ValidationError('Cross-project material scenario rejected')
        if core.hash_json({k:v for k,v in record.items() if k not in {'hash','revision'}}) != record['hash']:
            raise core.ValidationError('Material scenario integrity failed')
        provenance = validity(self.domain, record, calculator_version())
        reasons = provenance['stale_reasons']
        try:
            takeoff = self.takeoffs.view(pid, record['takeoff_id'])
            if takeoff['status'] != 'measured' or takeoff['hash'] != record['takeoff_hash']:
                reasons.append('layer_takeoff_changed')
        except (KeyError, OSError, ValueError):
            reasons.append('layer_takeoff_unavailable')
        return {**record, **provenance, 'status':'stale' if reasons else record['result']['status'],
            'result':None if reasons else record['result']}


def report(record):
    esc = lambda value: html.escape(str(value))
    display = lambda value: '缺数据' if value is None else format(Decimal(str(value)), '.8g')
    state = {'calculated':'已计算','incomplete':'资料不完整','stale':'来源已失效'}.get(record['status'],record['status'])
    result = record['result']
    content = '<p>来源或计算规则已变化，当前结果不可用。请重新核验并建立方案。</p>'
    if result:
        rows = ''.join('<tr>' + ''.join('<td>' + esc(v if v is not None else '缺数据') + '</td>' for v in
            [r['name'], r['cost']['material_total'], display(r['carbon']['boundary_total_kgco2e'])]) + '</tr>' for r in result['alternatives'])
        content = '<div class="table-scroll" tabindex="0" role="region" aria-label="两方案汇总表"><table><tr><th>方案</th><th>材料费用 '+esc(record['input']['currency'])+'</th><th>声明边界碳 kgCO₂e</th></tr>'+rows+'</table></div>'
        if result['comparison']:
            c = result['comparison']
            content += '<p>方案二相对方案一费用变化：'+esc(c['cost_difference'])+' '+esc(c['currency'])+'；碳减少：'+esc(display(c['carbon_reduction_kgco2e']))+' kgCO₂e。</p>'
        content += '<ul>'+''.join('<li>'+esc(s)+'</li>' for s in result['limitations'])+'</ul>'
        for alternative, declared in zip(result['alternatives'], record['input']['alternatives']):
            content += '<h2>'+esc(alternative['name'])+' · 逐层数量与依据</h2>'
            content += '<div class="table-scroll" tabindex="0" role="region" aria-label="逐层计量表"><table><tr><th>来源层 / 拟用材料</th><th>包络 m³</th><th>实体材料 m³</th><th>含损耗采购 m³</th><th>材料金额</th><th>生产碳 kgCO₂e</th></tr>'
            for row, cost, carbon, mapping in zip(alternative['derivations'], alternative['cost']['rows'],
                    alternative['carbon']['rows'][-len(alternative['derivations']):], declared['layers']):
                values = ['#'+str(row['layer_id'])+' '+(row['source_material_name'] or '未命名材料')+' → '+mapping['name'],
                    display(row['envelope_volume_m3']),display(row['net_material_volume_m3']),display(row['purchase_volume_m3']),cost['amount'],display(carbon['kgco2e'])]
                content += '<tr>'+''.join('<td>'+esc(v if v is not None else '缺数据')+'</td>' for v in values)+'</tr>'
            content += '</table></div><details><summary>查看实体比例、损耗、价格和因子依据</summary><ul>'
            for mapping in declared['layers']:
                content += '<li>'+esc(mapping['name'])+'：实体比例 '+esc(mapping['solid_fraction'])+'（'+esc(mapping['fraction_source'])+'）；损耗 '+esc(mapping['waste_ratio'])+'（'+esc(mapping['waste_basis'])+'）；报价 '+esc(mapping['quote']['source'])+' / '+esc(mapping['quote']['version'])+'；因子 '+esc(mapping['factor']['source'])+' / '+esc(mapping['factor']['version'])+'</li>'
            content += '</ul></details>'

    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>材料方案比较</title><style>body{font:16px/1.7 system-ui;max-width:1000px;margin:30px auto;padding:20px}body{overflow-wrap:anywhere;box-sizing:border-box}.table-scroll{max-width:100%;overflow-x:auto}table{border-collapse:collapse;width:100%;min-width:480px}td,th{border:1px solid #ccd6d4;padding:10px;text-align:left}td:not(:first-child){white-space:nowrap;overflow-wrap:normal}td:first-child,th:first-child{min-width:180px;max-width:260px;white-space:normal}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style><h1>材料方案比较</h1><p>状态：'+esc(state)+' · 功能等效性未核验，非总造价或碳资产认证。</p><p>表格数值按8位有效数字展示；金额保留分，原始精度见计算回执。窄屏可在表格内横向滚动。</p>'+content+'<details><summary>输入、逐层公式及来源回执</summary><pre>'+esc(json.dumps(record,ensure_ascii=False,indent=2))+'</pre></details></html>'


def register(app, takeoffs):
    service = MaterialScenarios(takeoffs)
    app.state.material_scenarios = service

    @app.post('/api/projects/{project_id}/material-scenarios', status_code=201)
    def create(project_id: str, body: ScenarioRequest):
        return service.create(project_id, body)

    @app.get('/api/projects/{project_id}/material-scenarios')
    def history(project_id: str):
        return [{'scenario_id':r['scenario_id'], 'created_at':r['created_at'],
                 'names':[a['name'] for a in r['input']['alternatives']]} for r in service.store.list('scenario', project_id)]

    @app.get('/api/projects/{project_id}/material-scenarios/{scenario_id}')
    def current(project_id: str, scenario_id: str):
        return service.view(project_id, scenario_id)

    @app.get('/api/projects/{project_id}/material-scenarios/{scenario_id}/report.html', response_class=HTMLResponse)
    def html_report(project_id: str, scenario_id: str):
        return report(service.view(project_id, scenario_id))
