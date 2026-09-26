"""Generate material scenarios, evaluate real EnergyPlus outputs and explain tradeoffs."""
import threading
import uuid
import inspect
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from . import core
from .materials import Materials, evidence_changes, evidence_snapshot, gap_text
from .robustness import objects
from .schema import Contract
from .trust import Trust


Objective = Literal['energy_kwh', 'cost_cny', 'cooling_unmet_h', 'carbon_kg']
TOLERANCES = {'energy_kwh': .01, 'cost_cny': .01, 'cooling_unmet_h': .01, 'carbon_kg': .01}
COMFORT = {'cooling_unmet_h': 'Time Setpoint Not Met During Occupied Cooling / Facility',
           'heating_unmet_h': 'Time Setpoint Not Met During Occupied Heating / Facility'}


def study_version():
    return core.hash_json({'study': core.sha(Path(__file__)), 'materials': core.sha(Path(__file__).with_name('materials.py')),
                           'idf_parser': inspect.getsource(objects)})


class Option(Contract):
    option_id: str = Field(pattern=r'^[A-Za-z][A-Za-z0-9_-]{0,39}$')
    name: str = Field(min_length=1, max_length=160)
    material_id: str
    thickness_m: float = Field(ge=.003, le=2, strict=True)
    cost_cny: float | None = Field(default=None, ge=0, le=1000000000, strict=True)
    cost_evidence_id: str | None = None
    cost_scope: str | None = Field(default=None, max_length=2000)

    @model_validator(mode='after')
    def cost_source(self):
        if self.option_id.lower() == 'baseline':
            raise ValueError('baseline is reserved')
        if self.cost_cny is not None and (not self.cost_evidence_id or not self.cost_scope or len(self.cost_scope) < 5):
            raise ValueError('费用需要已复核的来源证据与明确的增量造价范围')
        return self


class Constraints(Contract):
    max_cost_cny: float | None = Field(default=None, ge=0, le=1000000000, strict=True)
    max_cooling_unmet_h: float | None = Field(default=None, ge=0, le=8784, strict=True)
    max_heating_unmet_h: float | None = Field(default=None, ge=0, le=8784, strict=True)
    min_energy_saving_pct: float | None = Field(default=None, ge=0, le=100, strict=True)


class StudyCreate(Contract):
    source_run_id: str
    target_material: str = Field(min_length=1, max_length=160)
    options: list[Option] = Field(min_length=1, max_length=12)
    objectives: list[Objective] = Field(default_factory=lambda: ['energy_kwh', 'cost_cny'], min_length=1, max_length=4)
    constraints: Constraints = Field(default_factory=Constraints)
    budget: int = Field(ge=1, le=12, strict=True)
    basis: str = Field(min_length=5, max_length=2000)

    @model_validator(mode='after')
    def unique(self):
        if len({o.option_id.lower() for o in self.options}) != len(self.options) or len(set(self.objectives)) != len(self.objectives):
            raise ValueError('Duplicate options or objectives')
        return self


def material_catalog(model):
    parsed = objects(model)
    result = []
    for material in parsed:
        if material[0].lower() != 'material' or len(material) < 7:
            continue
        constructions = [o[1] for o in parsed if o[0].lower() == 'construction'
                         and material[1].lower() in [v.lower() for v in o[2:]]]
        surfaces = [{'name': o[1], 'type': o[2], 'construction': o[3], 'zone': o[4]} for o in parsed
                    if o[0].lower() == 'buildingsurface:detailed' and len(o) > 4
                    and o[3].lower() in {c.lower() for c in constructions}]
        special = any(o[0].lower().startswith('materialproperty:') and len(o) > 1
                      and o[1].lower() == material[1].lower() for o in parsed)
        result.append({'name': material[1], 'thickness_m': float(material[3]), 'conductivity_w_mk': float(material[4]),
                       'density_kg_m3': float(material[5]), 'specific_heat_j_kgk': float(material[6]),
                       'constructions': constructions, 'surfaces': surfaces,
                       'supported': bool(surfaces) and not special,
                       'limitation': '保留原粗糙度和吸收率；特殊 MaterialProperty 与未映射表面不自动替换'})
    return result


def replace_material(model, target, card, thickness):
    parsed = objects(model)
    matches = [o for o in parsed if o[0].lower() == 'material' and o[1].lower() == target.lower()]
    if len(matches) != 1 or len(matches[0]) < 7:
        raise core.ValidationError('Material missing or ambiguous')
    obj = matches[0]
    before = obj.copy()
    obj[3:7] = [str(v) for v in (thickness, card['conductivity_w_mk'], card['density_kg_m3'], card['specific_heat_j_kgk'])]
    return '\n\n'.join(',\n  '.join(o) + ';' for o in parsed), {'object': target, 'before': before, 'after': obj.copy()}


def assess(points, baseline_energy, objectives, constraints, profile, region):
    """Deterministic constraint/Pareto analysis; missing values cannot win."""
    rows = []
    for point in points:
        metrics = point.get('metrics') or {}
        carbon = core.calculate_carbon(metrics['energy_by_carrier_kwh'], profile, region) if metrics else None
        values = {'energy_kwh': metrics.get('annual_energy_kwh'), 'cost_cny': point.get('cost_cny'),
                  'carbon_kg': (carbon or {}).get('operating_carbon_kg')}
        values.update({key: metrics.get('comfort_hours', {}).get(locator) for key, locator in COMFORT.items()})
        savings = 100 * (baseline_energy - values['energy_kwh']) / baseline_energy if values['energy_kwh'] is not None else None
        missing = [key for key in objectives if values.get(key) is None]
        violations = []
        for field, key in [('max_cost_cny', 'cost_cny'), ('max_cooling_unmet_h', 'cooling_unmet_h'), ('max_heating_unmet_h', 'heating_unmet_h')]:
            bound = constraints[field]
            if bound is not None:
                if values[key] is None:
                    missing.append(key)
                elif values[key] > bound:
                    violations.append({'constraint': field, 'actual': values[key], 'limit': bound})
        if constraints['min_energy_saving_pct'] is not None:
            if savings is None:
                missing.append('energy_kwh')
            elif savings < constraints['min_energy_saving_pct']:
                violations.append({'constraint': 'min_energy_saving_pct', 'actual': savings, 'limit': constraints['min_energy_saving_pct']})
        status = 'FAILED' if point['status'] != 'succeeded' else 'INCOMPLETE' if missing else 'EXCLUDED' if violations else 'FEASIBLE'
        rows.append({'option_id': point['option_id'], 'name': point['name'], 'run_id': point.get('run_id'),
                     'status': status, 'values': values, 'energy_saving_pct': savings, 'carbon': carbon,
                     'missing': sorted(set(missing)), 'violations': violations, 'dominated_by': [],
                     'source_nature': point.get('source_nature'), 'cost_source_nature': point.get('cost_source_nature'),
                     'warnings': point.get('warnings')})
    feasible = [row for row in rows if row['status'] == 'FEASIBLE']
    for row in feasible:
        for other in feasible:
            if other is row:
                continue
            if all(other['values'][key] <= row['values'][key] for key in objectives) and any(
                other['values'][key] < row['values'][key] - TOLERANCES[key] for key in objectives
            ):
                row['dominated_by'].append(other['option_id'])
    frontier = [r['option_id'] for r in feasible if not r['dominated_by']]
    return {'rows': rows, 'pareto_option_ids': frontier, 'objectives': objectives,
            'constraints': constraints, 'tolerances': {k: TOLERANCES[k] for k in objectives},
            'status': 'CANDIDATES_FOR_REVIEW' if frontier else 'NO_ELIGIBLE_CANDIDATE',
            'explanation': '候选集内没有在全部所选目标上更优的可行方案；这不是全局最优或工程批准。',
            'factor_snapshot': profile, 'factor_hash': core.hash_json(profile), 'generated_at': core.now()}


class Decisions:
    def __init__(self, domain):
        self.domain, self.store = domain, domain.store
        self.materials = Materials(domain)
        self.capacity = threading.BoundedSemaphore(1)

    def recover(self):
        for record in self.store.list('study'):
            if record['status'] == 'running':
                self.store.put('study', {**record, 'status': 'failed', 'error': '进程中断；已保留输出，请新建研究'}, record['revision'])

    def catalog(self, project_id, run_id):
        job = self.store.job(run_id)
        if job['project_id'] != project_id:
            raise core.ValidationError('Cross-project source run rejected')
        _, path = self.domain.file_record(project_id, job['evidence_snapshot']['idf']['source_file'])
        return material_catalog(path.read_text(encoding='utf-8-sig'))

    def start(self, project_id, body, *, background=True):
        source = self.domain.view(body.source_run_id)
        if source['project_id'] != project_id or source['status'] != 'succeeded' or source['scheme_id'] != 'baseline':
            raise core.ValidationError('请先完成当前项目 baseline 的有效仿真')
        matched = [m for m in self.catalog(project_id, body.source_run_id) if m['name'].lower() == body.target_material.lower()]
        if len(matched) != 1 or not matched[0]['supported']:
            raise core.ValidationError('请选择唯一、已映射表面且不含特殊 MaterialProperty 的现有材料层')
        material_snapshots, cost_snapshots = {}, {}
        for option in body.options:
            card = self.materials.get(project_id, option.material_id)
            if not card['can_simulate']:
                raise core.ValidationError('材料不能进入仿真：' + card['name'])
            material_snapshots[option.material_id] = self.store.get('material', option.material_id)
            if option.cost_evidence_id:
                cost_snapshots[option.cost_evidence_id] = evidence_snapshot(self.domain, project_id, option.cost_evidence_id)
        job = self.store.job(body.source_run_id)
        if not self.capacity.acquire(blocking=False):
            raise core.ValidationError('已有方案研究正在运行')
        try:
            record = self.store.put('study', {'study_id': 'study_' + uuid.uuid4().hex, 'project_id': project_id,
                **body.model_dump(), 'status': 'running', 'created_at': core.now(), 'error': None, 'engine_calls': 0,
                'material_snapshots': material_snapshots, 'cost_snapshots': cost_snapshots,
                'source_provenance': source['provenance'], 'source_metrics': source['metrics'],
                'mapping': matched[0], 'study_code_hash': study_version(),
                'factor_snapshot': Trust(self.domain).current_profile(job), 'assessment': None,
                'points': [{'option_id': 'baseline', 'name': '维持现状', 'run_id': body.source_run_id, 'status': 'succeeded',
                            'metrics': source['metrics'], 'cost_cny': 0, 'source_nature': source['data_nature'],
                            'cost_source_nature': '维持现状的改造增量为 0', 'warnings': source['warnings_count']}],
                'limitations': ['只替换所选 Material 对象的厚度、导热系数、密度、比热；其全部关联表面一起变化。',
                                '粗糙度、光学吸收率、其他构造、HVAC 和运行时段沿用基准；不推断稀土机理或实测优势。',
                                '费用为用户声明的增量初始造价，维持现状为 0；不包含运行费用、贴现或生命周期收益。',
                                '舒适性指标分别来自原生 SQL Facility 汇总，不相加为总时长，不自动判定规范合格。',
                                '只比较已提交且已完成的候选集；材料实测、施工适用性、模型校准与工程签署仍需复核。']})
        except Exception:
            self.capacity.release()
            raise
        if background:
            threading.Thread(target=self.execute, args=(record,), daemon=True, name='vra-material-study').start()
        else:
            self.execute(record)
        return self.store.get('study', record['study_id'])

    def stale_reasons(self, record):
        reasons = []
        source = self.domain.view(record['source_run_id'])
        if source['status'] != 'succeeded' or source['provenance'] != record['source_provenance'] or source['metrics'] != record['source_metrics']:
            reasons.append('基准仿真或证据已变化')
        if record['study_code_hash'] != study_version():
            reasons.append('方案生成或评估代码版本变化')
        for mid, snapshot in record['material_snapshots'].items():
            try:
                if self.store.get('material', mid) != snapshot or not self.materials.get(record['project_id'], mid)['can_simulate']:
                    reasons.append('材料参数或来源变化：' + snapshot['name'])
            except (KeyError, OSError, core.ValidationError):
                reasons.append('材料记录缺失：' + mid)
        return reasons + evidence_changes(self.domain, record['project_id'], record['cost_snapshots'].values())

    def execute(self, record):
        def save():
            nonlocal record
            record = self.store.put('study', record, record['revision'])
        try:
            job = self.store.job(record['source_run_id'])
            _, source_path = self.domain.file_record(record['project_id'], job['evidence_snapshot']['idf']['source_file'])
            model = source_path.read_text(encoding='utf-8-sig')
            root = self.store.root / 'studies' / record['study_id']
            root.mkdir(parents=True, exist_ok=False)
            core.write_json(root / 'study-input.json', record)
            for option in record['options'][:record['budget']]:
                if self.stale_reasons(record):
                    raise core.ValidationError('研究输入已变化，请复核并新建研究')
                card = record['material_snapshots'][option['material_id']]
                altered, change = replace_material(model, record['target_material'], card, option['thickness_m'])
                path = root / (option['option_id'] + '.idf')
                path.write_text(altered, encoding='utf-8')
                case = {**job['case_snapshot'], 'schemes': [{'scheme_id': option['option_id'], 'name': option['name'],
                        'model': path.relative_to(self.store.root).as_posix(), 'cost': None}]}
                rid = 'run_' + uuid.uuid4().hex
                point = {**option, 'run_id': rid, 'status': 'running', 'metrics': None, 'error': None, 'change': change,
                         'cost_source_nature': record['cost_snapshots'].get(option['cost_evidence_id'], {}).get('status'),
                         'source_nature': self.materials.get(record['project_id'], option['material_id'])['source_nature']}
                record['points'].append(point)
                save()
                # Refresh the local reference after Store.put has copied the outer record.
                point = record['points'][-1]
                result = core.run_simulation(record['project_id'], option['option_id'], record['factor_snapshot']['profile_id'], root / rid,
                    case_override=case, profile_override=record['factor_snapshot'], file_root=self.store.root)
                checked, manifest, _ = core.read_validated(root / rid, check_current=False)
                record['engine_calls'] += manifest['engine_calls_executed']
                point['manifest_hash'] = core.sha(root / rid / 'manifest.json')
                point['warnings'] = manifest.get('warnings')
                point['status'] = 'failed'
                if result['status'] == checked['status'] == 'succeeded':
                    if abs(checked['metrics']['area_m2'] - record['source_metrics']['area_m2']) <= .1:
                        point.update(status='succeeded', metrics=checked['metrics'])
                    else:
                        point['error'] = '材料方案改变了建筑面积；结果拒绝'
                else:
                    point['error'] = (result.get('error') or {}).get('message', '原生结果核验失败')
                save()
            if self.stale_reasons(record):
                raise core.ValidationError('研究过程中证据变化，不能发布当前候选结论')
            record['status'] = 'succeeded'
            record['assessment'] = self.assessment(record)
        except Exception as exc:
            record.update(status='failed', error=str(exc)[:1200], assessment=None)
        finally:
            record['finished_at'] = core.now()
            save()
            self.capacity.release()

    def assessment(self, record):
        job = self.store.job(record['source_run_id'])
        value = assess(record['points'], record['source_metrics']['annual_energy_kwh'], record['objectives'], record['constraints'],
                       Trust(self.domain).current_profile(job), job['project_snapshot']['building']['region'])
        attempted = len(record['points']) - 1
        value.update(attempted_options=attempted, total_options=len(record['options']),
                     evaluated_options=sum(p['status'] == 'succeeded' for p in record['points'][1:]),
                     coverage=attempted / len(record['options']), untested_options=[o['option_id'] for o in record['options'][attempted:]],
                     energyplus_calls_for_assessment=0)
        return value

    def view(self, project_id, study_id):
        record = self.store.get('study', study_id)
        if record['project_id'] != project_id:
            raise core.ValidationError('Cross-project study rejected')
        reasons = self.stale_reasons(record)
        for point in record['points'][1:]:
            if 'manifest_hash' not in point:
                continue
            try:
                rd = self.store.root / 'studies' / study_id / point['run_id']
                result, manifest, _ = core.read_validated(rd, check_current=False)
                if core.sha(rd / 'manifest.json') != point['manifest_hash'] or result['scheme_id'] != point['option_id']:
                    raise core.ValidationError('Run binding changed')
                if point['status'] == 'succeeded' and (result['status'] != 'succeeded' or result['metrics'] != point['metrics']):
                    raise core.ValidationError('SQL summary changed')
            except (KeyError, OSError, core.ValidationError):
                reasons.append('方案原始输出损坏：' + point['name'])
        if reasons:
            return {**record, 'status': 'stale', 'stale_reasons': reasons, 'assessment': None,
                    'points': [{**p, 'metrics': None} for p in record['points']]}
        assessment = record['assessment']
        current = Trust(self.domain).current_profile(self.store.job(record['source_run_id']))
        factor_changed = assessment and assessment['factor_hash'] != core.hash_json(current)
        return {**record, 'assessment': None if factor_changed else assessment, 'assessment_stale': bool(factor_changed)}

    def reevaluate(self, project_id, study_id):
        view = self.view(project_id, study_id)
        if view['status'] != 'succeeded':
            raise core.ValidationError('只能重新评估当前有效的已完成研究')
        record = self.store.get('study', study_id)
        record['assessment'] = self.assessment(record)
        self.store.put('study', record, record['revision'])
        return self.view(project_id, study_id)

    def report(self, project_id, study_id):
        study = self.view(project_id, study_id)
        return {'schema_version': 'vra.decision-study.v1', 'generated_at': core.now(),
                'project': self.store.get('project', project_id), 'study': study,
                'certificate': {'status': (study['assessment'] or {}).get('status', study['status'].upper()),
                                'candidate_option_ids': (study['assessment'] or {}).get('pareto_option_ids'),
                                'current_recommendation': None, 'engineer_review': 'UNSIGNED',
                                'scope': '已声明材料候选集、用户约束和目标下的可行非支配集',
                                'conditions': study['limitations']},
                'diagnosis': self.diagnosis(project_id, include_studies=False)}

    def diagnosis(self, project_id, *, include_studies=True):
        project = self.store.get('project', project_id)
        evidence = self.store.list('evidence', project_id)
        gate = self.domain.gate(project_id)
        cards = self.materials.list(project_id)
        tasks = []
        def task(key, priority, title, action, target, evidence_ids=None):
            tasks.append({'task_key': key, 'priority': priority, 'title': title, 'action': action,
                          'target_view': target, 'evidence_ids': evidence_ids or []})
        for gap in gate['blockers']:
            task(gap['code'] + ':' + gap['field'], 1, gap['message'], gap['action'], 'evidence')
        for field, title in [('envelope', '围护结构与残图构造'), ('hvac', '设备台账与系统'), ('schedules', '运行时段与负荷')]:
            if not project['building'].get(field):
                task('building:' + field, 2, '核对' + title, '补充现场或授权资料并修订建筑声明；核对 IDF 对象，不自动用默认值填补。', 'evidence')
        for kind, title in [('drawing', '图纸、测量与构件定位'), ('bill', '能耗账单与模型校准')]:
            valid = []
            for ev in evidence:
                if ev['type'] == kind:
                    try:
                        checked = evidence_snapshot(self.domain, project_id, ev['evidence_id'])
                        if checked['status'] != 'ASSUMED':
                            valid.append(checked)
                    except (KeyError, OSError, core.ValidationError):
                        pass
            if not valid:
                task('evidence:' + kind, 2, '补充并复核' + title, '登记来源、测量/账单范围和版本；复核后本任务自动更新。', 'spatial' if kind == 'drawing' else 'evidence')
        if not cards:
            task('material:new', 2, '登记候选材料与热工参数', '填写检测定位、测试条件和适用范围；经复核后生成材料方案。', 'decision')
        for card in cards:
            if not card['can_simulate']:
                task('material:' + card['material_id'], 1, card['name'] + ' 尚不能生成方案',
                     '补齐或复核：' + '、'.join(card['stale_reasons'] or [gap_text(g) for g in card['simulation_gaps']]), 'decision', [e['evidence_id'] for e in card['evidence_snapshot']])
            if card['validation_gaps']:
                task('validation:' + card['material_id'], 3, card['name'] + ' 实测验证链待补齐',
                     '核对批次、热工测试、同色/同工况对照与老化：' + '、'.join(gap_text(g) for g in card['validation_gaps']), 'decision')
        runs = [self.domain.view(j['run_id']) for j in self.store.jobs(project_id)[:12]]
        latest_baseline = next((r for r in runs if r['scheme_id'] == 'baseline'), None)
        if not latest_baseline or latest_baseline['status'] != 'succeeded':
            task('run:baseline', 1 if gate['can_simulate'] else 2, '建立当前有效基准仿真', '完成输入复核后运行 baseline，用作材料方案的同题比较基准。', 'simulation')
        if any(r.get('warnings_count') for r in runs if r['status'] == 'succeeded'):
            task('run:warnings', 2, '复核仿真 Warning 与未达设定点时间', '查看原始 ERR 和 SQL；程序成功不等于 HVAC 设定适用于建筑。', 'trace')
        studies = [self.view(project_id, s['study_id']) for s in self.store.list('study', project_id)[:5]] if include_studies else []
        latest = studies[0] if studies else None
        current = latest if latest and latest['status'] == 'succeeded' and latest['assessment'] else None
        if include_studies and not current:
            task('study:new', 2, '比较材料方案与工程约束', '指定改造材料层、候选厚度、造价来源、预算和舒适性上限，运行真实方案研究。', 'decision')
        tasks.sort(key=lambda t: (t['priority'], t['task_key']))
        return {'project_id': project_id, 'generated_at': core.now(), 'can_simulate': gate['can_simulate'],
                'tasks': tasks, 'materials': cards, 'latest_study_status': latest['status'] if latest else None,
                'current_study_id': current['study_id'] if current else None,
                'current_assessment': current['assessment'] if current else None,
                'next_step': tasks[0] if tasks else None,
                'priority_basis': '1=阻断当前计算；2=影响方案判断；3=材料性能与工程外推验证。未估计补证概率或虚构费用。'}
