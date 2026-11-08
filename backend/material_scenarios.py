"""IFC-bound material alternatives using existing cost and carbon calculators."""
import html
import json
from datetime import date
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Literal

from fastapi.responses import HTMLResponse
from pydantic import Field, StrictFloat, StrictInt, ValidationError as SchemaError, field_validator, model_validator

from . import core, lifecycle, material_cost, material_transport
from .calculation_provenance import persist, validity
from .domain import identifier
from .schema import Contract


class LayerExclusion(Contract):
    layer_id: StrictInt = Field(gt=0)
    reason: str = Field(min_length=5, max_length=1000)


class MaterialMapping(Contract):
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


class LayerMaterial(MaterialMapping):
    layer_id: StrictInt = Field(gt=0)


class ScenarioActivity(lifecycle.Activity):
    source_evidence_ids: list[str] = Field(default_factory=list, max_length=30)

    @model_validator(mode='after')
    def unique_source_evidence(self):
        if len(set(self.source_evidence_ids)) != len(self.source_evidence_ids):
            raise ValueError('Duplicate activity source evidence')
        return self


class Alternative(Contract):
    name: str = Field(min_length=1, max_length=160)
    layers: list[LayerMaterial] = Field(min_length=1, max_length=32)
    other_activities: list[ScenarioActivity] = Field(default_factory=list, max_length=300)
    transport_legs: list[material_transport.TransportLeg] = Field(default_factory=list, max_length=30)

    @model_validator(mode='after')
    def unique(self):
        if len({r.layer_id for r in self.layers}) != len(self.layers):
            raise ValueError('Duplicate material layer; double counting rejected')
        if len({leg.leg_id for leg in self.transport_legs}) != len(self.transport_legs):
            raise ValueError('Duplicate transport leg ID')
        if any(a.stage == 'production' for a in self.other_activities):
            raise ValueError('Production is derived from mapped layers, not extra manual activities')
        return self


class ScenarioContext(Contract):
    functional_scope: str = Field(min_length=10, max_length=1000)
    region: str = Field(min_length=1, max_length=100)
    currency: Literal['CNY', 'USD', 'EUR']
    tax_basis: Literal['included', 'excluded']
    as_of: date
    exclusions: list[str] = Field(min_length=1, max_length=30)
    study_years: StrictInt = Field(gt=0, le=200)
    method: str = Field(min_length=3, max_length=300)
    boundaries: list[lifecycle.Boundary] = Field(min_length=5, max_length=5)

    @field_validator('as_of', mode='before')
    @classmethod
    def explicit_date(cls, value):
        return material_cost.Quote.explicit_dates(value)


def validate_scenario(body, mappings_field, identity_field, excluded_field):
    if body.alternatives[0].name == body.alternatives[1].name:
        raise ValueError('Distinct alternative names required')
    if len({getattr(r, identity_field) for r in getattr(body, excluded_field)}) != len(getattr(body, excluded_field)):
        raise ValueError('Duplicate excluded layer')
    if {b.stage for b in body.boundaries} != lifecycle.STAGES:
        raise ValueError('Declare each of the five carbon stages exactly once')
    if not any(b.stage == 'production' and b.included for b in body.boundaries):
        raise ValueError('Material alternatives must include production')
    factors, quotes = {}, {}
    for alt in body.alternatives:
        for factor in [r.factor for r in getattr(alt, mappings_field)] + [a.factor for a in alt.other_activities] + [leg.factor for leg in alt.transport_legs]:
            data = factor.model_dump(mode='json')
            if factor.factor_id in factors and factors[factor.factor_id] != data:
                raise ValueError('Same factor ID has conflicting source/value/version across alternatives')
            factors[factor.factor_id] = data
        for row in getattr(alt, mappings_field):
            q = row.quote.model_dump(mode='json')
            if row.quote.quote_id in quotes and quotes[row.quote.quote_id] != q:
                raise ValueError('Same quote ID conflicts across alternatives')
            quotes[row.quote.quote_id] = q
    return body


class ScenarioRequest(ScenarioContext):
    takeoff_id: str = Field(pattern=r'^takeoff_[a-f0-9]{32}$')
    excluded_layers: list[LayerExclusion] = Field(default_factory=list, max_length=31)
    alternatives: list[Alternative] = Field(min_length=2, max_length=2)

    @model_validator(mode='after')
    def coherent(self):
        return validate_scenario(self, 'layers', 'layer_id', 'excluded_layers')


def calculator_version():
    return core.hash_json({name: core.sha(Path(__file__).with_name(name)) for name in
        ['material_scenarios.py', 'collection_scenarios.py', 'material_transport.py', 'material_cost.py', 'lifecycle.py', 'schema.py', 'calculation_provenance.py']})


def calculate(body, takeoff, project, *, source_kind='layer'):
    if source_kind not in {'layer', 'collection'}:
        raise ValueError('Unknown scenario source kind')
    collection = source_kind == 'collection'
    identity_field = 'source_material_id' if collection else 'layer_id'
    mappings_field = 'materials' if collection else 'layers'
    record_id_field = 'materialset_id' if collection else 'takeoff_id'
    source_key = 'material_id' if collection else 'layer_id'
    volume_key = 'union_envelope_m3' if collection else 'envelope_volume_m3'
    prefix = 'material_' if collection else 'layer_'
    source = {r[source_key]: r for r in takeoff['result'][mappings_field]}
    excluded = {getattr(r, identity_field) for r in getattr(body, 'excluded_materials' if collection else 'excluded_layers')}
    if not excluded <= source.keys():
        raise core.ValidationError('Excluded layer does not exist in source')
    results = []
    with localcontext() as ctx:
        ctx.prec = 80
        for alternative in body.alternatives:
            if {getattr(r, identity_field) for r in getattr(alternative, mappings_field)} != source.keys() - excluded:
                raise core.ValidationError('Each non-excluded source layer must be mapped exactly once in both alternatives')
            costs, activities, derivations = [], list(alternative.other_activities), []
            for mapping in getattr(alternative, mappings_field):
                row = source[getattr(mapping, identity_field)]
                envelope = Decimal(str(row[volume_key]))
                net = None if mapping.solid_fraction is None else envelope * Decimal(str(mapping.solid_fraction))
                purchase = None if net is None or mapping.waste_ratio is None else net * (1 + Decimal(str(mapping.waste_ratio)))
                key = prefix + str(getattr(mapping, identity_field))
                locator = (f"{takeoff['materialset_id']} / selected IFC {takeoff['product_ids']} / material #{getattr(mapping, identity_field)} / {takeoff['hash']}"
                           if collection else f"{takeoff['takeoff_id']} / IFC #{takeoff['product_id']} / layer #{getattr(mapping, identity_field)} / {takeoff['hash']}")
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
                derivations.append({identity_field:getattr(mapping, identity_field), 'source_material_id':row['material_id'],
                    'source_material_name':row['material_name'], 'proposed_material_id':mapping.material_id,
                    'envelope_volume_m3':str(envelope), 'solid_fraction':mapping.solid_fraction,
                    'net_material_volume_m3':None if net is None else str(net),
                    'purchase_volume_m3':None if purchase is None else str(purchase),
                    'production_quantity':None if carbon_quantity is None else str(carbon_quantity),
                    'production_unit':mapping.factor.denominator, 'source_locator':locator,
                    'formula':'envelope * declared solid_fraction; purchase = net * (1+waste); mass = purchase * density',
                    'source_status':'MODEL_GEOMETRY_WITH_USER_DECLARED_MAPPING'})
            transport_activities, transport_receipts = material_transport.derive(alternative.transport_legs, getattr(alternative, mappings_field), derivations, takeoff,
                identity_field=identity_field, selection_field='material_ids' if collection else 'layer_ids',
                parts_field=mappings_field, record_id_field=record_id_field)
            activities.extend(transport_activities)
            cost_input = material_cost.Estimate(name=alternative.name, region=body.region, currency=body.currency,
                tax_basis=body.tax_basis, as_of=body.as_of, functional_scope=body.functional_scope,
                exclusions=body.exclusions, lines=costs)
            carbon_input = lifecycle.Inventory(name=alternative.name, region=body.region,
                area_m2=project['building']['area_m2'], study_years=body.study_years, method=body.method,
                functional_unit=body.functional_scope, boundaries=body.boundaries, activities=activities)
            cost, carbon = material_cost.calculate(cost_input), lifecycle.calculate(carbon_input)
            results.append({'name':alternative.name, 'derivations':derivations, 'transport':transport_receipts, 'cost':cost, 'carbon':carbon,
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
        'limitations':[('限定所选多墙去重材料包络及相同声明边界；材料功能等效、耐火、结构和节能效果未验证。' if collection else '限定同一构件及相同声明边界；材料功能等效、耐火、结构和节能效果未验证。'),
            '层包络乘显式实体比例得到条件材料量；比例、密度、损耗、价格和因子来源仍需专业复核。',
            '生产碳按含损耗采购量计；材料运输由采购质量、分批比例、附加质量和距离派生，其他活动须显式录入。阶段齐全不证明清单无遗漏或符合LCA标准。',
            '单位面积分母来自项目建筑面积，不是所选墙面积；材料成本不等于工程总造价。']}


class MaterialScenarios:
    source_kind = 'layer'
    source_id_field = 'takeoff_id'
    source_hash_field = 'takeoff_hash'
    record_kind = 'scenario'
    mappings_field = 'layers'

    def __init__(self, takeoffs):
        self.takeoffs, self.domain, self.store = takeoffs, takeoffs.domain, takeoffs.store

    def create(self, pid, body):
        takeoff = self.takeoffs.view(pid, getattr(body, self.source_id_field))
        if takeoff['status'] != 'measured':
            raise core.ValidationError('A current measured layer takeoff is required')
        project = self.store.get('project', pid)
        if project['building']['region'] != body.region:
            raise core.ValidationError('Scenario region must match current project')
        version = calculator_version()
        evidence_ids = set()
        for alt in body.alternatives:
            for row in getattr(alt, self.mappings_field):
                evidence_ids.update(row.evidence_ids)
                if row.factor.evidence_id: evidence_ids.add(row.factor.evidence_id)
            evidence_ids.update(a.factor.evidence_id for a in alt.other_activities if a.factor.evidence_id)
            evidence_ids.update(leg.factor.evidence_id for leg in alt.transport_legs if leg.factor.evidence_id)
            for activity in alt.other_activities:evidence_ids.update(activity.source_evidence_ids)
            for leg in alt.transport_legs:evidence_ids.update(leg.evidence_ids)
        evidence = []
        for eid in sorted(evidence_ids):
            ev = self.store.get('evidence', eid)
            if ev['project_id'] != pid or ev['review_state'] == 'rejected':
                raise core.ValidationError('Foreign or rejected scenario evidence')
            evidence.append(ev)
        file_record, _ = self.domain.file_record(pid, takeoff['source']['file_id'])
        try:
            result = calculate(body, takeoff, project, source_kind=self.source_kind)
        except SchemaError as error:
            raise core.ValidationError("Inconsistent scenario inputs: " + "; ".join(e["msg"] for e in error.errors())[:1000]) from error
        current = self.takeoffs.view(pid, getattr(body, self.source_id_field))
        if current['status'] != 'measured' or current['hash'] != takeoff['hash'] or version != calculator_version():
            raise core.ValidationError('Scenario source changed during calculation')
        record = {self.record_kind+'_id':identifier(self.record_kind), 'project_id':pid, 'project_revision':project['revision'],
            self.source_id_field:getattr(body, self.source_id_field), self.source_hash_field:takeoff['hash'], 'calculator_hash':version,
            'input':body.model_dump(mode='json'), 'result':result, 'source_snapshot':evidence,
            'import_source':file_record, 'created_at':core.now()}
        record['hash'] = core.hash_json(record)
        persist(self.domain, self.record_kind, record)
        return self.view(pid, record[self.record_kind+'_id'])

    def view(self, pid, ident):
        record = self.store.get(self.record_kind, ident)
        if record['project_id'] != pid:
            raise core.ValidationError('Cross-project material scenario rejected')
        if core.hash_json({k:v for k,v in record.items() if k not in {'hash','revision'}}) != record['hash']:
            raise core.ValidationError('Material scenario integrity failed')
        provenance = validity(self.domain, record, calculator_version())
        reasons = provenance['stale_reasons']
        try:
            takeoff = self.takeoffs.view(pid, record[self.source_id_field])
            if takeoff['status'] != 'measured' or takeoff['hash'] != record[self.source_hash_field]:
                reasons.append('material_collection_changed' if self.source_kind == 'collection' else 'layer_takeoff_changed')
        except (KeyError, OSError, ValueError):
            reasons.append('material_collection_unavailable' if self.source_kind == 'collection' else 'layer_takeoff_unavailable')
        return {**record, **provenance, 'status':'stale' if reasons else record['result']['status'],
            'result':None if reasons else record['result']}



def carbon_report(alternative, declared, study_years):
    """Readable stage and activity receipts; raw JSON remains available separately."""
    esc = lambda value: html.escape(str(value))
    display = lambda value: '缺数据' if value is None else format(Decimal(str(value)), '.8g')
    labels = {'production':'材料生产', 'transport':'材料运输', 'construction':'施工',
              'operation':'建筑运行', 'end_of_life':'寿命末期'}
    statuses = {'calculated':'已计算', 'incomplete':'资料不完整', 'excluded':'未纳入（不等于零）'}
    carbon = alternative['carbon']
    content = '<h3>阶段边界与排放</h3><p>评估期 '+esc(study_years)+' 年。单位面积分母为项目建筑面积；五阶段有数值不等于已完成清单完整性核证。</p>'
    content += '<div class="table-scroll" tabindex="0" role="region" aria-label="阶段排放表"><table><tr><th>阶段</th><th>状态</th><th>kgCO₂e</th><th>纳入范围或排除理由</th></tr>'
    for stage, row in carbon['stages'].items():
        content += '<tr><td>'+labels[stage]+'</td><td>'+statuses[row['status']]+'</td><td>'+('未纳入' if not row['included'] else display(row['kgco2e']))+'</td><td class="prose">'+esc(row['reason'])+'</td></tr>'
    content += '</table></div>'
    rows = {r['activity_id']:r for r in carbon['rows']}
    legs = {r['leg_id']:r for r in declared.get('transport_legs', [])}
    collection = 'materials' in declared
    identity_field, parts_field = ('source_material_id', 'materials') if collection else ('layer_id', 'layers')
    for leg in alternative.get('transport', []):
        source = legs[leg['leg_id']]
        content += '<details><summary>材料运段 · '+esc(leg['name'])+' · '+display(rows[leg['activity_id']]['kgco2e'])+' kgCO₂e</summary>'
        content += ('<p>所选材料实体：' if collection else '<p>所选层：')+esc(', '.join('#'+str(r[identity_field]) for r in leg[parts_field]))+'；采购质量 '+display(leg['purchase_mass_kg'])+' kg × 承运比例 '+display(leg['purchase_fraction'])+' + 附加包装/托盘质量 '+display(leg['additional_mass_kg'])+' kg = 承运质量 '+display(leg['shipped_mass_kg'])+' kg。</p>'
        content += '<p>承运质量 ÷ 1000 × '+display(leg['distance_km'])+' km = '+display(leg['quantity_tkm'])+' tkm。空白输入保持未知；距离和分批均为声明值。</p>'
        content += '<ul>'+''.join('<li>'+label+'：'+esc(source[key])+'</li>' for label,key in [('分批依据','fraction_source'),('距离依据','distance_source'),('附加质量依据','additional_mass_source')])+'</ul></details>'
    activities = [a for a in alternative['carbon_input']['activities'] if a['stage'] != 'production']
    if activities:
        content += '<h3>非生产阶段逐项复算与来源</h3>'
    for activity in activities:
        row, factor = rows[activity['activity_id']], activity['factor']
        period = '每年' if activity['period'] == 'annual' else '整个评估期'
        content += '<details><summary>'+labels[activity['stage']]+' · '+esc(activity['name'])+' · '+display(row['kgco2e'])+' kgCO₂e</summary>'
        content += '<p>输入 '+display(activity['quantity'])+' '+esc(activity['unit'])+'（'+period+'）；期间倍数 '+esc(row['period_multiplier'])+'；换算后整个评估期活动量 '+display(row['quantity_in_factor_unit'])+' '+esc(factor['denominator'])+' × 因子 '+display(factor['value'])+' kgCO₂e/'+esc(factor['denominator'])+'。</p>'
        content += '<p>活动来源：'+esc(activity['source'])+'。</p><p>因子 '+esc(factor['factor_id'])+'：'+esc(factor['source'])+'；发布方 '+esc(factor['publisher'])+'；版本 '+esc(factor['version'])+'；年份 '+esc(factor['year'])+'；地区 '+esc(factor['region'])+'；方法 '+esc(factor['method'])+'。</p></details>'
    content += '<ul>'+''.join('<li>'+esc(note)+'</li>' for note in carbon['limitations'])+'</ul>'
    return content


def report(record):
    esc = lambda value: html.escape(str(value))
    display = lambda value: '缺数据' if value is None else format(Decimal(str(value)), '.8g')
    state = {'calculated':'已计算','incomplete':'资料不完整','stale':'来源已失效'}.get(record['status'],record['status'])
    result = record['result']
    collection = 'materialset_id' in record['input']
    identity_field, mappings_field, prefix = ('source_material_id', 'materials', 'material_') if collection else ('layer_id', 'layers', 'layer_')
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
            content += '<h2>'+esc(alternative['name'])+(' · 按材料实体数量与依据</h2>' if collection else ' · 逐层数量与依据</h2>')
            content += '<div class="table-scroll" tabindex="0" role="region" aria-label="逐层计量表"><table><tr><th>来源层 / 拟用材料</th><th>包络 m³</th><th>实体材料 m³</th><th>含损耗采购 m³</th><th>材料金额</th><th>生产碳 kgCO₂e</th></tr>'
            carbon_rows = {r['activity_id']:r for r in alternative['carbon']['rows']}
            for row, cost, mapping in zip(alternative['derivations'], alternative['cost']['rows'], declared[mappings_field]):
                carbon = carbon_rows[prefix+str(row[identity_field])]
                values = ['#'+str(row[identity_field])+' '+(row['source_material_name'] or '未命名材料')+' → '+mapping['name'],
                    display(row['envelope_volume_m3']),display(row['net_material_volume_m3']),display(row['purchase_volume_m3']),cost['amount'],display(carbon['kgco2e'])]
                content += '<tr>'+''.join('<td>'+esc(v if v is not None else '缺数据')+'</td>' for v in values)+'</tr>'
            content += '</table></div><details><summary>查看实体比例、损耗、价格和因子依据</summary><ul>'
            for mapping in declared[mappings_field]:
                content += '<li>'+esc(mapping['name'])+'：实体比例 '+esc(mapping['solid_fraction'])+'（'+esc(mapping['fraction_source'])+'）；损耗 '+esc(mapping['waste_ratio'])+'（'+esc(mapping['waste_basis'])+'）；报价 '+esc(mapping['quote']['source'])+' / '+esc(mapping['quote']['version'])+'；因子 '+esc(mapping['factor']['source'])+' / '+esc(mapping['factor']['version'])+'</li>'
            content += '</ul></details>'
            content += carbon_report(alternative, declared, record['input']['study_years'])

    if collection:content = content.replace('逐层计量表', '逐材料计量表').replace('来源层 / 拟用材料', '来源材料实体 / 拟用材料')
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>材料方案比较</title><style>body{font:16px/1.7 system-ui;max-width:1000px;margin:30px auto;padding:20px}body{overflow-wrap:anywhere;box-sizing:border-box}.table-scroll{max-width:100%;overflow-x:auto}table{border-collapse:collapse;width:100%;min-width:480px}td,th{border:1px solid #ccd6d4;padding:10px;text-align:left}td:not(:first-child){white-space:nowrap;overflow-wrap:normal}td:first-child,th:first-child{min-width:180px;max-width:260px;white-space:normal}td.prose{white-space:normal;min-width:200px;max-width:360px}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style><h1>材料方案比较</h1><p>状态：'+esc(state)+' · 功能等效性未核验，非总造价或碳资产认证。</p><p>表格数值按8位有效数字展示；金额保留分，原始精度见计算回执。窄屏可在表格内横向滚动。</p>'+content+'<details><summary>输入、逐层公式及来源回执</summary><pre>'+esc(json.dumps(record,ensure_ascii=False,indent=2))+'</pre></details></html>'


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
