"""Actual native projection and adversarial mutations; no native call claimed here."""
import json
import sqlite3
from pathlib import Path

import pytest

from backend.hourly_thermal import inspect_hourly_thermal


@pytest.fixture
def hourly_files(tmp_path):
    fixture = json.loads((Path(__file__).resolve().parents[1] / 'fixtures/test/native_hourly_thermal_projection.json').read_text())
    sql, model = tmp_path / 'native.sql', tmp_path / 'model.idf'
    with sqlite3.connect(sql) as con:
        for table, data in fixture['tables'].items():
            con.execute('CREATE TABLE "' + table + '" (' + ','.join('"' + c + '"' for c in data['columns']) + ')')
            con.executemany('INSERT INTO "' + table + '" VALUES (' + ','.join('?' for _ in data['columns']) + ')', data['rows'])
    model.write_text(fixture['model_idf'])
    return sql, model


def test_native_staggered_zones_and_multiplier_match_independent_heat_balance(hourly_files):
    result = inspect_hourly_thermal(*hourly_files, environment_index=1)
    assert result['status'] == 'calculated_model_scenario', result.get('reason')
    s = result['summary']
    assert s['hour_count'] == 24 and s['environment']['EnvironmentType'] == 1
    # Opposite sinusoidal exterior boundaries cancel in the sum of two massless boxes.
    expected = 2 * 3 * 2 * 110 * 20 / .54
    assert s['building']['heating_peak']['value_W'] == pytest.approx(expected, abs=1e-6)
    assert s['building']['heating_delivered_sensible_kWh'] == pytest.approx(expected * 24 / 1000, abs=1e-6)
    assert s['building']['heating_peak']['value_W'] < sum(z['heating_peak']['value_W'] for z in s['zones'])
    for z in s['zones']:
        assert z['zone_multiplier'] == 3 and z['zone_list_multiplier'] == 2
        assert z['temperature_min_C'] == pytest.approx(20, abs=1e-8)
        assert z['temperature_max_C'] == pytest.approx(20, abs=1e-8)
        assert z['locators']['heating_W']['scale_applied'] == 6
        assert z['locators']['temperature_C']['scale_applied'] == 1
        assert z['cooling_peak']['value_W'] == 0  # Observed zero, distinct from missing.


def test_design_day_never_implicitly_becomes_annual_weather(hourly_files):
    result = inspect_hourly_thermal(*hourly_files)
    assert result['status'] == 'unavailable' and result['summary'] is None


@pytest.mark.parametrize('statement,parameters', [
    ('DELETE FROM ReportData WHERE rowid=(SELECT MIN(rowid) FROM ReportData)', ()),
    ('INSERT INTO ReportData SELECT * FROM ReportData LIMIT 1', ()),
    ('UPDATE ReportData SET Value=?', (None,)),
    ('UPDATE ReportData SET Value=?', (float('inf'),)),
    ('UPDATE ReportData SET Value=?', (-1e9,)),
    ('UPDATE ReportData SET Value=?', ('12',)),
    ('DELETE FROM ReportDataDictionary WHERE Units=?', ('C',)),
    ('INSERT INTO ReportDataDictionary SELECT * FROM ReportDataDictionary LIMIT 1', ()),
    ('UPDATE ReportDataDictionary SET Units=? WHERE Units=?', ('kW', 'W')),
    ('UPDATE ReportDataDictionary SET TimestepType=?', ('HVAC System',)),
    ('UPDATE ReportDataDictionary SET ScheduleName=?', ('conditional',)),
    ('UPDATE ReportDataDictionary SET IsMeter=?', (1,)),
    ('UPDATE ReportDataDictionary SET Type=?', ('Sum',)),
    ('UPDATE ReportDataDictionary SET KeyValue=?', ('UNKNOWN',)),
    ('DELETE FROM Time WHERE Hour=?', (12,)),
    ('INSERT INTO Time SELECT * FROM Time LIMIT 1', ()),
    ('UPDATE Time SET Hour=? WHERE Hour=?', (11, 12)),
    ('UPDATE Time SET Minute=?', (60,)),
    ('UPDATE Time SET Interval=?', (30,)),
    ('UPDATE Time SET SimulationDays=?', (0,)),
    ('UPDATE Time SET Dst=?', (2,)),
    ('UPDATE Time SET Day=?', (32,)),
    ('UPDATE Time SET WarmupFlag=?', (1,)),
    ('UPDATE Zones SET Multiplier=?', (0,)),
    ('UPDATE Zones SET ListMultiplier=?', (float('inf'),)),
    ('UPDATE Zones SET ZoneName=?', ('UNKNOWN',)),
    ('INSERT INTO Zones SELECT * FROM Zones LIMIT 1', ()),
    ('UPDATE EnvironmentPeriods SET EnvironmentType=?', (2,)),
    ('INSERT INTO EnvironmentPeriods SELECT * FROM EnvironmentPeriods', ()),
    ('UPDATE Simulations SET CompletedSuccessfully=?', (0,)),
    ('UPDATE Simulations SET EnergyPlusVersion=?', ('EnergyPlus, Version 24.1.0',)),
])
def test_corruption_is_unavailable_not_zero_or_partial(hourly_files, statement, parameters):
    with sqlite3.connect(hourly_files[0]) as con:
        con.execute(statement, parameters)
    result = inspect_hourly_thermal(*hourly_files, environment_index=1)
    assert result['status'] == 'unavailable' and result['summary'] is None
    assert result['reason']


def test_views_cannot_impersonate_native_tables(hourly_files):
    with sqlite3.connect(hourly_files[0]) as con:
        con.execute('ALTER TABLE Zones RENAME TO OriginalZones')
        con.execute('CREATE VIEW Zones AS SELECT * FROM OriginalZones')
    result = inspect_hourly_thermal(*hourly_files, environment_index=1)
    assert result['status'] == 'unavailable' and 'physical tables' in result['reason']


def test_unbound_or_duplicate_model_zone_refused(hourly_files):
    hourly_files[1].write_text(hourly_files[1].read_text() + '\nZone,Invented;')
    result = inspect_hourly_thermal(*hourly_files, environment_index=1)
    assert result['status'] == 'unavailable' and result['summary'] is None


def test_truncated_weather_cannot_be_reported_as_annual(hourly_files):
    with sqlite3.connect(hourly_files[0]) as con:
        con.execute('UPDATE EnvironmentPeriods SET EnvironmentType=3')
    result = inspect_hourly_thermal(*hourly_files)
    assert result['status'] == 'unavailable' and result['summary'] is None
