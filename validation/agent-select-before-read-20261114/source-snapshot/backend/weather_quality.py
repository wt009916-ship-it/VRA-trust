"""Read-only EPW policy for the supported EnergyPlus 9.0 hourly annual workflow.

The receipt is input screening, not station certification or model validation.
Native optional defaults remain visible; VRA never rewrites weather observations.
"""
import csv
import math
import re
from pathlib import Path

from .core import ValidationError, sha

POLICY_VERSION = 'epw-hourly-9.0-v1'
DICTIONARY = 'https://bigladdersoftware.com/epx/docs/9-0/auxiliary-programs/energyplus-weather-file-epw-data-dictionary.html'
ENGINE_SOURCE = 'https://github.com/NatLabRockies/EnergyPlus/blob/v9.0.1/src/EnergyPlus/WeatherManager.cc'
# Column (zero based), name, unit, minimum, maximum, missing threshold.
FIELDS = (
    (6, 'dry_bulb', 'degC', -70, 70, 99.9),
    (7, 'dew_point', 'degC', -70, 70, 99.9),
    (8, 'relative_humidity', '%', 0, 110, 999),
    (9, 'station_pressure', 'Pa', 31000, 120000, 999999),
    (10, 'extraterrestrial_horizontal_radiation', 'Wh/m2', 0, None, 9999),
    (11, 'extraterrestrial_direct_radiation', 'Wh/m2', 0, None, 9999),
    (12, 'horizontal_infrared', 'Wh/m2', 0, None, 9999),
    (13, 'global_horizontal_radiation', 'Wh/m2', 0, None, 9999),
    (14, 'direct_normal_radiation', 'Wh/m2', 0, None, 9999),
    (15, 'diffuse_horizontal_radiation', 'Wh/m2', 0, None, 9999),
    (16, 'global_illuminance', 'lux', 0, None, 999900),
    (17, 'direct_illuminance', 'lux', 0, None, 999900),
    (18, 'diffuse_illuminance', 'lux', 0, None, 999900),
    (19, 'zenith_luminance', 'cd/m2', 0, None, 9999),
    (20, 'wind_direction', 'deg', 0, 360, 999),
    (21, 'wind_speed', 'm/s', 0, 40, 999),
    (22, 'total_sky_cover', 'tenths', 0, 10, 99),
    (23, 'opaque_sky_cover', 'tenths', 0, 10, 99),
    (24, 'visibility', 'km', 0, None, 9999),
    (25, 'ceiling_height', 'm', 0, None, 99999),
    (28, 'precipitable_water', 'mm', 0, None, 999),
    (29, 'aerosol_optical_depth', 'EPW value', 0, None, .999),
    (30, 'snow_depth', 'cm', 0, None, 999),
    (31, 'days_since_snow', 'day', 0, None, 99),
    (32, 'albedo', '1', 0, 1, 999),
    (33, 'liquid_precipitation_depth', 'mm', 0, None, 999),
    (34, 'liquid_precipitation_quantity', 'h', 0, None, 99),
)
REQUIRED = {6, 7, 8, 9, 14, 15, 20, 21}
UNUSED = {10, 11, 13, 16, 17, 18, 19, 24, 25, 28, 29, 31, 34}
HEADERS = ['LOCATION', 'DESIGN CONDITIONS', 'TYPICAL/EXTREME PERIODS', 'GROUND TEMPERATURES',
           'HOLIDAYS/DAYLIGHT SAVINGS', 'COMMENTS 1', 'COMMENTS 2', 'DATA PERIODS']


def fail(line, field, unit, message):
    raise ValidationError(f'EPW line {line} · {field} [{unit}]: {message}')


def numeric(raw, line, field, unit):
    # Python float accepts underscores which are not an EPW numeric representation.
    if not re.fullmatch(r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[Ee][+-]?[0-9]+)?', raw.strip()):
        fail(line, field, unit, '需要有限数值，不接受空值、NaN、Inf 或带单位文本')
    value = float(raw)
    if not math.isfinite(value):
        fail(line, field, unit, '数值溢出或非有限值')
    return value


def inspect_epw(path):
    from .input_validation import validate_hourly_rows
    path = Path(path)
    if path.stat().st_size > 32 * 1024 * 1024:
        fail(1, 'file', 'byte', '超过当前年度小时文件 32 MiB 校验上限')
    digest = sha(path)
    with path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.reader(stream, strict=True)
        rows = []
        try:
            for row in reader:
                rows.append(row)
                if len(rows) > 8792:
                    fail(reader.line_num, 'calendar', 'h', '只支持单年 8760 或 8784 个小时')
                if reader.line_num != len(rows):
                    fail(reader.line_num, 'record', 'line', '不支持跨行 CSV 字段')
        except csv.Error as exc:
            fail(reader.line_num, 'CSV', 'line', str(exc))
    for index, label in enumerate(HEADERS):
        if len(rows) <= index or not rows[index] or rows[index][0].strip() != label:
            fail(index + 1, 'header', 'record', '需要八条完整 EPW 头记录: ' + label)
    if len(rows[0]) != 10:
        fail(1, 'LOCATION', 'record', '需要 10 个字段')
    station = dict(zip(['city', 'region', 'country', 'source', 'station_id'], [x.strip() for x in rows[0][1:6]]))
    for col, name, unit, lo, hi in [(6, 'latitude_deg', 'deg', -90, 90), (7, 'longitude_deg', 'deg', -180, 180),
                                    (8, 'utc_offset_h', 'h', -12, 12), (9, 'elevation_m', 'm', -1000, 9999.9)]:
        value = numeric(rows[0][col], 1, name, unit)
        if value < lo or value > hi or (col == 9 and value == hi):
            fail(1, name, unit, '超出 EnergyPlus 9.0 支持范围')
        station[name] = value
    period = [x.strip() for x in rows[7]]
    if len(period) != 7 or period[1:3] != ['1', '1']:
        fail(8, 'DATA PERIODS', 'h', '只支持一个年度、每小时一条记录')
    if period[4].lower() not in {'sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday'}:
        fail(8, 'start_weekday', 'day', '需要有效星期名称')
    if re.sub(r'\s', '', period[5]) != '1/1' or re.sub(r'\s', '', period[6]) != '12/31':
        fail(8, 'annual_period', 'date', '当前支持范围为 1/1 至 12/31；其他日期语法或多年度需另行核验')
    if len(rows[4]) < 5 or rows[4][1].strip().lower() not in {'yes', 'no'}:
        fail(5, 'LeapYear', 'flag', '需要明确 Yes 或 No')
    fields = {name: {'unit': unit, 'present_count': 0, 'missing_count': 0, 'min': None, 'max': None}
              for _, name, unit, *_ in FIELDS}
    conditions = {}

    def condition(code, field, line, message):
        key = (code, field)
        if key not in conditions:
            conditions[key] = {'code': code, 'field': field, 'count': 0, 'first_line': line, 'last_line': line,
                               'message': message}
        conditions[key]['count'] += 1
        conditions[key]['last_line'] = line

    times, years, minutes = [], set(), set()
    for line, row in enumerate(rows[8:], 9):
        if len(row) != 35:
            fail(line, 'record', 'field', '每小时需要 35 个字段')
        for col in range(5):
            if not re.fullmatch(r'[0-9]{1,' + ('4' if col == 0 else '2') + '}', row[col].strip()):
                fail(line, ['year', 'month', 'day', 'hour', 'minute'][col], 'integer', '时间字段须为整数')
        year, month, day, hour, minute = map(int, row[:5])
        if not 1 <= year <= 9999:
            fail(line, 'year', 'year', '无效年份')
        if minute not in {0, 60} or (minutes and minute not in minutes):
            fail(line, 'minute', 'min', '只支持全文件一致的 0（旧版小时文件）或 60；不支持混用或子小时数据')
        minutes.add(minute); years.add(year); times.append((month, day, hour, 60))
        values, missing = {}, set()
        for col, name, unit, lo, hi, sentinel in FIELDS:
            value = numeric(row[col], line, name, unit)
            values[col] = value
            is_missing = value >= sentinel or (col == 12 and value == 0)
            if is_missing:
                if col in REQUIRED:
                    fail(line, name, unit, '关键天气字段缺测；不允许由前值、默认值或零代替，请补充有来源的新版本')
                missing.add(col); fields[name]['missing_count'] += 1
                if col != 12:
                    code = 'UNUSED_FIELD_MISSING' if col in UNUSED else 'NATIVE_OPTIONAL_DEFAULT'
                    message = ('9.0 常规天气计算不使用该字段；缺测仍未补齐' if col in UNUSED else
                               '引擎可能沿用前值或默认值；不是已观测数据，需复核相应模型功能和适用性')
                    condition(code, name, line, message)
                continue
            if value < lo or (hi is not None and value > hi) or (col in {6, 7, 9} and value in {lo, hi}):
                fail(line, name, unit, '超出本策略采用的数据字典范围；请检查单位及源数据')
            item = fields[name]; item['present_count'] += 1
            item['min'] = value if item['min'] is None else min(value, item['min'])
            item['max'] = value if item['max'] is None else max(value, item['max'])
        if 12 in missing:
            if 23 in missing:
                fail(line, 'opaque_sky_cover', 'tenths', '长波辐射缺失时必须提供有效不透明天空覆盖量，不能使用默认云量推导')
            condition('NATIVE_SKY_DERIVATION', 'horizontal_infrared', line,
                      '引擎默认天空模型可用干球、露点及不透明云量推导天空温度；不是观测长波辐射，IDF 天空模型覆盖仍需复核')
        if values[7] > values[6]:
            condition('DEW_POINT_ABOVE_DRY_BULB', 'dew_point', line, '露点高于干球，可能涉及饱和或测量舍入；需气象专业复核')
        if row[26].strip() not in {'0', '9'}:
            fail(line, 'present_weather_observation', 'code', '只支持 0（观测）或 9（缺测）')
        if not re.fullmatch(r'[0-9]{9}', row[27].strip()):
            fail(line, 'present_weather_codes', 'code', '需要九位天气代码，缺测使用 9')
        if row[26].strip() == '9':
            condition('RAIN_OBSERVATION_MISSING', 'present_weather_observation', line,
                      '天气现象未观测，引擎会将雨标志视为否；不证明无雨，不可作为降雨/湿润过程实测依据')
        elif row[27].strip()[:3] == '999':
            condition('RAIN_CODES_MISSING', 'present_weather_codes', line, '降雨代码缺失；不证明无雨')
    try:
        validate_hourly_rows(times)
        if times != sorted(times):
            raise ValidationError('weather records out of order')
    except ValidationError as exc:
        fail(9, 'annual_calendar', 'h', str(exc))
    leap = any(month == 2 and day == 29 for month, day, _, _ in times)
    if leap and rows[4][1].strip().lower() != 'yes':
        fail(5, 'LeapYear', 'flag', '包含 2/29，但头记录不允许闰日，引擎可能跳过该日')
    if sha(path) != digest:
        fail(1, 'source_sha256', 'hash', '校验期间源文件变化，请重新导入')
    return {'policy_version': POLICY_VERSION, 'validator_sha256': sha(Path(__file__)), 'source_sha256': digest,
            'status': 'accepted_with_conditions' if conditions else 'accepted', 'hours': len(times), 'leap_day': leap,
            'minute_convention': next(iter(minutes)), 'source_years': sorted(years), 'station': station,
            'fields': fields, 'conditions': list(conditions.values()), 'application_imputation_count': 0,
            'references': [DICTIONARY, ENGINE_SOURCE],
            'scope': '单年小时输入筛查；允许有记录的可选缺测和原生天空推导，不认证气象来源、设计日或模型适用性。',
            'limitations': ['年份可由典型气象年跨年组合，不等于连续实测年。',
                            '0 分钟仅作为旧版整点文件约定接受，未改写原件。',
                            '未核验设计条件、典型周期及地温头的专业适用性；未执行气象一致性全面质量认证。',
                            '可选缺测仍影响相应模型能力，雨雪、地表反照率、湿润和植被功能须另行补证。']}
