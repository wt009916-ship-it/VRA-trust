"""Project-bound measured series QA and chronological holdout comparisons.

Never impute a missing meter value, equate a whole-building meter to a chiller,
or label imported predictions as a calibrated native simulation.
"""
import csv
import io
import math
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import Field, StrictInt

from . import core
from .domain import identifier
from .schema import Contract


class SeriesImport(Contract):
    file_id: str
    building_ref: str = Field(min_length=1, max_length=200)
    meter_boundary: str = Field(min_length=3, max_length=300)
    quantity: Literal['electricity', 'gas', 'heating', 'cooling']
    role: Literal['observed', 'prediction']
    timestamp_column: str = Field(min_length=1, max_length=200)
    value_column: str = Field(min_length=1, max_length=200)
    unit: Literal['kWh', 'Wh', 'kW', 'W']
    interval_seconds: StrictInt = Field(ge=60, le=86400)
    # Required for naive timestamps. Offset-aware timestamps take precedence.
    utc_offset_minutes: StrictInt | None = Field(default=None, ge=-720, le=840)
    source_note: str = Field(min_length=10, max_length=2000)


class SeriesComparison(Contract):
    observed_id: str
    prediction_id: str
    holdout_start: str = Field(min_length=10, max_length=50)
    fitted_parameters: StrictInt = Field(default=0, ge=0, le=50)
    source_note: str = Field(min_length=10, max_length=2000)


def timestamp(value, offset=None):
    value = datetime.fromisoformat(value.strip().replace('Z', '+00:00'))
    if value.utcoffset() is None:
        if offset is None:
            raise ValueError('无时区时间须明确固定UTC偏移；不会猜测夏令时')
        value = value.replace(tzinfo=timezone(timedelta(minutes=offset)))
    return value.astimezone(timezone.utc)


class MeterCSVReader(csv.DictReader):
    def __next__(self):
        try:
            return super().__next__()
        except csv.Error as exc:
            raise core.ValidationError("计量CSV结构损坏或单个字段过长；请核对导出格式") from exc


def csv_reader(path):
    if path.suffix.lower() != '.csv' or path.stat().st_size > 20_000_000:
        raise core.ValidationError('计量输入须为20MB以内UTF-8 CSV；请按建筑/设备拆分')
    try:
        text = path.read_text(encoding='utf-8-sig')
    except UnicodeError as exc:
        raise core.ValidationError('计量CSV须使用UTF-8编码') from exc
    reader = MeterCSVReader(io.StringIO(text), strict=True)
    try:
        names = reader.fieldnames or []
    except csv.Error as exc:
        raise core.ValidationError('计量CSV表头结构损坏或字段过长') from exc
    if not names or any(not name.strip() for name in names) or len(names) > 500 or len(set(names)) != len(names):
        raise core.ValidationError('CSV列名为空、重复或超过500列')
    return reader


def analyze(path, options):
    reader = csv_reader(path)
    if options.timestamp_column not in reader.fieldnames or options.value_column not in reader.fieldnames:
        raise core.ValidationError('时间列或计量列不存在，请核对原件列名')
    records, issues, dates, valid = [], Counter(), [], []
    multiplier = {'kWh': 1., 'Wh': .001, 'kW': options.interval_seconds/3600,
                  'W': options.interval_seconds/3_600_000}[options.unit]
    for index, row in enumerate(reader, 2):
        if index > 100001:
            raise core.ValidationError('计量记录超过100000行；未截断分析')
        flags, instant, value = [], None, None
        if None in row or any(v is None for v in row.values()):
            flags.append('malformed_csv_row')
        raw_time = row.get(options.timestamp_column) or ''
        raw_value = row.get(options.value_column) or ''
        try:
            instant = timestamp(raw_time, options.utc_offset_minutes)
            dates.append(instant)
        except ValueError:
            flags.append('invalid_or_ambiguous_timestamp')
        if raw_value.strip().lower() in {'', 'na', 'nan', 'null', 'n/a'}:
            flags.append('missing_value')
        else:
            try:
                value = float(raw_value)
                if not math.isfinite(value) or value < 0:
                    flags.append('invalid_or_negative_consumption')
                else:
                    value *= multiplier
                    if not math.isfinite(value) or value > 1e12:
                        flags.append('energy_out_of_supported_range')
            except ValueError:
                flags.append('nonnumeric_value')
        issues.update(flags)
        item = {'row': index, 'timestamp': instant.isoformat() if instant else None,
                'energy_kwh': value if not flags else None, 'flags': flags}
        records.append(item)
        if not flags:
            valid.append(item)
    if not records:
        raise core.ValidationError('计量CSV无数据行')
    counts = Counter(dates)
    duplicates = sum(n-1 for n in counts.values())
    descending = sum(b < a for a, b in zip(dates, dates[1:]))
    unique = sorted(counts)
    missing_intervals, misaligned = 0, 0
    if unique:
        for a, b in zip(unique, unique[1:]):
            steps = (b-a).total_seconds()/options.interval_seconds
            if abs(steps-round(steps)) > 1e-8:
                misaligned += 1
            else:
                missing_intervals += max(0, round(steps)-1)
    issues.update({k:v for k,v in {'duplicate_timestamps':duplicates,'out_of_order':descending,
                                  'off_interval_grid':misaligned,'absent_intervals':missing_intervals}.items() if v})
    eligible = not issues and bool(valid)
    summary = {'rows': len(records), 'valid_rows': len(valid), 'issues': dict(issues),
        'start_utc': unique[0].isoformat() if unique else None,
        'end_utc': unique[-1].isoformat() if unique else None,
        'valid_observed_energy_kwh': sum(r['energy_kwh'] for r in valid) if not duplicates else None,
        'zero_readings': sum(r['energy_kwh'] == 0 for r in valid),
        'eligible_for_comparison': eligible, 'imputed_rows': 0, 'calibrated': False,
        'scope': 'User-declared series; QA does not certify sensor accuracy, meter boundary or source authenticity'}
    return summary, records


def errors(pairs, parameters=0):
    n = len(pairs)
    if n <= parameters or not n:
        raise core.ValidationError('对齐有效样本不足，不能计算误差指标')
    measured = sum(a for a, _ in pairs)
    if measured <= 0:
        raise core.ValidationError('实测均值为零，归一化误差无定义')
    mean = measured/n
    return {'n':n, 'degrees_of_freedom': n-parameters,
        'nmbe_percent': 100*sum(b-a for a,b in pairs)/((n-parameters)*mean),
        'cvrmse_percent': 100*math.sqrt(sum((b-a)**2 for a,b in pairs)/(n-parameters))/mean,
        'measured_kwh': measured, 'predicted_kwh': sum(b for _,b in pairs),
        'sign_convention': 'prediction minus measurement'}


class Measurements:
    def __init__(self, domain):
        self.domain, self.store = domain, domain.store

    def import_series(self, pid, options, actor):
        source, path = self.domain.file_record(pid, options.file_id)
        summary, _ = analyze(path, options)
        if core.sha(path) != source['hash']:
            raise core.ValidationError('分析期间原件哈希变化，未保存')
        return self.store.put('measurement', {'measurement_id': identifier('measurement'),
            'project_id': pid, 'actor': actor, 'created_at': core.now(), 'options': options.model_dump(),
            'source': {k: source[k] for k in ('file_id','hash','name')}, 'parser_hash':core.sha(__file__),
            'summary': summary})

    def get(self, pid, mid):
        record = self.store.get('measurement', mid)
        if record['project_id'] != pid:
            raise KeyError(mid)
        source, path = self.domain.file_record(pid, record['source']['file_id'])
        if source['hash'] != record['source']['hash'] or core.sha(path) != source['hash']:
            raise core.ValidationError('计量原件变化；历史分析已失效，须新建分析')
        if record['parser_hash'] != core.sha(__file__):
            raise core.ValidationError('计量分析规则已变；历史记录保留，须新建分析')
        return record, path

    def compare(self, pid, request, actor):
        observed, opath = self.get(pid, request.observed_id)
        predicted, ppath = self.get(pid, request.prediction_id)
        a, b = observed['options'], predicted['options']
        if a['role'] != 'observed' or b['role'] != 'prediction':
            raise core.ValidationError('须分别选择实测序列与预测序列')
        for key in ('building_ref','meter_boundary','quantity','interval_seconds'):
            if a[key] != b[key]:
                raise core.ValidationError('计量口径不一致：'+key+'；不把全楼用电当作冷机用电')
        sa, ra = analyze(opath, SeriesImport(**a))
        sb, rb = analyze(ppath, SeriesImport(**b))
        if not sa['eligible_for_comparison'] or not sb['eligible_for_comparison']:
            raise core.ValidationError('计量或预测存在缺测/重复/乱序/时间问题；须保留原件并提供有依据的修订版本')
        da = {r['timestamp']:r['energy_kwh'] for r in ra}
        db = {r['timestamp']:r['energy_kwh'] for r in rb}
        if da.keys() != db.keys():
            raise core.ValidationError('实测与预测时段未完整一一对应，未仅保留交集来美化误差')
        try:
            cutoff = timestamp(request.holdout_start)
        except ValueError as exc:
            raise core.ValidationError('留出期开始时间须明确UTC偏移') from exc
        train, holdout = [], []
        for key in sorted(da):
            (train if timestamp(key) < cutoff else holdout).append((da[key],db[key]))
        result = {'comparison_id':identifier('comparison'), 'project_id':pid, 'actor':actor,
            'created_at':core.now(), 'options':request.model_dump(),
            'observed_source':observed['source'], 'prediction_source':predicted['source'],
            'parser_hash':core.sha(__file__), 'training':errors(train,request.fitted_parameters),
            'holdout':errors(holdout), 'calibrated':False,
            'scope':'Aligned imported-series error assessment only. No native-model parameter fit, independent sensor certification, or field calibration approval.'}
        return self.store.put('comparison', result)


def register_measurements(app, domain):
    from fastapi import Request
    service = app.state.measurements = Measurements(domain)

    @app.get('/api/projects/{project_id}/measurements/columns/{file_id}')
    def columns(project_id: str, file_id: str):
        _, path = domain.file_record(project_id, file_id)
        return {'columns': csv_reader(path).fieldnames}

    @app.get('/api/projects/{project_id}/measurements')
    def history(project_id: str):
        return domain.store.list('measurement', project_id)

    @app.get('/api/projects/{project_id}/measurements/comparisons')
    def comparisons(project_id: str):
        return domain.store.list('comparison', project_id)

    @app.post('/api/projects/{project_id}/measurements', status_code=201)
    def create(project_id: str, body: SeriesImport, request: Request):
        return service.import_series(project_id, body, request.state.user['id'])

    @app.post('/api/projects/{project_id}/measurements/compare', status_code=201)
    def compare(project_id: str, body: SeriesComparison, request: Request):
        return service.compare(project_id, body, request.state.user['id'])
