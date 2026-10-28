"""Source-bound operating-point fits. Never certify a plant or alter an IDF."""
import itertools
import math
from collections import Counter
from typing import Literal

import numpy as np
from fastapi import Request
from pydantic import Field, StrictInt

from . import core
from .domain import identifier
from .measurements import csv_reader, errors, timestamp
from .schema import Contract


class PlantFit(Contract):
    file_id: str
    building_ref: str = Field(min_length=1, max_length=200)
    equipment_ref: str = Field(min_length=1, max_length=200)
    boundary: Literal['chiller_electricity', 'chiller_train_electricity', 'plant_electricity']
    source_nature: Literal['field_processed', 'field_raw', 'laboratory', 'simulation']
    source_note: str = Field(min_length=20, max_length=4000)
    timestamp_column: str = Field(min_length=1, max_length=200)
    power_column: str = Field(min_length=1, max_length=200)
    cooling_column: str = Field(min_length=1, max_length=200)
    flow_column: str = Field(min_length=1, max_length=200)
    return_temperature_column: str = Field(min_length=1, max_length=200)
    supply_temperature_column: str = Field(min_length=1, max_length=200)
    condenser_temperature_column: str = Field(min_length=1, max_length=200)
    power_unit: Literal['W', 'kW']
    cooling_unit: Literal['W', 'kW', 'refrigeration_ton']
    flow_unit: Literal['m3/s', 'm3/h', 'L/s', 'US_gpm']
    temperature_unit: Literal['K', 'C', 'F']
    utc_offset_minutes: StrictInt | None = Field(default=None, ge=-720, le=840)
    interval_seconds: StrictInt = Field(ge=60, le=86400)
    # Required engineering assumptions, recorded rather than silently defaulted.
    fluid_density_kg_m3: float = Field(ge=900, le=1300)
    fluid_heat_capacity_j_kgk: float = Field(ge=2000, le=4500)
    balance_tolerance_percent: float = Field(gt=0, le=30)
    holdout_start: str = Field(min_length=10, max_length=50)


def nonnegative_fit(x, y):
    """Exact small (four-column) NNLS by enumerating the 16 active sets."""
    best = None
    for width in range(1, x.shape[1] + 1):
        for active in itertools.combinations(range(x.shape[1]), width):
            values, _, rank, _ = np.linalg.lstsq(x[:, active], y, rcond=None)
            if rank != width or np.any(values < 0):
                continue
            beta = np.zeros(x.shape[1])
            beta[list(active)] = values
            score = float(np.sum((x @ beta - y)**2))
            if best is None or score < best[0]:
                best = score, beta
    if best is None:
        raise core.ValidationError('工况无法拟合非负功率模型')
    return best[1]


def analyze_plant(path, options):
    reader = csv_reader(path)
    columns = {key: getattr(options, key+'_column') for key in (
        'timestamp', 'power', 'cooling', 'flow', 'return_temperature',
        'supply_temperature', 'condenser_temperature')}
    if len(set(columns.values())) != len(columns):
        raise core.ValidationError('校准字段必须使用不同的原件列')
    if not set(columns.values()) <= set(reader.fieldnames):
        raise core.ValidationError('校准字段不存在，请核对原件表头')
    try:
        cutoff = timestamp(options.holdout_start)
    except ValueError as exc:
        raise core.ValidationError('留出期起点必须包含UTC偏移') from exc
    power_scale = {'W': .001, 'kW': 1}[options.power_unit]
    cooling_scale = {'W': .001, 'kW': 1, 'refrigeration_ton': 3.516852842}[options.cooling_unit]
    flow_scale = {'m3/s': 1, 'm3/h': 1/3600, 'L/s': .001, 'US_gpm': .003785411784/60}[options.flow_unit]
    def celsius(value):
        return value-273.15 if options.temperature_unit == 'K' else (
            (value-32)*5/9 if options.temperature_unit == 'F' else value)
    records, issues, dates = [], Counter(), []
    for index, row in enumerate(reader, 2):
        if index > 100001:
            raise core.ValidationError('超过100000行，未截断拟合')
        item = {'row': index, 'flags': [], 'timestamp': None}
        if None in row or any(v is None for v in row.values()):
            item['flags'].append('malformed_csv_row')
        try:
            instant = timestamp(row[columns['timestamp']] or '', options.utc_offset_minutes)
            item['timestamp'] = instant.isoformat()
            dates.append(instant)
        except (ValueError, TypeError):
            item['flags'].append('invalid_or_ambiguous_timestamp')
        try:
            v = {key: float(row[name]) for key, name in columns.items() if key != 'timestamp'}
            if not all(math.isfinite(a) for a in v.values()):
                raise ValueError('nonfinite')
            p, q, flow = v['power']*power_scale, v['cooling']*cooling_scale, v['flow']*flow_scale
            ret, supply, cond = [celsius(v[key]) for key in ('return_temperature', 'supply_temperature', 'condenser_temperature')]
            lift = cond-supply
            if not 0 <= p <= 1e7 or not 0 <= q <= 1e8 or not 0 <= flow <= 1000 or not all(-20 <= a <= 90 for a in (ret, supply, cond)):
                item['flags'].append('invalid_physical_range')
            elif p == 0 or q == 0 or flow == 0:
                item['flags'].append('inactive_or_zero_measurement')
            elif not 0 < lift <= 80 or ret <= supply:
                item['flags'].append('invalid_temperature_direction')
            else:
                heat = flow*options.fluid_density_kg_m3*options.fluid_heat_capacity_j_kgk*(ret-supply)/1000
                item.update(power_kw=p, cooling_kw=q, lift_k=lift,
                            water_heat_kw=heat, balance_error_percent=100*abs(heat-q)/q)
        except (ValueError, TypeError, KeyError):
            item['flags'].append('missing_or_nonnumeric_measurement')
        issues.update(item['flags'])
        records.append(item)
    if not records:
        raise core.ValidationError('CSV无工况记录')
    counts = Counter(dates)
    duplicates = sum(v-1 for v in counts.values())
    descending = sum(b < a for a, b in zip(dates, dates[1:]))
    gaps, off_grid = 0, 0
    for a, b in zip(sorted(counts), sorted(counts)[1:]):
        steps = (b-a).total_seconds()/options.interval_seconds
        if abs(steps-round(steps)) > 1e-8:
            off_grid += 1
        else:
            gaps += max(0, round(steps)-1)
    issues.update({k: v for k, v in {'duplicate_timestamps': duplicates, 'out_of_order': descending,
                                  'absent_intervals': gaps, 'off_interval_grid': off_grid}.items() if v})
    valid = [r for r in records if not r['flags']]
    bad_balance = sum(r['balance_error_percent'] > options.balance_tolerance_percent for r in valid)
    blockers = []
    if duplicates or descending or any(r['timestamp'] is None for r in records):
        blockers.append('时间无效、重复或乱序，拒绝工况拟合')
    if bad_balance:
        blockers.append(f'{bad_balance}个有效工况的水侧冷量不满足声明误差预算；不得自动更改单位或乘60')
    if any(r['flags'] and r['flags'] != ['inactive_or_zero_measurement'] for r in records):
        blockers.append('存在损坏或无效观测；拟合仅供诊断，须提供有依据的修订原件')
    train = [r for r in valid if timestamp(r['timestamp']) < cutoff]
    holdout = [r for r in valid if timestamp(r['timestamp']) >= cutoff]
    result = {'rows': len(records), 'valid_operating_rows': len(valid), 'excluded_rows': len(records)-len(valid),
              'issues': dict(issues), 'imputed_rows': 0, 'balance_failed_rows': bad_balance,
              'balance_error_median_percent': float(np.median([r['balance_error_percent'] for r in valid])) if valid else None,
              'blockers': blockers, 'fit': None, 'status': 'blocked', 'calibrated': False,
              'scope': 'Operating-point electric power fit only; not annual energy, sensor certification, native EnergyPlus calibration, or site acceptance.'}
    if len(train) < 40 or len(holdout) < 20:
        blockers.append('至少40个训练工况、20个按时间留出的工况；不复制样本补足')
        return result, records
    if duplicates or descending or any(r['timestamp'] is None for r in records):
        return result, records
    def matrix(rows):
        q = np.array([r['cooling_kw']/1000 for r in rows])
        lift = np.array([r['lift_k']/10 for r in rows])
        return np.column_stack([np.ones(len(rows)), q, q*q, q*lift])
    x = matrix(train)
    condition = float(np.linalg.cond(x))
    if np.linalg.matrix_rank(x) < 4 or not math.isfinite(condition) or condition > 1e8:
        blockers.append('训练工况无法辨识4个参数，拒绝不稳定拟合')
        return result, records
    beta = nonnegative_fit(x, np.array([r['power_kw'] for r in train]))
    domains = {key: [min(r[key] for r in train), max(r[key] for r in train)] for key in ('cooling_kw', 'lift_k')}
    outside = sum(any(not low <= r[key] <= high for key, (low, high) in domains.items()) for r in holdout)
    for rows in (train, holdout):
        for r, predicted in zip(rows, matrix(rows) @ beta):
            r['predicted_power_kw'] = float(predicted)
            r['partition'] = 'training' if rows is train else 'holdout'
    result['fit'] = {'formula': 'P_kW = b0 + b1*q + b2*q² + b3*q*lift; q=Q_kW/1000, lift=(T_cond_in_C-T_supply_C)/10',
        'coefficients': beta.tolist(), 'parameter_count': 4, 'condition_number': condition,
        'training_domain': domains, 'holdout_outside_training_domain': outside,
        'training': errors([(r['power_kw'], r['predicted_power_kw']) for r in train], 4),
        'holdout': errors([(r['power_kw'], r['predicted_power_kw']) for r in holdout])}
    # The generic series metric helper's sums are not energy for instantaneous samples.
    for key in ('training', 'holdout'):
        m = result['fit'][key]
        m['measured_sample_sum_kw'] = m.pop('measured_kwh')
        m['predicted_sample_sum_kw'] = m.pop('predicted_kwh')
    result['status'] = 'blocked' if blockers else 'candidate_requires_engineer_review'
    result['warnings'] = ['同一设备时间留出不等于跨建筑泛化；相邻工况可能自相关。',
                          '系数不直接对应EnergyPlus冷机性能曲线，未写入原生模型。']
    if gaps:
        result['warnings'].append('原时段有缺口，仅评价实际记录工况，不外推完整时段能耗。')
    if outside:
        result['warnings'].append('留出期含训练域外工况，已保留全部误差。')
    return result, records


class PlantCalibrations:
    def __init__(self, domain):
        self.domain, self.store = domain, domain.store

    def create(self, pid, options, actor):
        source, path = self.domain.file_record(pid, options.file_id)
        result, rows = analyze_plant(path, options)
        if core.sha(path) != source['hash']:
            raise core.ValidationError('拟合期间原件改变，未保存')
        # No raw rows in SQL summaries. Reconstruct the audit table from the same immutable source.
        return self.store.put('calibration', {'calibration_id': identifier('calibration'), 'project_id': pid,
            'actor': actor, 'created_at': core.now(), 'options': options.model_dump(),
            'source': {k: source[k] for k in ('file_id', 'hash', 'name')}, 'rules_hash': core.sha(__file__),
            'result': result})

    def get(self, pid, key):
        record = self.store.get('calibration', key)
        if record['project_id'] != pid:
            raise KeyError(key)
        source, path = self.domain.file_record(pid, record['source']['file_id'])
        if source['hash'] != record['source']['hash'] or core.sha(path) != source['hash'] or record['rules_hash'] != core.sha(__file__):
            raise core.ValidationError('原件或校准规则变化；保留旧记录，须新建拟合')
        return record, path


def register_plant_calibrations(app, domain):
    service = app.state.plant_calibrations = PlantCalibrations(domain)

    @app.get('/api/projects/{project_id}/calibrations')
    def history(project_id: str):
        return service.store.list('calibration', project_id)

    @app.post('/api/projects/{project_id}/calibrations', status_code=201)
    def create(project_id: str, body: PlantFit, request: Request):
        return service.create(project_id, body, request.state.user['id'])

    @app.get('/api/projects/{project_id}/calibrations/{calibration_id}')
    def detail(project_id: str, calibration_id: str):
        record, _ = service.get(project_id, calibration_id)
        return record

    @app.get('/api/projects/{project_id}/calibrations/{calibration_id}/rows')
    def rows(project_id: str, calibration_id: str, page: int = 1):
        if not 1 <= page <= 1000:
            raise core.ValidationError('页码超出1–1000')
        record, path = service.get(project_id, calibration_id)
        _, values = analyze_plant(path, PlantFit(**record['options']))
        return {'total': len(values), 'page': page, 'page_size': 100, 'items': values[(page-1)*100:page*100]}
