"""Source-bound EnergyPlus 9.0.1 zone sensible sizing, never annual-energy inference.

ZoneSizes columns/units follow SQLiteProcedures.cc:1689 and SizingManager.cc:4008
at tag v9.0.1. Values already include native zone multipliers; do not multiply again.
Unsupported/missing sizing evidence leaves rows null without invalidating annual energy.
"""
import math
import re
import sqlite3
from datetime import date
from pathlib import Path

from .core import sha

POLICY = 'zone-sensible-sizing-9.0.1-v1'
SOURCE = 'https://github.com/NatLabRockies/EnergyPlus/blob/v9.0.1/src/EnergyPlus/SizingManager.cc#L4008'
LIMITATIONS = [
    '仅为输入模型设计工况下的分区显热负荷；不代表当地规范设计、实楼校准或设备选型结论。',
    '计算负荷与用户调整后负荷分开；原生数值已包含分区倍率，不再次相乘。',
    '各分区峰值发生时刻可能不同，不提供全楼同时峰值或将分区峰值求和冒充全楼负荷。',
    '不包含潜热总冷负荷、完整设备容量与系统输配损失核验；未输出的分区不能计为零。',
    '设计日名称不是资料来源证明；地理坐标相符也不等于设计日统计来源、版本或适用性已审核。',
]


class SizingEvidenceError(ValueError):
    pass


def numeric(value, label, low=None, high=None):
    if isinstance(value, bool):
        raise SizingEvidenceError('Invalid numeric ' + label)
    try:
        number = float(value)
    except (ValueError, TypeError) as exc:
        raise SizingEvidenceError('Invalid numeric ' + label) from exc
    if not math.isfinite(number) or (low is not None and number < low) or (high is not None and number > high):
        raise SizingEvidenceError('Out-of-range ' + label)
    return number


def model_basis(path):
    if path.stat().st_size > 32 * 1024**2:
        raise SizingEvidenceError('Model exceeds sizing inspection budget')
    text = re.sub(r'!.*', '', path.read_text(encoding='utf-8-sig'))
    if not text.rstrip().endswith(';'):
        raise SizingEvidenceError('Unterminated IDF object')
    objects = [[field.strip() for field in part.split(',')] for part in text.split(';') if part.strip()]
    if len(objects) > 100000:
        raise SizingEvidenceError('Too many IDF objects for sizing inspection')
    groups = {}
    for index, obj in enumerate(objects, 1):
        groups.setdefault(obj[0].lower(), []).append((index, obj))
    def single(kind):
        rows = groups.get(kind, [])
        if len(rows) != 1:
            raise SizingEvidenceError('Missing/duplicate IDF ' + kind)
        return rows[0][1]
    version = single('version')
    if len(version) != 2 or version[1] != '9.0':
        raise SizingEvidenceError('Only the pinned IDF 9.0 sizing schema is verified')
    control = single('simulationcontrol')
    if len(control) < 2 or control[1].lower() != 'yes':
        raise SizingEvidenceError('Zone sizing calculation is not explicitly enabled')
    if any(k.startswith('sizingperiod:') and k != 'sizingperiod:designday' for k in groups):
        raise SizingEvidenceError('Weather-file sizing periods require separate provenance verification')
    location = single('site:location')
    if len(location) != 6:
        raise SizingEvidenceError('Invalid Site:Location')
    site = {'name': location[1]}
    for index, key, low, high in [(2, 'latitude_deg', -90, 90), (3, 'longitude_deg', -180, 180),
                                  (4, 'utc_offset_h', -12, 12), (5, 'elevation_m', -1000, 9999.9)]:
        site[key] = numeric(location[index], key, low, high)
    days = {}
    for index, obj in groups.get('sizingperiod:designday', []):
        if len(obj) < 7 or not obj[1] or obj[1].upper() in days:
            raise SizingEvidenceError('Missing/duplicate/short design day')
        month, day = numeric(obj[2], 'design month', 1, 12), numeric(obj[3], 'design day', 1, 31)
        if int(month) != month or int(day) != day:
            raise SizingEvidenceError('Non-integer design date')
        try:
            date(2024, int(month), int(day))
        except ValueError as exc:
            raise SizingEvidenceError('Invalid design date') from exc
        days[obj[1].upper()] = {'name': obj[1], 'month': int(month), 'day': int(day), 'day_type': obj[4],
            'maximum_dry_bulb_C': numeric(obj[5], 'maximum dry bulb', -90, 70),
            'daily_dry_bulb_range_K': numeric(obj[6], 'dry bulb range', 0, 120),
            'locator': {'object': 'SizingPeriod:DesignDay', 'object_index': index},
            'raw_fields': obj[1:], 'statistical_source_status': 'not_independently_verified'}
    if not days:
        raise SizingEvidenceError('No explicit design-day definitions')
    model_zones = [o[1].upper() for _, o in groups.get('zone', []) if len(o) > 1 and o[1]]
    if not model_zones or len(set(model_zones)) != len(model_zones):
        raise SizingEvidenceError('Missing/duplicate model zones')
    summaries = [v.lower() for _, o in groups.get('output:table:summaryreports', []) for v in o[1:]]
    return {'declared_site': site, 'design_days': list(days.values()), 'zone_names': model_zones,
            'tabular_requested': any(v.startswith('allsummary') or v == 'hvacsizingsummary' for v in summaries),
            'simulation_control_fields': control[1:],
            'sizing_parameter_objects': [o[1:] for _, o in groups.get('sizing:parameters', [])],
            'zone_sizing_objects': [o[1:] for _, o in groups.get('sizing:zone', [])]}


def _read_rows(con, basis):
    sim = con.execute('SELECT EnergyPlusVersion,Completed,CompletedSuccessfully FROM Simulations').fetchall()
    if len(sim) != 1 or tuple(sim[0])[1:] != (1, 1):
        raise SizingEvidenceError('Sizing simulation did not uniquely complete successfully')
    if not isinstance(sim[0][0], str) or not re.search(r'\bVersion\s+9\.0\.1(?:[-,\s]|$)', sim[0][0]):
        raise SizingEvidenceError('Native sizing units/schema are only verified for EnergyPlus 9.0.1')
    data = con.execute('SELECT * FROM ZoneSizes ORDER BY ZoneSizesIndex').fetchmany(10001)
    if not data or len(data) > 10000:
        raise SizingEvidenceError('Missing or excessive native ZoneSizes records')
    zones = con.execute('SELECT ZoneName,Multiplier,ListMultiplier,FloorArea FROM Zones').fetchmany(10001)
    if not zones or len(zones) > 10000:
        raise SizingEvidenceError('Missing or excessive native zone metadata')
    if any(not isinstance(r['ZoneName'], str) or not r['ZoneName'] for r in zones):
        raise SizingEvidenceError('Invalid native zone name')
    zone_map = {r['ZoneName'].upper(): r for r in zones}
    if len(zone_map) != len(zones) or set(zone_map) != set(basis['zone_names']):
        raise SizingEvidenceError('Model/SQL zone coverage mismatch')
    days = {day['name'].upper(): day for day in basis['design_days']}
    cells = con.execute("SELECT TableName,RowName,ColumnName,Units,Value FROM TabularDataWithStrings WHERE ReportName='HVACSizingSummary'").fetchmany(100001)
    if len(cells) > 100000:
        raise SizingEvidenceError('Sizing table exceeds inspection budget')
    crosscheck = bool(cells)
    if basis['tabular_requested'] and not crosscheck:
        raise SizingEvidenceError('Requested HVAC sizing summary is missing')
    cell_index = {}
    for cell in cells:
        if not isinstance(cell['RowName'], str):
            raise SizingEvidenceError('Invalid sizing summary row name')
        cell_index.setdefault((cell['TableName'], cell['RowName'].upper(), cell['ColumnName']), []).append(cell)
    seen, rows = set(), []
    for native in data:
        name, mode = native['ZoneName'], native['LoadType']
        if not isinstance(name, str) or name.upper() not in zone_map or mode not in {'Heating', 'Cooling'}:
            raise SizingEvidenceError('Unbound zone or unknown load type')
        key = (name.upper(), mode)
        if key in seen:
            raise SizingEvidenceError('Duplicate zone/load type')
        seen.add(key)
        row_id = numeric(native['ZoneSizesIndex'], 'ZoneSizes row index', 1)
        if row_id != int(row_id):
            raise SizingEvidenceError('Non-integer ZoneSizes row index')
        calculated = numeric(native['CalcDesLoad'], 'calculated design load W', 0)
        adjusted = numeric(native['UserDesLoad'], 'user design load W', 0)
        zone = zone_map[name.upper()]
        multiplier = numeric(zone['Multiplier'], 'zone multiplier', 1)
        list_multiplier = numeric(zone['ListMultiplier'], 'zone list multiplier', 1)
        floor_area = numeric(zone['FloorArea'], 'unmultiplied zone area m2', 0)
        day_name = native['DesDayName']
        peak = None
        if calculated > 0 or adjusted > 0:
            if not isinstance(day_name, str) or day_name.upper() not in days:
                raise SizingEvidenceError('Positive design load has no bound design day')
            definition = days[day_name.upper()]
            match = re.fullmatch(r'(\d{1,2})/(\d{1,2}) (\d{2}):(\d{2}):(\d{2})', native['PeakHrMin'] or '')
            if not match:
                raise SizingEvidenceError('Invalid peak date/time')
            month, day, hour, minute, second = map(int, match.groups())
            if ((month, day) != (definition['month'], definition['day']) or hour > 24 or minute > 59 or second > 59
                    or (hour == 24 and (minute or second))):
                raise SizingEvidenceError('Peak date/time does not bind to design day')
            peak = {'design_day': day_name, 'date_time': native['PeakHrMin'],
                    'outdoor_temperature_C': numeric(native['PeakTemp'], 'peak temperature C', -100, 100),
                    'outdoor_humidity_ratio_kg_kg': numeric(native['PeakHumRat'], 'peak humidity ratio', 0),
                    'design_day_locator': definition['locator']}
        elif day_name:
            if not isinstance(day_name, str) or day_name.upper() not in days:
                raise SizingEvidenceError('Zero-load row has an unknown design day')
        if crosscheck:
            for column, value in [('Calculated Design Load', calculated), ('User Design Load', adjusted)]:
                matches = cell_index.get(('Zone Sensible ' + mode, name.upper(), column), [])
                if len(matches) != 1 or matches[0]['Units'] != 'W':
                    raise SizingEvidenceError('Missing/duplicate or unsupported-unit sizing summary cell')
                # Native table W values are printed with two decimal places.
                if abs(numeric(matches[0]['Value'], 'tabular load W', 0) - value) > .011:
                    raise SizingEvidenceError('ZoneSizes/tabular load values disagree')
        rows.append({'zone_name': name, 'load_type': mode, 'calculated_sensible_load_W': calculated,
            'user_adjusted_sensible_load_W': adjusted, 'peak': peak,
            'calculated_airflow_m3_s': numeric(native['CalcDesFlow'], 'calculated airflow', 0),
            'user_airflow_m3_s': numeric(native['UserDesFlow'], 'user airflow', 0),
            'outdoor_airflow_m3_s': numeric(native['CalcOutsideAirFlow'], 'outdoor airflow', 0),
            'doas_heat_addition_W': numeric(native['DOASHeatAddRate'], 'DOAS heat addition'),
            'zone_multiplier': multiplier, 'zone_list_multiplier': list_multiplier,
            'unmultiplied_floor_area_m2': floor_area, 'multipliers_already_applied': True,
            'locator': {'table': 'ZoneSizes', 'row_id': int(row_id),
                        'calculated_column': 'CalcDesLoad', 'user_column': 'UserDesLoad', 'unit': 'W'}})
    covered = {name for name, _ in seen}
    if any((name, mode) not in seen for name in covered for mode in ('Heating', 'Cooling')):
        raise SizingEvidenceError('Incomplete heating/cooling pair')
    return rows, sim[0][0], sorted(set(zone_map) - covered), 'matched_W_cells' if crosscheck else 'not_requested'


def inspect_design_loads(sql_path, model_path, weather_quality=None):
    """Return a typed unavailable receipt for known evidence gaps, never fabricated rows."""
    sql_path, model_path = Path(sql_path), Path(model_path)
    receipt = {'policy_version': POLICY, 'parser_sha256': sha(Path(__file__)), 'source_reference': SOURCE,
               'status': 'unavailable', 'rows': None, 'building_coincident_peak_W': None,
               'limitations': list(LIMITATIONS), 'model_sha256': sha(model_path), 'sql_sha256': sha(sql_path),
               'basis': None, 'site_comparison': 'not_assessed', 'weather_station': None,
               'weather_sha256': None, 'site_applicability': 'requires_professional_review'}
    try:
        basis = model_basis(model_path)
        receipt['basis'] = basis
        if weather_quality is not None:
            station = weather_quality['station']
            keys = ('latitude_deg', 'longitude_deg', 'utc_offset_h', 'elevation_m')
            same = all(abs(numeric(station[k], k) - basis['declared_site'][k]) <= (1 if k == 'elevation_m' else .01) for k in keys)
            receipt.update(weather_station=station, weather_sha256=weather_quality['source_sha256'],
                           site_comparison='coordinates_close_not_proof' if same else 'declared_site_differs_from_weather')
        con = sqlite3.connect(sql_path.resolve().as_uri() + '?mode=ro', uri=True)
        con.row_factory = sqlite3.Row
        try:
            if con.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise SizingEvidenceError('Native SQLite integrity failure')
            rows, version, omitted, crosscheck = _read_rows(con, basis)
        finally:
            con.close()
        if sha(sql_path) != receipt['sql_sha256'] or sha(model_path) != receipt['model_sha256']:
            raise SizingEvidenceError('Sizing evidence changed during inspection')
        receipt.update(status='calculated_model_scenario', rows=rows, engine_sql_version=version,
                       zones_without_sizing=omitted, tabular_crosscheck=crosscheck)
    except (SizingEvidenceError, sqlite3.Error, UnicodeError, KeyError, IndexError) as exc:
        receipt['reason'] = str(exc)
    return receipt
