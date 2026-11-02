"""Evidence-bound material procurement and CCER preparation, never credit issuance."""
import math
import re
import unicodedata
import uuid
from pathlib import Path
from typing import Literal

from pydantic import Field, StrictBool, model_validator

from . import core
from .materials import evidence_changes, evidence_snapshot
from .schema import Contract

CATALOG = Path(__file__).resolve().parents[1] / 'cases/material_research.json'
DISCOVERY = CATALOG.with_name('material_discovery_index.json')
METHOD_URL = 'https://www.mee.gov.cn/xxgk2018/xxgk/xxgk06/202512/W020251223502007241623.pdf'
CHECKS = {
    'public_building': ('既有公共建筑或符合定义的建筑单元', '2; 4.1–4.2'),
    'same_use': ('基准期与计入期用途一致', '2(a)'),
    'prior_design': ('改造前节能设计符合适用标准', '2(c)'),
    'excluded_systems_absent': ('无方法学排除的联供、燃煤和外购蒸汽直驱溴化锂系统', '2(e)'),
    'continuous_metering': ('连续计量与定期记录', '2(f)'),
    'platform_timing': ('基准期开始前已联网试运行，减排发生时间满足要求', '2(g)'),
    'ownership': ('产权及HVAC系统权属或授权完整', '2(h)'),
    'aggregation': ('合并项目同省、全部授权且年减排量不超过6万吨', '2(h)'),
    'not_pilot_ets': ('未纳入碳排放权交易试点管理', '2(i)'),
    'legal_compliance': ('法律、标准及行业政策符合性', '2(j)'),
    'baseline_continuous': ('改造前连续稳定24个月、能源与运行边界完整', '7.2 tables 4–6'),
    'meter_calibration': ('计量点位与检定校准凭证可追溯', '7.3.2'),
    'additionality': ('额外性等项目开发要求经专业核对', '5'),
    'unique_claim': ('权属与唯一性、避免重复申报', '发布通知 一'),
}
MEASURES = {str(i): name for i, name in enumerate([
    '外墙外保温', '外墙内保温', '更换整窗', '加窗', '更换透明幕墙和采光顶',
    '更换透明幕墙和采光顶玻璃', '高效冷水机组', '高效热泵机组', '多联式空调（热泵）机组'], 1)}


def catalog(*, include_discovery=False):
    data = core.read_json(CATALOG)
    discovery=core.read_json(DISCOVERY)
    data['collection_stats']={**data.get('collection_stats',{}),**discovery.get('collection_stats',{})}
    if include_discovery:
        data['discovery'] = discovery
    return {**data, 'sha256': core.sha(CATALOG), 'methodology': {'id': 'CCER-06-001-V01',
            'url': METHOD_URL, 'checks': CHECKS, 'measures': MEASURES},
            'price_cny': None, 'epd_factors': None,
            'notice': '文献方向不是可采购产品；不自动填入热工参数、价格、EPD或节能率。钨、钒不是稀土。'}


def research_lookup(query=None, limit=5):
    """Narrow evidence retrieval before the agent's generic 16-item context cap."""
    data = catalog()
    entries = data['entries']
    if query:
        def normalize(value):
            return unicodedata.normalize('NFKC', value).translate(str.maketrans({'–':'-', '—':'-', '‑':'-'})).casefold()
        term = normalize(query.strip())
        term = term.removeprefix('https://doi.org/').removeprefix('http://doi.org/')
        exact = [e for e in entries if term in {normalize(e['id']),normalize(e.get('doi') or '')}]
        if exact or re.fullmatch(r'10\.\d{4,9}/\S+', term):
            return {**data, 'entries':exact[:limit], 'query':query, 'total_matches':len(exact),
                    'has_more':len(exact)>limit, 'lookup_method':'exact_identifier',
                    'lookup_hint':'按DOI或索引ID精确匹配；未匹配不代表材料不存在。'}
        aliases = [('lab6','六硼化镧','lanthanum hexaboride'), ('ceo2','氧化铈','cerium oxide','ceria'),
                   ('y2o3','氧化钇','yttrium oxide'), ('low-e','lowe','low e','低辐射')]
        terms = re.findall(r'[a-z][a-z0-9]*(?:-[a-z0-9]+)*|[\u4e00-\u9fff]+', term) or [term]
        def hit(word, text):
            return bool(re.search(r'(?<![a-z0-9])'+re.escape(word)+r'(?![a-z0-9])', text)) if re.fullmatch(r'[a-z0-9-]+', word) else word in text
        anchors = [group for group in aliases if any(hit(word, term) for word in group)]
        ranked = []
        for e in entries:
            text = normalize(' '.join([e['id'],e['name'],e['title'],e['finding'],e.get('doi') or '',*e['keywords']]))
            groups = sum(any(hit(w,text) for w in group) for group in anchors)
            matches = [t for t in terms if hit(t,text)]
            if (anchors and groups) or (not anchors and matches):
                score = groups * 10 + len(matches) + (100 if term == normalize(e['id']) or term == normalize(e.get('doi') or '') else 0)
                ranked.append((score,e))
        ranked.sort(key=lambda pair: -pair[0])
        entries = [e for _,e in ranked]
    return {**data, 'entries': entries[:limit], 'query': query, 'total_matches': len(entries),
            'has_more': len(entries) > limit,
            'lookup_method': '化学式/常用名称锚定及分词匹配，非语义模型评分；多词不要求原文连续出现。',
            'lookup_hint': 'query可用具体名称、化学式、用途、DOI或题名片段；最多5条。has_more时请缩小范围，不必反复尝试同义长句。未返回不等于不存在。'}


class Estimate(Contract):
    name: str = Field(min_length=1, max_length=160)
    research_id: str | None = Field(default=None, max_length=80)
    study_option_id: str | None = Field(default=None, max_length=40)
    quantity: float = Field(gt=0, le=1e9, strict=True)
    unit: Literal['kg', 'm2', 'm3', 'item']
    unit_price_cny: float | None = Field(default=None, ge=0, le=1e9, strict=True)
    quote_evidence_id: str | None = None
    gwp_per_unit: float | None = Field(default=None, ge=0, le=1e9, strict=True)
    gwp_unit: Literal['kg', 'm2', 'm3', 'item'] | None = None
    gwp_boundary: Literal['A1-A3', 'A1-A5'] | None = None
    gwp_evidence_id: str | None = None
    source_locator: str = Field(min_length=5, max_length=1000)
    service_life_years: int | None = Field(default=None, ge=1, le=100, strict=True)

    @model_validator(mode='after')
    def evidence(self):
        if self.unit_price_cny is not None and not self.quote_evidence_id:
            raise ValueError('报价需要项目内已复核证据')
        if self.gwp_per_unit is not None and (not self.gwp_evidence_id or not self.gwp_boundary or self.gwp_unit != self.unit):
            raise ValueError('GWP需来源、边界及与工程量一致的声明单位；禁止隐式kg/m²转换')
        return self


class Selection(Contract):
    intent: str = Field(min_length=5, max_length=4000)
    budget_cny: float = Field(ge=0, le=1e12, strict=True)
    application: Literal['all', 'glazing', 'coating', 'cement', 'hvac', 'insulation', 'research'] = 'all'
    horizon_years: int = Field(default=20, ge=1, le=100, strict=True)
    estimates: list[Estimate] = Field(default_factory=list, max_length=12)
    study_id: str | None = None


class Declaration(Contract):
    satisfied: StrictBool | None = None
    evidence_id: str | None = None
    locator: str = Field(default='', max_length=1000)


class Measure(Contract):
    code: Literal['1', '2', '3', '4', '5', '6', '7', '8', '9']
    coverage: float = Field(ge=0, le=1, strict=True)
    evidence_id: str
    performance: Declaration = Field(default_factory=Declaration)


class CreditScreen(Contract):
    checks: dict[str, Declaration] = Field(default_factory=dict, max_length=len(CHECKS))
    monthly_hours: list[float] = Field(default_factory=list, max_length=24)
    hours_evidence_id: str | None = None
    start_month: int = Field(default=1, ge=1, le=12, strict=True)
    school_kind: Literal['ordinary', 'primary_secondary_kindergarten'] = 'ordinary'
    measures: list[Measure] = Field(default_factory=list, max_length=9)
    hypothetical_tonnes: float | None = Field(default=None, ge=0, le=1e9, strict=True)
    prices_cny_per_t: list[float] = Field(default_factory=list, max_length=3)
    development_cost_cny: float | None = Field(default=None, ge=0, le=1e12, strict=True)
    monitoring_cost_cny: float | None = Field(default=None, ge=0, le=1e12, strict=True)

    @model_validator(mode='after')
    def finite(self):
        if set(self.checks) - CHECKS.keys():
            raise ValueError('未知方法学检查项')
        if any(v < 0 or v > 744 for v in self.monthly_hours) or any(v < 0 or v > 1e7 for v in self.prices_cny_per_t):
            raise ValueError('运行小时或碳价超出范围')
        if len({m.code for m in self.measures}) != len(self.measures):
            raise ValueError('技术措施不得重复')
        return self


class Sustainability:
    def __init__(self, domain):
        self.domain, self.store = domain, domain.store

    def source(self, pid, eid, snapshots):
        if not eid:
            return False
        ev = evidence_snapshot(self.domain, pid, eid)
        if ev['status'] not in {'DOCUMENTED', 'MEASURED', 'IMPORTED'}:
            raise core.ValidationError('材料造价、EPD和合规依据不能使用假设或AI推断')
        snapshots[eid] = ev
        return True

    def select(self, pid, body):
        self.store.get('project', pid)
        data, snapshots = catalog(), {}
        candidates = []
        for entry in data['entries']:
            if body.application != 'all' and entry['application'] != body.application:
                continue
            matches = [word for word in entry['keywords'] if (
                re.search(r'(?<![A-Za-z0-9])' + re.escape(word) + r'(?![A-Za-z0-9])', body.intent, re.I)
                if re.fullmatch(r'[A-Za-z][A-Za-z0-9.-]*', word) else word.casefold() in body.intent.casefold())]
            candidates.append({**entry, 'matched_terms': matches, 'match_count': len(matches),
                               'selection_state': 'RESEARCH_ONLY' if entry['application'] == 'research' else 'NEEDS_PRODUCT_EVIDENCE'})
        candidates.sort(key=lambda row: (-row['match_count'], row['id']))
        known = {entry['id'] for entry in data['entries']}
        study = self.domain.decisions.view(pid, body.study_id) if body.study_id else None
        assessment = study.get('assessment') if study and study['status'] == 'succeeded' else None
        assessed = {r['option_id']: r for r in assessment['rows']} if assessment else {}
        rows = []
        for i, item in enumerate(body.estimates):
            if item.research_id and item.research_id not in known:
                raise core.ValidationError('未知文献方向')
            self.source(pid, item.quote_evidence_id, snapshots)
            self.source(pid, item.gwp_evidence_id, snapshots)
            cost = item.quantity * item.unit_price_cny if item.unit_price_cny is not None else None
            carbon = item.quantity * item.gwp_per_unit if item.gwp_per_unit is not None else None
            cycles = math.ceil(body.horizon_years / item.service_life_years) if item.service_life_years else None
            target, baseline = assessed.get(item.study_option_id), assessed.get('baseline')
            if item.study_option_id and (not target or not baseline or target['status'] not in {'FEASIBLE', 'EXCLUDED'}):
                raise core.ValidationError('绑定方案必须来自当前有效且已完成的真实研究')
            saving = (baseline['values']['carbon_kg'] - target['values']['carbon_kg']) if target and baseline and (
                baseline['values'].get('carbon_kg') is not None and target['values'].get('carbon_kg') is not None) else None
            material_total = carbon * cycles if carbon is not None and cycles else None
            rows.append({'option': i, **item.model_dump(), 'initial_cost_cny': cost, 'initial_embodied_kgco2e': carbon,
                         'replacement_cycles': cycles, 'horizon_material_kgco2e': material_total,
                         'annual_operating_saving_kgco2': saving,
                         'partial_horizon_net_reduction_kg': saving * body.horizon_years - material_total
                         if saving is not None and material_total is not None else None,
                         'within_budget': cost <= body.budget_cny if cost is not None else None})
        # Different declared units may be compared only if engineer specified equivalent scope.
        # Do not rank dissimilar quantities/products without functional equivalence evidence.
        return self.save(pid, 'selection', body, {'candidates': candidates, 'estimates': rows,
            'study': study, 'recommendation': 'DIRECTION_SHORTLIST_ONLY',
            'ranking_basis': '按意图关键词匹配数排序，非LLM评分；报价决定预算筛选，缺价保留未知。不同功能单位不直接优劣排序。',
            'carbon_scope': '材料阶段按声明边界分项；替换与绑定研究的运行减排按恒定参数延续。净减排仅为所填材料新增碳负担扣运行差值的部分边界情景，不含缺失运输、拆除与回收，不称完整LCA。',
            'issued_credits_t': None, 'credit_revenue_in_base_case': False}, snapshots)

    def screen(self, pid, body):
        self.store.get('project', pid)
        snapshots, rows = {}, []
        for key, (label, clause) in CHECKS.items():
            value = body.checks.get(key, Declaration())
            sourced = self.source(pid, value.evidence_id, snapshots) and bool(value.locator)
            state = 'FAIL' if value.satisfied is False else 'DECLARED_PASS' if value.satisfied is True and sourced else 'MISSING'
            rows.append({'key': key, 'label': label, 'clause': clause, 'state': state, **value.model_dump()})
        hours_source = self.source(pid, body.hours_evidence_id, snapshots)
        bad_months = [i + 1 for i, h in enumerate(body.monthly_hours) if h < 160 and not (
            body.school_kind == 'primary_secondary_kindergarten' and (body.start_month + i - 1) % 12 + 1 in {1, 2, 7, 8})]
        rows.append({'key': 'monthly_hours', 'label': '基准期逐月运行小时', 'clause': '2(b);7.2',
                     'state': 'FAIL' if bad_months else 'DECLARED_PASS' if len(body.monthly_hours) == 24 and hours_source else 'MISSING',
                     'failed_month_indexes': bad_months})
        measures = []
        for item in body.measures:
            sourced = self.source(pid, item.evidence_id, snapshots)
            performance_source = self.source(pid, item.performance.evidence_id, snapshots) and bool(item.performance.locator)
            minimum = .8 if int(item.code) <= 6 else .66
            state = 'FAIL' if item.coverage < minimum or item.performance.satisfied is False else (
                'DECLARED_PASS' if sourced and performance_source and item.performance.satisfied is True else 'MISSING')
            measures.append({**item.model_dump(), 'name': MEASURES[item.code], 'minimum_coverage': minimum,
                             'coverage_basis': '相关面积' if int(item.code) <= 6 else '总额定制冷/制热量', 'state': state})
        rows.append({'key': 'appendix_a', 'label': '至少一项附录A措施覆盖率与性能', 'clause': '2(d);附录A',
                     'state': 'DECLARED_PASS' if any(m['state'] == 'DECLARED_PASS' for m in measures) else 'MISSING' if not measures or any(m['state'] == 'MISSING' for m in measures) else 'FAIL'})
        status = 'BLOCKED' if any(r['state'] == 'FAIL' for r in rows) else 'NEEDS_EVIDENCE' if any(r['state'] == 'MISSING' for r in rows) else 'READY_FOR_PROFESSIONAL_REVIEW'
        money = [{'price_cny_per_t': p, 'hypothetical_gross_cny': p * body.hypothetical_tonnes,
                  'hypothetical_net_cny': p * body.hypothetical_tonnes - body.development_cost_cny - body.monitoring_cost_cny
                  if body.development_cost_cny is not None and body.monitoring_cost_cny is not None else None}
                 for p in body.prices_cny_per_t] if body.hypothetical_tonnes is not None else []
        return self.save(pid, 'credit_screen', body, {'status': status, 'checks': rows, 'measures': measures,
            'methodology': data_method(), 'economic_scenarios': money, 'issued_credits_t': None,
            'eligible_credits_t': None, 'credit_revenue_in_base_case': False,
            'next_steps': [r['label'] for r in rows if r['state'] != 'DECLARED_PASS'] + [
                '专业项目设计/额外性与唯一性复核', '第三方审定与项目登记', '实际监测和方法学减排量核算', '第三方核查及减排量登记', '交易账户与可用签发量核对'],
            'limitations': ['只对已实现条款做准备度预筛；勾选及来源复核不等于审定结论。',
                            '未实现完整方法学减排公式、额外性裁定、平台联网、签发或下单。',
                            '碳价和假设吨数由用户输入，不是行情或可售库存；税费、交易费、折现及履约风险未计。']}, snapshots)

    def save(self, pid, kind, body, result, snapshots):
        extra = {'package_rules_hash': core.sha(Path(__file__).with_name('retrofit_packages.py'))} if kind == 'package' else {}
        return self.store.put('sustainability', {'sustainability_id': 'sustainability_' + uuid.uuid4().hex,
            'project_id': pid, 'kind': kind, 'input': body.model_dump(mode='json'), 'result': result,
            'evidence_snapshots': list(snapshots.values()), 'code_hash': core.sha(Path(__file__)),
            'catalog_hash': core.sha(CATALOG), 'created_at': core.now(), **extra})

    def view(self, pid, record):
        if record['project_id'] != pid:
            raise core.ValidationError('Cross-project report rejected')
        stale = evidence_changes(self.domain, pid, record['evidence_snapshots'])
        if record['code_hash'] != core.sha(Path(__file__)) or record['catalog_hash'] != core.sha(CATALOG):
            stale.append('材料目录或评估规则版本变化')
        if record['kind'] == 'package':
            if record.get('package_rules_hash') != core.sha(Path(__file__).with_name('retrofit_packages.py')):
                stale.append('整包比选规则版本变化')
            # Expired quotations invalidate the current view, while retaining the saved record.
            from datetime import date
            for package in record['input']['packages']:
                for item in package['items']:
                    for value in [*item['costs'].values(), item['annual_maintenance'], item['replacement']]:
                        if value.get('valid_until') and value['valid_until'] < date.today().isoformat():
                            stale.append('报价已过有效期')
        if record['kind'] == 'selection' and record['input'].get('study_id'):
            current = self.domain.decisions.view(pid, record['input']['study_id'])
            if current != record['result']['study']:
                stale.append('绑定的真实材料研究发生变化')
        return {**record, 'stale_reasons': stale, 'current': not stale,
                'result': None if stale else record['result']}


def data_method():
    return {'id': 'CCER-06-001-V01', 'source_url': METHOD_URL, 'checked_on': '2026-11-01',
            'implementation': 'partial_readiness_screen_not_certification'}


def register_sustainability(app, domain):
    service = domain.sustainability = Sustainability(domain)
    from .retrofit_packages import register_packages
    register_packages(app, service)

    @app.get('/api/projects/{project_id}/material-research')
    def research(project_id: str):
        domain.store.get('project', project_id)
        return catalog(include_discovery=True)

    @app.post('/api/projects/{project_id}/sustainability/selections', status_code=201)
    def selection(project_id: str, body: Selection):
        return service.select(project_id, body)

    @app.post('/api/projects/{project_id}/sustainability/credit-screens', status_code=201)
    def screen(project_id: str, body: CreditScreen):
        return service.screen(project_id, body)

    @app.get('/api/projects/{project_id}/sustainability')
    def reports(project_id: str):
        return [service.view(project_id, r) for r in domain.store.list('sustainability', project_id)]

    @app.get('/api/projects/{project_id}/sustainability/{report_id}')
    def report(project_id: str, report_id: str):
        return service.view(project_id, domain.store.get('sustainability', report_id))
