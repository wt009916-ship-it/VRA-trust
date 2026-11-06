"""Native SQL projection + independently declared heat balance + adversarial edits."""
import json
import sqlite3
from pathlib import Path

import pytest

from backend.design_loads import inspect_design_loads


@pytest.fixture
def sizing_files(tmp_path):
    fixture = json.loads((Path(__file__).resolve().parents[1] / 'fixtures/test/native_zone_sizing_projection.json').read_text())
    sql, model = tmp_path / 'native.sql', tmp_path / 'model.idf'
    with sqlite3.connect(sql) as con:
        for table, data in fixture['tables'].items():
            con.execute('CREATE TABLE "' + table + '" (' + ','.join('"' + c + '"' for c in data['columns']) + ')')
            con.executemany('INSERT INTO "' + table + '" VALUES (' + ','.join('?' for _ in data['columns']) + ')', data['rows'])
    model.write_text(fixture['model_idf'])
    return sql, model


def test_native_sizing_matches_independent_heat_balance(sizing_files):
    receipt = inspect_design_loads(*sizing_files)
    assert receipt['status'] == 'calculated_model_scenario', receipt.get('reason')
    assert receipt['tabular_crosscheck'] == 'matched_W_cells'
    assert receipt['building_coincident_peak_W'] is None
    assert receipt['site_applicability'] == 'requires_professional_review'
    for row in receipt['rows']:
        delta = 30 if row['load_type'] == 'Heating' else 10
        expected = 110 * delta / (1 / 10 + 2 + 1 / 25)
        assert abs(row['calculated_sensible_load_W'] - expected) < 1e-6
        assert row['multipliers_already_applied'] and row['locator']['unit'] == 'W'


@pytest.mark.parametrize('statement,parameters', [
    ('DELETE FROM ZoneSizes', ()),
    ('INSERT INTO ZoneSizes SELECT * FROM ZoneSizes LIMIT 1', ()),
    ("DELETE FROM ZoneSizes WHERE LoadType='Heating'", ()),
    ("UPDATE ZoneSizes SET CalcDesLoad=?", (-1,)),
    ("UPDATE ZoneSizes SET UserDesLoad=?", (float('inf'),)),
    ("UPDATE ZoneSizes SET CalcDesFlow=?", (None,)),
    ("UPDATE ZoneSizes SET PeakHumRat=?", (-.1,)),
    ("UPDATE ZoneSizes SET DesDayName=?", ('Invented station',)),
    ("UPDATE ZoneSizes SET ZoneName=?", ('Unknown zone',)),
    ("UPDATE ZoneSizes SET LoadType=?", ('Latent',)),
    ("UPDATE ZoneSizes SET PeakHrMin=?", ('7/21 25:00:00',)),
    ("UPDATE ZoneSizes SET PeakHrMin=?", ('7/21 24:01:00',)),
    ("UPDATE ZoneSizes SET PeakHrMin=?", ('2/30 14:00:00',)),
    ("UPDATE ZoneSizes SET ZoneSizesIndex=?", (1.5,)),
    ("UPDATE Zones SET Multiplier=?", (0,)),
    ("UPDATE Zones SET ZoneName=?", (None,)),
    ("UPDATE Zones SET FloorArea=?", (-1,)),
    ("INSERT INTO Zones SELECT * FROM Zones", ()),
    ("UPDATE Simulations SET EnergyPlusVersion=?", ('EnergyPlus, Version 24.1.0',)),
    ("UPDATE Simulations SET CompletedSuccessfully=?", (0,)),
    ("INSERT INTO Simulations SELECT * FROM Simulations", ()),
    ("UPDATE TabularDataWithStrings SET Units=? WHERE ColumnName='Calculated Design Load'", ('Btu/h',)),
    ("UPDATE TabularDataWithStrings SET Value=? WHERE ColumnName='User Design Load'", ('999999',)),
    ("INSERT INTO TabularDataWithStrings SELECT * FROM TabularDataWithStrings", ()),
    ("DELETE FROM TabularDataWithStrings", ()),
])
def test_sql_corruption_cannot_produce_loads(sizing_files, statement, parameters):
    with sqlite3.connect(sizing_files[0]) as con:
        con.execute(statement, parameters)
    receipt = inspect_design_loads(*sizing_files)
    assert receipt['status'] == 'unavailable'
    assert receipt['rows'] is None and receipt['building_coincident_peak_W'] is None
    assert receipt['reason']


@pytest.mark.parametrize('old,new', [
    ('Version,9.0;', 'Version,9.1;'),
    ('SimulationControl,Yes,', 'SimulationControl,No,'),
    ('Synthetic winter,1,21', 'Synthetic winter,2,30'),
    ('Synthetic winter,1,21', 'Synthetic winter,1.5,21'),
    ('Site:Location,Synthetic sea-level site,0,0,0,0;', ''),
    ('Site:Location,Synthetic sea-level site,0,0,0,0;', 'Site:Location,X,900,0,0,0;'),
    ('Synthetic summer,7,21', 'Unbound summer,7,21'),
    ('Zone,Box,', 'Zone,Changed,'),
    ('Version,9.0;', 'Version,9.0; SizingPeriod:WeatherFileDays,X,1,1,1,2;'),
])
def test_unbound_or_unsupported_model_does_not_invent_loads(sizing_files, old, new):
    model = sizing_files[1]
    text = model.read_text()
    assert old in text
    model.write_text(text.replace(old, new))
    receipt = inspect_design_loads(*sizing_files)
    assert receipt['status'] == 'unavailable' and receipt['rows'] is None


def test_coordinates_never_certify_design_day_source(sizing_files):
    station = {'city': 'Synthetic', 'latitude_deg': 0, 'longitude_deg': 0, 'utc_offset_h': 0, 'elevation_m': 0}
    quality = {'station': station, 'source_sha256': 'a' * 64}
    result = inspect_design_loads(*sizing_files, quality)
    assert result['site_comparison'] == 'coordinates_close_not_proof'
    assert result['site_applicability'] == 'requires_professional_review'
    station['latitude_deg'] = 30
    changed = inspect_design_loads(*sizing_files, quality)
    assert changed['site_comparison'] == 'declared_site_differs_from_weather'
    assert changed['rows'] == result['rows']  # Still the same model scenario, never relabelled a local design.


def test_unrequested_table_does_not_fabricate_crosscheck(sizing_files):
    model = sizing_files[1]
    model.write_text(model.read_text().replace('Output:Table:SummaryReports,HVACSizingSummary;', ''))
    with sqlite3.connect(sizing_files[0]) as con:
        con.execute('DELETE FROM TabularDataWithStrings')
    result = inspect_design_loads(*sizing_files)
    assert result['status'] == 'calculated_model_scenario'
    assert result['tabular_crosscheck'] == 'not_requested'


def test_legitimate_zero_is_distinct_from_absent(sizing_files):
    with sqlite3.connect(sizing_files[0]) as con:
        con.execute("UPDATE ZoneSizes SET CalcDesLoad=0,UserDesLoad=0,DesDayName='',PeakHrMin='' WHERE LoadType='Heating'")
        con.execute("UPDATE TabularDataWithStrings SET Value='0.00' WHERE TableName='Zone Sensible Heating' AND ColumnName IN ('Calculated Design Load','User Design Load')")
    result = inspect_design_loads(*sizing_files)
    assert result['status'] == 'calculated_model_scenario'
    row = next(r for r in result['rows'] if r['load_type'] == 'Heating')
    assert row['calculated_sensible_load_W'] == 0 and row['peak'] is None
