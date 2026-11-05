"""Source-bound material quantities and quote scenarios; not tender certification."""
import html
import json
import re
from datetime import date
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP, localcontext
from pathlib import Path
from typing import Literal
from pydantic import Field, StrictFloat, StrictInt, field_validator, model_validator
from . import core
from .domain import identifier
from .schema import Contract

Unit = Literal['kg', 't', 'm', 'cm', 'mm', 'm2', 'm3', 'item']
UNITS = {'kg': ('mass', '1', 'kg'), 't': ('mass', '1000', 'kg'),
    'm': ('length', '1', 'm'), 'cm': ('length', '.01', 'm'), 'mm': ('length', '.001', 'm'),
    'm2': ('area', '1', 'm2'), 'm3': ('volume', '1', 'm3'), 'item': ('count', '1', 'item')}
D = lambda value: Decimal(str(value))
CENT = Decimal('.01')


class Measure(Contract):
    mode: Literal['direct', 'rectangle', 'cuboid']
    unit: Unit
    quantity: StrictFloat | None = Field(default=None, ge=0, le=1e12)
    length: StrictFloat | None = Field(default=None, gt=0, le=1e7)
    width: StrictFloat | None = Field(default=None, gt=0, le=1e7)
    height: StrictFloat | None = Field(default=None, gt=0, le=1e7)
    dimension_unit: Literal['m', 'cm', 'mm'] | None = None
    count: StrictInt | None = Field(default=None, gt=0, le=1000000)
    deduction: StrictFloat | None = Field(default=None, ge=0, le=1e12)
    source: str = Field(min_length=5, max_length=2000)

    @model_validator(mode='after')
    def coherent(self):
        if self.mode == 'direct':
            if any(getattr(self, k) is not None for k in ('length','width','height','dimension_unit','count','deduction')):
                raise ValueError('Direct quantity is net; geometry fields must be absent')
            if self.unit == 'item' and self.quantity is not None and not self.quantity.is_integer():
                raise ValueError('Item count must be an integer')
        else:
            if self.quantity is not None or self.unit != ('m2' if self.mode == 'rectangle' else 'm3'):
                raise ValueError('Geometry requires m2/m3 and no direct quantity')
            if self.mode == 'rectangle' and self.height is not None:
                raise ValueError('Rectangle has no height parameter')
        return self


class Quote(Contract):
    quote_id: str = Field(min_length=1, max_length=100)
    unit_price: StrictFloat | None = Field(default=None, ge=0, le=1e12)
    per_unit: Unit
    currency: Literal['CNY', 'USD', 'EUR']
    tax_basis: Literal['included', 'excluded']
    region: str = Field(min_length=1, max_length=100)
    valid_from: date
    valid_until: date
    source: str = Field(min_length=5, max_length=2000)
    version: str = Field(min_length=1, max_length=100)

    @field_validator('valid_from', 'valid_until', mode='before')
    @classmethod
    def explicit_dates(cls, value):
        if type(value) is not date and (not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value)):
            raise ValueError('Use explicit ISO date, not numeric timestamps')
        return value

    @model_validator(mode='after')
    def period(self):
        if self.valid_until < self.valid_from:
            raise ValueError('Quote date interval is reversed')
        return self


class MaterialLine(Contract):
    line_id: str = Field(min_length=1, max_length=100)
    material_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    measure: Measure
    waste_ratio: StrictFloat | None = Field(default=None, ge=0, le=1)
    waste_basis: str = Field(min_length=5, max_length=1000)
    density_kg_m3: StrictFloat | None = Field(default=None, ge=1e-6, le=100000)
    density_source: str | None = Field(default=None, min_length=5, max_length=2000)
    quote: Quote
    evidence_ids: list[str] = Field(default_factory=list, max_length=30)

    @model_validator(mode='after')
    def compatibility(self):
        a, b = UNITS[self.measure.unit][0], UNITS[self.quote.per_unit][0]
        if a != b and {a,b} != {'mass','volume'}:
            raise ValueError('Incompatible quantity and quote dimensions')
        if a == b and (self.density_kg_m3 is not None or self.density_source is not None):
            raise ValueError('Density is only used for mass-volume conversion')
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError('Duplicate evidence IDs')
        return self


class Estimate(Contract):
    name: str = Field(min_length=1, max_length=160)
    region: str = Field(min_length=1, max_length=100)
    currency: Literal['CNY', 'USD', 'EUR']
    tax_basis: Literal['included', 'excluded']
    as_of: date
    functional_scope: str = Field(min_length=10, max_length=2000)
    exclusions: list[str] = Field(min_length=1, max_length=30)
    import_file_id: str | None = Field(default=None, pattern=r'^file_[a-f0-9]{32}$')
    lines: list[MaterialLine] = Field(min_length=1, max_length=300)

    @field_validator('as_of', mode='before')
    @classmethod
    def explicit_date(cls, value):
        return Quote.explicit_dates(value)

    @model_validator(mode='after')
    def coherent(self):
        if any(not x.strip() or len(x)>500 for x in self.exclusions) or len(set(self.exclusions)) != len(self.exclusions):
            raise ValueError('Explicit unique exclusions required')
        if len({x.line_id for x in self.lines}) != len(self.lines):
            raise ValueError('Duplicate line ID; double counting rejected')
        quotes = {}
        for row in self.lines:
            q = row.quote
            if (q.currency,q.tax_basis,q.region) != (self.currency,self.tax_basis,self.region):
                raise ValueError('Quote currency, tax basis and region must match the estimate')
            if not q.valid_from <= self.as_of <= q.valid_until:
                raise ValueError('Quote does not cover the explicit valuation date')
            payload = q.model_dump(mode='json')
            if q.quote_id in quotes and quotes[q.quote_id] != payload:
                raise ValueError('Same quote ID has inconsistent price, unit, source or version')
            quotes[q.quote_id] = payload
        return self


def quantity(measure):
    if measure.mode == 'direct':
        return None if measure.quantity is None else D(measure.quantity), 'declared net quantity'
    keys = ['length','width','dimension_unit','count','deduction'] + (['height'] if measure.mode == 'cuboid' else [])
    if any(getattr(measure, key) is None for key in keys):
        return None, 'missing geometry/count/deduction/unit'
    scale = D(UNITS[measure.dimension_unit][1])
    gross = D(measure.length)*D(measure.width)*scale**2*measure.count
    if measure.mode == 'cuboid':
        gross *= D(measure.height)*scale
    net = gross-D(measure.deduction)
    if net < 0:
        raise core.ValidationError('Deduction exceeds gross quantity')
    return net, ('length*width' + ('*height' if measure.mode=='cuboid' else '') + '*unit_scale^dimension*count - deduction')


def text_number(value):
    return None if value is None else format(value, 'f')


def calculate(body):
    # Fixed Decimal precision is independent of process-global financial settings.
    with localcontext() as ctx:
        ctx.prec = 80
        rows, missing, groups = [], [], {}
        for line in body.lines:
            net, formula = quantity(line.measure)
            purchase = None if net is None or line.waste_ratio is None else net*(1+D(line.waste_ratio))
            if purchase is not None and line.measure.unit == 'item':
                purchase = purchase.to_integral_value(rounding=ROUND_CEILING)
            source_dim, source_scale, canonical = UNITS[line.measure.unit]
            quote_dim, quote_scale, _ = UNITS[line.quote.per_unit]
            quoted = None if purchase is None else purchase*D(source_scale)/D(quote_scale)
            if source_dim != quote_dim:
                if line.density_kg_m3 is None or not line.density_source:
                    quoted = None
                elif quoted is not None:
                    quoted = quoted*D(line.density_kg_m3) if source_dim=='volume' else quoted/D(line.density_kg_m3)
            amount = None if quoted is None or line.quote.unit_price is None else (quoted*D(line.quote.unit_price)).quantize(CENT,rounding=ROUND_HALF_UP)
            if amount is None:
                missing.append(line.line_id)
            rows.append({'line_id':line.line_id,'material_id':line.material_id,'name':line.name,'unit':line.measure.unit,
                'net_quantity':text_number(net),'purchase_quantity':text_number(purchase),'quantity_in_quote_unit':text_number(quoted),
                'quote_unit':line.quote.per_unit,'amount':text_number(amount),'quantity_formula':formula,
                'cost_formula':'net*(1+waste), ceil for item; dimensional conversion; *unit_price; round HALF_UP to 0.01 per line',
                'missing':[k for k,v in [('net_quantity',net),('waste_ratio',line.waste_ratio),('quote_quantity',quoted),('unit_price',line.quote.unit_price)] if v is None]})
            key=(line.material_id,canonical)
            group=groups.setdefault(key,{'net':[],'purchase':[]})
            group['net'].append(None if net is None else net*D(source_scale))
            group['purchase'].append(None if purchase is None else purchase*D(source_scale))
        sums=[]
        for (material_id,unit),values in groups.items():
            sums.append({'material_id':material_id,'unit':unit,**{key:text_number(sum(v,Decimal(0))) if all(x is not None for x in v) else None for key,v in values.items()}})
        total = None if missing else sum((D(row['amount']) for row in rows),Decimal('0.00'))
        return {'status':'incomplete' if missing else 'calculated','rows':rows,'materials':sums,'missing_lines':missing,
            'material_total':text_number(total),'currency':body.currency,'tax_basis':body.tax_basis,'as_of':body.as_of.isoformat(),
            'source_status':'USER_DECLARED','tender_certification':'NOT_ASSESSED','functional_equivalence':'NOT_ASSESSED',
            'rounding':'Decimal, HALF_UP 0.01 per line then sum; item procurement rounded upward per line',
            'limitations':['只计算声明材料清单；不自动加入人工、机械、运输、管理费、税额、汇率或碳收益。',
                '价格有效期、地区及来源由用户声明；未验证市场报价真实性或材料功能等效性。',
                '几何量为矩形/长方体显式参数估算；扣减使用输出单位m²或m³，不是CAD自动算量或计量规范认证。',
                '未计损耗填写0，未知留空；按件采购逐行向上取整。金额为十进制字符串，避免JSON浮点金额失真。']}


class Costs:
    def __init__(self, domain):
        self.domain,self.store=domain,domain.store

    def save(self,pid,body):
        project=self.store.get('project',pid)
        if body.region != project['building']['region']:
            raise core.ValidationError('Estimate region must match project declaration')
        sources=[]; imported=None
        for eid in sorted({eid for line in body.lines for eid in line.evidence_ids}):
            ev=self.store.get('evidence',eid)
            if ev['project_id']!=pid or ev['review_state']=='rejected':
                raise core.ValidationError('Foreign or rejected material cost evidence')
            if ev['source_file']: self.domain.file_record(pid,ev['source_file'])
            sources.append(ev)
        if body.import_file_id: imported,_=self.domain.file_record(pid,body.import_file_id)
        obj={'cost_id':identifier('cost'),'project_id':pid,'project_revision':project['revision'],
            'input':body.model_dump(mode='json'),'result':calculate(body),'source_snapshot':sources,'import_source':imported,
            'calculator_hash':core.sha(Path(__file__)),'created_at':core.now()}
        obj['hash']=core.hash_json(obj); self.store.put('cost',obj)
        return self.view(pid,obj['cost_id'])

    def view(self,pid,cid):
        obj=self.store.get('cost',cid)
        if obj['project_id']!=pid: raise core.ValidationError('Cross-project cost record rejected')
        if core.hash_json({k:v for k,v in obj.items() if k not in {'hash','revision'}})!=obj['hash']:
            raise core.ValidationError('Cost record integrity failed')
        stale=obj['project_revision']!=self.store.get('project',pid)['revision'] or obj['calculator_hash']!=core.sha(Path(__file__))
        files=[]
        if obj['import_source']: files.append(obj['import_source']['file_id'])
        for old in obj['source_snapshot']:
            ev=self.store.get('evidence',old['evidence_id'])
            stale |= ev['review_state']=='rejected' or ev['revision']!=old['revision'] or ev['hash']!=old['hash']
            if ev['source_file']: files.append(ev['source_file'])
        for fid in files:
            try: self.domain.file_record(pid,fid)
            except (ValueError,KeyError,OSError): stale=True
        return {**obj,'status':'stale' if stale else obj['result']['status'],'result':None if stale else obj['result']}


class Comparison(Contract):
    cost_ids: list[str] = Field(min_length=2,max_length=5)


def compare(service,pid,body):
    if len(body.cost_ids)!=len(set(body.cost_ids)): raise core.ValidationError('Distinct estimates required')
    records=[service.view(pid,cid) for cid in body.cost_ids]
    if any(r['status']!='calculated' for r in records): raise core.ValidationError('Current complete estimates required')
    def context(r):
        b=r['input']
        return {k:b[k] for k in ('region','currency','tax_basis','as_of','functional_scope')} | {'exclusions':sorted(b['exclusions'])}
    if any(context(r)!=context(records[0]) for r in records[1:]): raise core.ValidationError('Comparison scope/date/currency/tax/region mismatch')
    with localcontext() as ctx:
        ctx.prec=80
        base=D(records[0]['result']['material_total'])
        rows=[]
        for r in records:
            value=D(r['result']['material_total'])
            rows.append({'cost_id':r['cost_id'],'name':r['input']['name'],'material_total':text_number(value),
                'difference_from_baseline':text_number(value-base),
                'reduction_pct':None if base==0 else text_number(((base-value)/base*100).quantize(Decimal('.0001'),rounding=ROUND_HALF_UP))})
    return {'baseline_id':body.cost_ids[0],'currency':records[0]['input']['currency'],'results':rows,
        'note':'仅比较相同声明范围的材料成本情景；未验证功能等效性，不自动推荐最低价方案。'}


def report(record):
    esc=lambda v:html.escape(str(v))
    def measured(value, unit):
        # Display only: retain full decimal strings in the record below.
        number='—' if value is None else (value.rstrip('0').rstrip('.') if '.' in value else value)
        return number+' '+unit
    result=record['result']
    content='<p>来源或计算器已变更，当前结果不可用。</p>'
    if result:
        content='<h2>材料清单合计：'+esc(result['material_total'] if result['material_total'] is not None else '缺数据，不能汇总')+' '+esc(result['currency'])+'</h2>'
        content+='<table><tr><th>材料</th><th>净量</th><th>用量</th><th>计价数量</th><th>金额</th></tr>'+''.join('<tr>'+''.join('<td>'+esc(v if v is not None else '—')+'</td>' for v in (x['name'],measured(x['net_quantity'],x['unit']),measured(x['purchase_quantity'],x['unit']),measured(x['quantity_in_quote_unit'],x['quote_unit']),x['amount']))+'</tr>' for x in result['rows'])+'</table>'
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>材料成本清单</title><style>body{font:16px/1.7 system-ui;max-width:1000px;margin:30px auto;padding:20px}td,th{border:1px solid #ccc;padding:8px}table{border-collapse:collapse}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style><h1>'+esc(record['input']['name'])+'</h1><p>材料成本情景；不含自动税额、汇率、人工等，非工程总造价或招投标认证。</p>'+content+'<h2>输入、边界、来源及逐项复算</h2><pre>'+esc(json.dumps(record,ensure_ascii=False,indent=2))+'</pre></html>'
