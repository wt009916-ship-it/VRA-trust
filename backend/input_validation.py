"""Conservative preflight for the supported annual EnergyPlus workflow.

These checks detect malformed inputs; they do not certify model suitability.
"""
import csv
import math
import re
from datetime import date, timedelta

from .core import ValidationError


def annual_hour_keys(leap=False):
    start = date(2024 if leap else 2025, 1, 1)
    return {(d.month, d.day, hour) for day in range(366 if leap else 365)
            for d in [start + timedelta(days=day)] for hour in range(1, 25)}


def validate_hourly_rows(rows):
    """Month, day, hour, duration minutes; require each calendar hour exactly once."""
    keys = []
    for month, day, hour, interval in rows:
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
               or int(v) != v for v in (month, day, hour, interval)) or interval != 60:
            raise ValidationError('Invalid annual hourly interval')
        keys.append((int(month), int(day), int(hour)))
    expected = annual_hour_keys(any(m == 2 and d == 29 for m, d, _ in keys))
    if len(keys) != len(expected) or set(keys) != expected:
        raise ValidationError('Incomplete/duplicate annual hourly calendar coverage')


def validate_epw(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.reader(stream))
    headers = ['LOCATION', 'DESIGN CONDITIONS', 'TYPICAL/EXTREME PERIODS', 'GROUND TEMPERATURES',
               'HOLIDAYS/DAYLIGHT SAVINGS', 'COMMENTS 1', 'COMMENTS 2', 'DATA PERIODS']
    if len(rows) < 8 or any(not row or row[0].strip() != label for row, label in zip(rows[:8], headers)):
        raise ValidationError('EPW requires eight valid header records')
    if len(rows[0]) < 10 or len(rows[7]) < 7 or rows[7][1:3] != ['1', '1']:
        raise ValidationError('EPW requires one hourly annual data period and LOCATION metadata')
    times = []
    try:
        for row in rows[8:]:
            if len(row) != 35:
                raise ValueError('expected 35 weather fields')
            month, day, hour, minute = map(int, row[1:5])
            if minute not in (0, 60):
                raise ValueError('non-hourly minute')
            for index in (6, 7, 8, 9):
                if not math.isfinite(float(row[index])):
                    raise ValueError('non-finite weather value')
            times.append((month, day, hour, 60))
        validate_hourly_rows(times)
        if [(m, d, h) for m, d, h, _ in times] != sorted((m, d, h) for m, d, h, _ in times):
            raise ValueError('weather records out of order')
    except (ValueError, IndexError) as exc:
        raise ValidationError('Invalid EPW annual data: ' + str(exc)) from exc


def validate_idf(path):
    text = re.sub(r'!.*', '', path.read_text(encoding='utf-8-sig'))
    if not text.rstrip().endswith(';'):
        raise ValidationError('IDF contains an unterminated object')
    objects = [[v.strip() for v in chunk.split(',')] for chunk in text.split(';') if chunk.strip()]
    kinds = {obj[0].lower() for obj in objects}
    required = {'building', 'zone', 'construction', 'buildingsurface:detailed', 'runperiod', 'output:table:summaryreports'}
    missing = required - kinds
    if missing:
        raise ValidationError('IDF annual model missing required objects: ' + ', '.join(sorted(missing)))
    for obj in objects:
        if obj[0].lower() == 'material':
            try:
                values = [float(obj[i]) for i in (3, 4, 5, 6)]
                if any(not math.isfinite(v) or v <= 0 for v in values):
                    raise ValueError('non-positive property')
            except (ValueError, IndexError) as exc:
                raise ValidationError('Invalid Material thickness/conductivity/density/specific heat') from exc
