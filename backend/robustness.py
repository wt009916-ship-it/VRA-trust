"""Finite, declared material-conductivity search with actual EnergyPlus calls."""
import itertools
import re
import threading
import uuid
from pathlib import Path

from pydantic import Field, model_validator

from . import core
from .schema import Contract


def objects(text):
    return [[part.strip() for part in chunk.split(',')] for chunk in re.sub(r'!.*', '', text).split(';') if chunk.strip()]


def set_conductivity(text, name, value):
    parsed = objects(text)
    matched = [o for o in parsed if o[0].lower() == 'material' and o[1].lower() == name.lower()]
    if len(matched) != 1 or len(matched[0]) < 7:
        raise core.ValidationError('Material object missing or ambiguous: ' + name)
    matched[0][4] = str(value)
    return '\n\n'.join(',\n  '.join(obj) + ';' for obj in parsed)


class Axis(Contract):
    material: str = Field(min_length=1, max_length=160)
    values: list[float] = Field(min_length=2, max_length=6)
    source: str = Field(min_length=5, max_length=1000)
    evidence_id: str | None = None

    @model_validator(mode='after')
    def valid_values(self):
        if any(v <= 0 or v > 100 for v in self.values) or len(set(self.values)) != len(self.values):
            raise ValueError('Conductivity values must be unique, positive and <= 100 W/(m K)')
        return self


class Search(Contract):
    run_ids: list[str] = Field(min_length=2, max_length=3)
    axes: list[Axis] = Field(min_length=1, max_length=2)
    budget: int = Field(ge=2, le=24)
    ranking_tolerance_kwh: float = Field(default=.01, gt=0, le=1000)


class Acquisition(Contract):
    material: str
    confirmed_value: float = Field(gt=0)
    cost_cny: float = Field(ge=0, le=1000000)
    duration_hours: float = Field(ge=0, le=10000)
    method: str = Field(min_length=3, max_length=1000)


class Actions(Contract):
    actions: list[Acquisition] = Field(min_length=1, max_length=20)


def stability_status(points, total):
    if not points:
        return 'NOT_ASSESSED'
    if any(p['flipped'] for p in points):
        return 'COUNTEREXAMPLE_FOUND'
    if any(p.get('indeterminate') for p in points):
        return 'RANKING_INDETERMINATE'
    return 'STABLE_ON_ENUMERATED_GRID' if len(points) == total else 'NO_FLIP_WITHIN_BUDGET'


class Robustness:
    def __init__(self, domain):
        self.domain, self.store = domain, domain.store
        self.capacity = threading.BoundedSemaphore(1)

    def recover(self):
        # Persist interruption truth; no resume pretending previous runs finished.
        for obj in self.store.list('search'):
            if obj['status'] == 'running':
                self.store.put('search', {**obj, 'status': 'failed', 'error': 'Worker interrupted; create a new search'}, obj['revision'])

    def materials(self, run_ids):
        catalogs = []
        for rid in run_ids:
            job = self.store.job(rid)
            _, path = self.domain.file_record(job['project_id'], job['evidence_snapshot']['idf']['source_file'])
            catalog = {o[1]: float(o[4]) for o in objects(path.read_text(encoding='utf-8-sig')) if o[0].lower() == 'material' and len(o) >= 7}
            catalogs.append(catalog)
        common = set.intersection(*(set(c) for c in catalogs)) if catalogs else set()
        return [{'name': name, 'conductivity_w_mk': [c[name] for c in catalogs], 'unit': 'W/(m K)'} for name in sorted(common)]

    def start(self, project_id, body, *, background=True):
        views = [self.domain.view(r) for r in body.run_ids]
        if any(v['project_id'] != project_id or v['status'] != 'succeeded' for v in views):
            raise core.ValidationError('Search requires current verified runs from this project')
        self.domain.compare(body.run_ids)
        energies = sorted(v['metrics']['annual_energy_kwh'] for v in views)
        if any(b - a <= body.ranking_tolerance_kwh for a, b in zip(energies, energies[1:])):
            raise core.ValidationError('参考排序在给定容差内存在并列，不能假定唯一排名')
        names = {m['name'] for m in self.materials(body.run_ids)}
        if len({a.material for a in body.axes}) != len(body.axes) or any(a.material not in names for a in body.axes):
            raise core.ValidationError('Search axes require unique common Material objects')
        if body.budget < len(body.run_ids):
            raise core.ValidationError('Budget must cover at least one complete comparison')
        for axis in body.axes:
            if axis.evidence_id:
                evidence = self.store.get('evidence', axis.evidence_id)
                if evidence['project_id'] != project_id:
                    raise core.ValidationError('Cross-project axis evidence rejected')
        if not self.capacity.acquire(blocking=False):
            raise core.ValidationError('已有反例搜索正在执行')
        record = {'search_id': 'search_' + uuid.uuid4().hex, 'project_id': project_id, 'status': 'running',
            **body.model_dump(), 'reference_order': [v['scheme_id'] for v in sorted(views, key=lambda v: v['metrics']['annual_energy_kwh'])],
            'reference_provenance': [v['provenance'] for v in views], 'points': [], 'engine_calls': 0,
            'created_at': core.now(), 'stability_status': 'NOT_ASSESSED', 'objective': 'annual_site_energy_kwh',
            'domain_type': 'explicit_discrete_grid_not_continuous_interval', 'error': None, 'search_code_hash': core.sha(Path(__file__))}
        record = self.store.put('search', record)
        if background:
            threading.Thread(target=self.execute, args=(record,), daemon=True, name='vra-counterexamples').start()
        else:
            self.execute(record)
        return self.store.get('search', record['search_id'])

    def execute(self, record):
        def save():
            nonlocal record
            record = self.store.put('search', record, record['revision'])
        try:
            domain = list(itertools.product(*(a['values'] for a in record['axes'])))
            record['total_grid_points'] = len(domain)
            for number, values in enumerate(domain):
                if record['engine_calls'] + len(record['run_ids']) > record['budget']:
                    break
                point = {'parameters': dict(zip((a['material'] for a in record['axes']), values)), 'runs': [], 'order': None, 'flipped': None}
                record['points'].append(point)
                for source_id in record['run_ids']:
                    if self.domain.view(source_id)['status'] != 'succeeded':
                        raise core.ValidationError('Source inputs became stale during search')
                    job = self.store.job(source_id)
                    _, path = self.domain.file_record(record['project_id'], job['evidence_snapshot']['idf']['source_file'])
                    model = path.read_text(encoding='utf-8-sig')
                    for material, value in point['parameters'].items():
                        model = set_conductivity(model, material, value)
                    search_root = self.store.root / 'searches' / record['search_id']
                    search_root.mkdir(parents=True, exist_ok=True)
                    model_path = search_root / f'{number}_{job["scheme_id"]}.idf'
                    model_path.write_text(model, encoding='utf-8')
                    case = {**job['case_snapshot'], 'schemes': [{'scheme_id': job['scheme_id'], 'name': job['scheme_id'], 'model': model_path.relative_to(self.store.root).as_posix(), 'cost': None}]}
                    rid = 'run_' + uuid.uuid4().hex
                    rd = search_root / rid
                    record['engine_calls'] += 1
                    save()
                    result = core.run_simulation(record['project_id'], job['scheme_id'], job['factor_profile_id'], rd,
                        case_override=case, profile_override=job['factor_snapshot'], file_root=self.store.root)
                    checked, manifest, _ = core.read_validated(rd, check_current=False)
                    if result['status'] != 'succeeded' or checked['status'] != 'succeeded':
                        raise core.ValidationError('Search simulation failed: ' + rid)
                    if abs(result['metrics']['area_m2'] - job['project_snapshot']['building']['area_m2']) > .1:
                        raise core.ValidationError('Search model area mismatch')
                    point['runs'].append({'run_id': rid, 'scheme_id': job['scheme_id'], 'metrics': result['metrics'], 'manifest_hash': core.sha(rd / 'manifest.json'), 'warnings': manifest.get('warnings')})
                    save()
                point['order'] = [r['scheme_id'] for r in sorted(point['runs'], key=lambda r: r['metrics']['annual_energy_kwh'])]
                energies = sorted(r['metrics']['annual_energy_kwh'] for r in point['runs'])
                point['indeterminate'] = any(b - a <= record['ranking_tolerance_kwh'] for a, b in zip(energies, energies[1:]))
                point['flipped'] = None if point['indeterminate'] else point['order'] != record['reference_order']
                save()
            record.update(status='succeeded', searched_points=len(record['points']), coverage=len(record['points']) / len(domain),
                stability_status=stability_status(record['points'], len(domain)),
                limitation='仅适用于声明的离散点、全年场地能耗目标和当前输入；不证明连续区间稳定，不等于综合最优。')
        except Exception as exc:
            record.update(status='failed', stability_status='SIMULATION_FAILED', error=str(exc)[:1200])
        finally:
            record['finished_at'] = core.now()
            save()
            self.capacity.release()

    def view(self, project_id, search_id):
        record = self.store.get('search', search_id)
        if record['project_id'] != project_id:
            raise core.ValidationError('Cross-project search rejected')
        if record.get('search_code_hash') != core.sha(Path(__file__)) or any(self.domain.view(r)['status'] != 'succeeded' for r in record['run_ids']):
            return {**record, 'status': 'stale', 'stability_status': 'STALE'}
        for point in record['points']:
            for run in point['runs']:
                rd = self.store.root / 'searches' / search_id / run['run_id']
                checked, _, _ = core.read_validated(rd, check_current=False)
                if core.sha(rd / 'manifest.json') != run['manifest_hash']:
                    raise core.ValidationError('Search manifest changed')
                if checked['metrics'] != run['metrics'] or checked['scheme_id'] != run['scheme_id']:
                    raise core.ValidationError('Search summary does not match verified SQL result')
        return record

    def actions(self, project_id, search_id, body):
        study = self.view(project_id, search_id)
        if study['status'] != 'succeeded':
            raise core.ValidationError('Evidence planning requires a completed current search')
        flipped = [p for p in study['points'] if p['flipped']]
        ranked = []
        for action in body.actions:
            axis = next((a for a in study['axes'] if a['material'] == action.material), None)
            if not axis or action.confirmed_value not in axis['values']:
                raise core.ValidationError('Hypothetical confirmation must match a tested domain value')
            eliminated = sum(p['parameters'][action.material] != action.confirmed_value for p in flipped)
            # Conditional scenario pruning, explicitly not a probabilistic value-of-information estimate.
            reduction = eliminated / len(flipped) if flipped else None
            ranked.append({**action.model_dump(), 'excluded_observed_counterexamples': eliminated,
                'conditional_reduction_fraction': reduction, 'reduction_per_cny': reduction / action.cost_cny if action.cost_cny and reduction is not None else None,
                'free_action': action.cost_cny == 0, 'assumption': '假设测量恰好确认该离散值；不计测量误差。不是已完成补测或真实风险概率。'})
        ranked.sort(key=lambda a: (a['free_action'] and bool(a['conditional_reduction_fraction']), a['reduction_per_cny'] or 0), reverse=True)
        return self.store.put('actionplan', {'actionplan_id': 'actionplan_' + uuid.uuid4().hex,
            'project_id': project_id, 'search_id': search_id, 'search_revision': study['revision'], 'timestamp': core.now(),
            'actions': ranked, 'observed_counterexamples': len(flipped), 'scope': '已搜索反例的条件排除率 / 用户填报成本；无反例时不虚构收益'})
