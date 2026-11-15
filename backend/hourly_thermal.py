"""Pinned EnergyPlus 9.0.1 hourly sensible delivery, not equipment sizing.

The SQL TimestepType labels in this version are reversed relative to the output
registration strings. Contracts below follow actual native SQLite, not guessed
labels. SNLoad rates are single-zone values; apply zone/list multipliers once.
"""
import math
import re
import sqlite3
import time
from contextlib import closing
from datetime import date
from pathlib import Path

from .core import sha

POLICY = 'native-hourly-sensible-9.0.1-v1'
MAX_ZONES = 64
MAX_HOURS = 8784
VARIABLES = {
    'temperature_C': ('Zone Air Temperature', 'C'),
    'heating_W': ('Zone Air System Sensible Heating Rate', 'W'),
    'cooling_W': ('Zone Air System Sensible Cooling Rate', 'W'),
}
LIMITATIONS = [
    '逐时值是该小时的原生平均值；峰值为所选环境内的小时平均峰值，不是瞬时峰值、设计容量或设备选型结果。',
    '显热交付量不等于电耗、燃料消耗或含潜热的总冷热量；不能据此直接核算能耗或碳排放。',
    '全楼同时峰值按同一原生时刻汇总；分区倍率和分组倍率仅对负荷应用一次，不放大温度。',
    '完整覆盖要求所有模型分区都具备三个逐时变量；缺测、未请求或不支持的数据不计为零。',
    '时钟沿用原生月、日、小时及 DST 标志；未转换为 UTC，设计日与天气运行期分别处理。',
    '只代表输入模型情景；未验证实楼校准、当地规范符合性、逐时舒适性达标或时间步独立性。',
]


class HourlyEvidenceError(ValueError):
    pass


def finite(value, label, low=None, high=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise HourlyEvidenceError('Invalid native numeric ' + label)
    if (low is not None and value < low) or (high is not None and value > high):
        raise HourlyEvidenceError('Out-of-range ' + label)
    return float(value)


def integer(value, label, low, high):
    number = finite(value, label, low, high)
    if number != int(number):
        raise HourlyEvidenceError('Non-integer ' + label)
    return int(number)


def model_zones(path):
    if path.stat().st_size > 32 * 1024**2:
        raise HourlyEvidenceError('Model exceeds hourly inspection budget')
    text = re.sub(r'!.*', '', path.read_text(encoding='utf-8-sig'))
    if not text.rstrip().endswith(';'):
        raise HourlyEvidenceError('Unterminated model')
    objects = [[v.strip() for v in p.split(',')] for p in text.split(';') if p.strip()]
    versions = [v for v in objects if v[0].lower() == 'version']
    if len(versions) != 1 or versions[0][1:] != ['9.0']:
        raise HourlyEvidenceError('Only IDF 9.0 is verified')
    zones = [v[1].upper() for v in objects if v[0].lower() == 'zone' and len(v) > 1 and v[1]]
    if not 1 <= len(zones) <= MAX_ZONES or len(set(zones)) != len(zones):
        raise HourlyEvidenceError('Missing, duplicate or excessive model zones')
    return set(zones)


def bounded(con, query, parameters=(), limit=MAX_HOURS):
    rows = con.execute(query, parameters).fetchmany(limit + 1)
    if len(rows) > limit:
        raise HourlyEvidenceError('Native row budget exceeded')
    return rows


def environment_rows(con, environment_index):
    sim = bounded(con, 'SELECT EnergyPlusVersion,Completed,CompletedSuccessfully FROM Simulations', limit=1)
    if (len(sim) != 1 or tuple(sim[0])[1:] != (1, 1) or not isinstance(sim[0][0], str)
            or not re.search(r'\bVersion\s+9\.0\.1(?:[-,\s]|$)', sim[0][0])):
        raise HourlyEvidenceError('Expected successful pinned EnergyPlus 9.0.1 simulation')
    envs = bounded(con, 'SELECT * FROM EnvironmentPeriods', limit=100)
    if len({r['EnvironmentPeriodIndex'] for r in envs}) != len(envs):
        raise HourlyEvidenceError('Duplicate environment identity')
    selected = [r for r in envs if (r['EnvironmentType'] == 3 if environment_index is None
                                  else r['EnvironmentPeriodIndex'] == environment_index)]
    if len(selected) != 1 or selected[0]['EnvironmentType'] not in (1, 3):
        raise HourlyEvidenceError('Select one supported weather period or explicit design day')
    env = selected[0]
    env_id = integer(env['EnvironmentPeriodIndex'], 'environment index', 1, 1000000)
    clocks = bounded(con, 'SELECT * FROM Time WHERE EnvironmentPeriodIndex=? AND IntervalType=1 '
                     'AND COALESCE(WarmupFlag,0)=0 ORDER BY TimeIndex', (env_id,))
    expected_hours = 24 if env['EnvironmentType'] == 1 else len(clocks)
    if not clocks or len(clocks) != expected_hours or (env['EnvironmentType'] == 3 and len(clocks) not in (8760, 8784)):
        raise HourlyEvidenceError('Incomplete environment hourly coverage')
    leap_year = 2000 if len(clocks) == 8784 else 2001
    clock_map, stamps, previous = {}, [], None
    for i, row in enumerate(clocks):
        idx = integer(row['TimeIndex'], 'TimeIndex', 1, 2**31 - 1)
        month = integer(row['Month'], 'month', 1, 12)
        day = integer(row['Day'], 'day', 1, 31)
        hour = integer(row['Hour'], 'hour', 1, 24)
        dst = integer(row['Dst'], 'DST', 0, 1)
        integer(row['Year'], 'year', 0, 9999)
        if row['Minute'] != 0 or row['Interval'] != 60 or row['SimulationDays'] != i // 24 + 1:
            raise HourlyEvidenceError('Unsupported hourly clock or simulation day')
        try:
            ordinal = (date(leap_year, month, day) - date(leap_year, 1, 1)).days * 24 + hour - 1
        except ValueError as exc:
            raise HourlyEvidenceError('Invalid native calendar date') from exc
        if idx in clock_map or (previous is not None and ordinal != previous + 1):
            raise HourlyEvidenceError('Duplicate, missing or reordered hourly clock')
        if i == 0 and (hour != 1 or (env['EnvironmentType'] == 3 and ordinal != 0)):
            raise HourlyEvidenceError('Incomplete initial day')
        previous = ordinal
        clock_map[idx] = i
        stamps.append({'time_index': idx, 'year': row['Year'], 'month': month, 'day': day,
                       'hour_ending': hour, 'dst': dst, 'interval_minutes': 60})
    return sim[0][0], env, clocks, clock_map, stamps


def _read(con, names, environment_index):
    sql_version, env, clocks, clock_map, stamps = environment_rows(con, environment_index)
    env_id = env['EnvironmentPeriodIndex']
    zones = bounded(con, 'SELECT ZoneName,Multiplier,ListMultiplier FROM Zones', limit=MAX_ZONES)
    if any(not isinstance(r['ZoneName'], str) for r in zones):
        raise HourlyEvidenceError('Invalid native zone name')
    if len(zones) != len(names) or {r['ZoneName'].upper() for r in zones} != names:
        raise HourlyEvidenceError('Model/native zone coverage mismatch')
    dictionary = bounded(con, 'SELECT * FROM ReportDataDictionary WHERE Name IN (?,?,?) AND ReportingFrequency=?',
                         tuple(v[0] for v in VARIABLES.values()) + ('Hourly',), limit=3 * MAX_ZONES)
    lookup = {}
    for row in dictionary:
        key = (row['KeyValue'], row['Name'])
        if key in lookup or row['KeyValue'] not in names:
            raise HourlyEvidenceError('Duplicate or unbound hourly dictionary')
        lookup[key] = row
    if len(lookup) != len(names) * 3:
        raise HourlyEvidenceError('Missing requested hourly temperature/heating/cooling variables')
    building = {'heating_W': [0.] * len(clocks), 'cooling_W': [0.] * len(clocks)}
    series, summaries = {}, []
    def peak(values):
        index = max(range(len(values)), key=values.__getitem__)
        return {'value_W': values[index], 'time': stamps[index], 'first_of_ties': True}
    for zone in zones:
        name = zone['ZoneName'].upper()
        multiplier = finite(zone['Multiplier'], 'zone multiplier', 1, 1000000)
        list_multiplier = finite(zone['ListMultiplier'], 'list multiplier', 1, 1000000)
        values, locators = {}, {}
        for key, (variable, unit) in VARIABLES.items():
            d = lookup[(name, variable)]
            if (d['IsMeter'], d['Type'], d['IndexGroup'], d['TimestepType'], d['Units']) != (0, 'Avg', 'System', 'Zone', unit) or d['ScheduleName'] not in (None, ''):
                raise HourlyEvidenceError('Unsupported hourly dictionary semantics or unit')
            did = integer(d['ReportDataDictionaryIndex'], 'dictionary index', 1, 2**31 - 1)
            data = bounded(con, 'SELECT r.TimeIndex,r.Value FROM ReportData r JOIN Time t ON r.TimeIndex=t.TimeIndex '
                           'WHERE r.ReportDataDictionaryIndex=? AND t.EnvironmentPeriodIndex=? '
                           'AND COALESCE(t.WarmupFlag,0)=0 ORDER BY r.TimeIndex', (did, env_id))
            if len(data) != len(clocks) or [r['TimeIndex'] for r in data] != list(clock_map):
                raise HourlyEvidenceError('Missing, duplicate or extra native hourly samples')
            low, high = (-100, 150) if unit == 'C' else (0, 1e12)
            scale = 1 if unit == 'C' else multiplier * list_multiplier
            values[key] = [finite(r['Value'], variable, low, high) * scale for r in data]
            locators[key] = {'dictionary_index': did, 'variable': variable, 'unit': unit,
                             'native_values_unmultiplied': True, 'scale_applied': scale}
            if unit == 'W':
                building[key] = [a + b for a, b in zip(building[key], values[key])]
        series[name] = values
        summaries.append({'zone_name': name, 'zone_multiplier': multiplier, 'zone_list_multiplier': list_multiplier,
                          'temperature_min_C': min(values['temperature_C']), 'temperature_max_C': max(values['temperature_C']),
                          'heating_peak': peak(values['heating_W']), 'cooling_peak': peak(values['cooling_W']),
                          'delivered_sensible_heating_kWh': math.fsum(values['heating_W']) / 1000,
                          'delivered_sensible_cooling_kWh': math.fsum(values['cooling_W']) / 1000, 'locators': locators})
    totals = {mode + '_peak': peak(building[mode + '_W']) for mode in ('heating', 'cooling')}
    totals.update({mode + '_delivered_sensible_kWh': math.fsum(building[mode + '_W']) / 1000 for mode in ('heating', 'cooling')})
    profiles = []
    for mode in ('heating', 'cooling'):
        at = clock_map[totals[mode + '_peak']['time']['time_index']]
        start = at // 24 * 24
        profiles.append({'selected_for': mode + '_coincident_peak', 'times': stamps[start:start + 24],
                         'building': {k: v[start:start + 24] for k, v in building.items()},
                         'zones': {name: {k: v[start:start + 24] for k, v in values.items()} for name, values in series.items()}})
    return {'engine_sql_version': sql_version, 'environment': dict(env), 'hour_count': len(clocks),
            'coverage': 'all_model_zones_all_environment_hours', 'zones': summaries, 'building': totals,
            'peak_day_profiles': profiles}


def inspect_hourly_thermal(sql_path, model_path, *, environment_index=None):
    """No input mutation. Unavailable is explicit and never contains numeric results."""
    sql_path, model_path = Path(sql_path), Path(model_path)
    receipt = {'status': 'unavailable', 'policy_version': POLICY, 'parser_sha256': sha(Path(__file__)),
               'model_sha256': sha(model_path), 'sql_sha256': sha(sql_path), 'summary': None,
               'limitations': list(LIMITATIONS)}
    try:
        if sql_path.stat().st_size > 512 * 1024**2:
            raise HourlyEvidenceError('Native SQL exceeds hourly inspection budget')
        names = model_zones(model_path)
        with closing(sqlite3.connect(sql_path.resolve().as_uri() + '?mode=ro', uri=True, timeout=2)) as con:
            con.row_factory = sqlite3.Row
            deadline = time.monotonic() + 15
            con.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
            con.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, 1024**2)
            con.execute('PRAGMA trusted_schema=OFF')
            schema = bounded(con, "SELECT type,name,sql FROM sqlite_master WHERE name IN ('Simulations','EnvironmentPeriods','Time','Zones','ReportDataDictionary','ReportData')", limit=6)
            if len(schema) != 6 or any(r['type'] != 'table' or not re.match(r'CREATE\s+TABLE\b', r['sql'] or '', re.I) for r in schema):
                raise HourlyEvidenceError('Expected native physical tables, not views or virtual tables')
            if con.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise HourlyEvidenceError('Native SQLite integrity failure')
            summary = _read(con, names, environment_index)
        if sha(model_path) != receipt['model_sha256'] or sha(sql_path) != receipt['sql_sha256']:
            raise HourlyEvidenceError('Hourly evidence changed during inspection')
        receipt.update(status='calculated_model_scenario', summary=summary)
    except (HourlyEvidenceError, sqlite3.Error, UnicodeError, KeyError, IndexError) as exc:
        receipt['reason'] = str(exc)
    return receipt
