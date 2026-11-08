"""Actual native projection plus hostile mutations; no new engine execution claimed."""
import json
import sqlite3
from pathlib import Path

import pytest

from backend.ideal_loads import inspect_ideal_loads, model_systems


@pytest.fixture
def native(tmp_path):
    raw=json.loads((Path(__file__).parents[1]/'fixtures/test/native_ideal_loads_projection.json').read_text())
    sql,model=tmp_path/'native.sql',tmp_path/'model.idf'
    with sqlite3.connect(sql) as con:
        for name,data in raw['tables'].items():
            con.execute('CREATE TABLE '+name+' ('+','.join('"'+c+'"' for c in data['columns'])+')')
            con.executemany('INSERT INTO '+name+' VALUES ('+','.join('?' for _ in data['columns'])+')',data['rows'])
    model.write_text(raw['model_idf'])
    return sql,model,raw


def inspect(native):return inspect_ideal_loads(*native[:2],environment_index=1)


def test_actual_native_includes_multiplier_and_matches_independent_balance(native):
    result=inspect(native);assert result['status']=='calculated_model_scenario',result.get('reason')
    summary=result['summary'];system=summary['systems'][0]
    assert summary['hour_count']==24 and system['zone_multiplier']==3 and system['zone_list_multiplier']==2
    for key,expected in native[2]['oracle']['expected_native_including_multipliers'].items():
        actual=summary['aggregate'][key]
        assert actual['peak']['value']==pytest.approx(expected,rel=.005,abs=2e-6 if key.endswith('kg_s') else 1.)
        if key.endswith('_W'):assert actual['energy_kWh']==pytest.approx(expected*24/1000,rel=.005,abs=.024)
        assert system['locators'][key]['scale_applied']==1
    assert summary['coverage']['uncovered_zones']==[] and summary['coverage']['other_equipment']==[]
    assert len(summary['peak_day_profiles'])==2
    # Declared water source is 320 W per zone. Native latent enthalpy delivery is different.
    assert summary['aggregate']['zone_latent_cooling_W']['peak']['value']!=pytest.approx(320*6,abs=1)


def test_design_day_requires_explicit_selection(native):
    r=inspect_ideal_loads(*native[:2]);assert r['status']=='unavailable' and r['summary'] is None


@pytest.mark.parametrize('sql,values',[
    ('DELETE FROM ReportData WHERE rowid=(SELECT MIN(rowid) FROM ReportData)',()),
    ('INSERT INTO ReportData SELECT * FROM ReportData LIMIT 1',()),
    ('UPDATE ReportData SET Value=?',(None,)),('UPDATE ReportData SET Value=?',(float('inf'),)),
    ('UPDATE ReportData SET Value=?',(-1.,)),('UPDATE ReportData SET Value=?',('1.2',)),
    ('DELETE FROM ReportDataDictionary WHERE Units=?',('kg/s',)),
    ('INSERT INTO ReportDataDictionary SELECT * FROM ReportDataDictionary LIMIT 1',()),
    ('UPDATE ReportDataDictionary SET Units=? WHERE Units=?',('kW','W')),
    ('UPDATE ReportDataDictionary SET TimestepType=?',('HVAC System',)),
    ('UPDATE ReportDataDictionary SET ScheduleName=?',('conditional',)),
    ('UPDATE ReportDataDictionary SET IsMeter=?',(1,)),
    ('UPDATE ReportDataDictionary SET Type=?',('Sum',)),
    ('UPDATE ReportDataDictionary SET KeyValue=?',('MISSING',)),
    ('DELETE FROM Time WHERE Hour=?',(12,)),('INSERT INTO Time SELECT * FROM Time LIMIT 1',()),
    ('UPDATE Time SET Minute=?',(30,)),('UPDATE Time SET Interval=?',(30,)),
    ('UPDATE Time SET WarmupFlag=?',(1,)),('UPDATE Time SET Dst=?',(2,)),
    ('UPDATE Time SET Day=?',(32,)),('UPDATE Zones SET Multiplier=?',(0,)),
    ('UPDATE Zones SET ListMultiplier=?',(float('inf'),)),('UPDATE Zones SET ZoneName=?',('UNKNOWN',)),
    ('INSERT INTO Zones SELECT * FROM Zones LIMIT 1',()),
    ('UPDATE EnvironmentPeriods SET EnvironmentType=?',(2,)),
    ('INSERT INTO EnvironmentPeriods SELECT * FROM EnvironmentPeriods',()),
    ('UPDATE Simulations SET CompletedSuccessfully=?',(0,)),
    ('UPDATE Simulations SET EnergyPlusVersion=?',('EnergyPlus, Version 24.1',)),
    ('UPDATE ReportData SET Value=100 WHERE ReportDataDictionaryIndex IN (SELECT ReportDataDictionaryIndex FROM ReportDataDictionary WHERE Name=?)',('Zone Ideal Loads Zone Total Cooling Rate',)),
])
def test_missing_or_conflicting_native_evidence_has_no_summary(native,sql,values):
    with sqlite3.connect(native[0]) as con:con.execute(sql,values)
    r=inspect(native);assert r['status']=='unavailable' and r['summary'] is None and r['reason']


def test_no_ideal_is_not_applicable_not_zero(native):
    text=native[1].read_text();text=';'.join(p for p in text.split(';') if not p.strip().startswith('ZoneHVAC:IdealLoadsAirSystem,'))
    native[1].write_text(text);r=inspect(native)
    assert r['status']=='not_applicable' and r['summary'] is None


@pytest.mark.parametrize('before,after',[
    ('Ideal,,Supply','Ideal,,Wrong supply'),
    ('ZoneHVAC:IdealLoadsAirSystem,Ideal,1,1','ZoneHVAC:IdealLoadsAirSystem,Absent,1,1'),
    ('ZoneHVAC:EquipmentConnections,Box,Equipment','ZoneHVAC:EquipmentConnections,Other zone,Equipment'),
    ('ZoneHVAC:EquipmentConnections,Box,Equipment','ZoneHVAC:EquipmentConnections,Box,Absent list'),
    ('Version,9.0','Version,9.6'),
])
def test_unbound_or_wrong_version_model_unavailable(native,before,after):
    text=native[1].read_text();assert before in text;native[1].write_text(text.replace(before,after));r=inspect(native)
    assert r['status']=='unavailable' and r['summary'] is None


def test_duplicate_equipment_binding_rejected(native):
    native[1].write_text(native[1].read_text().replace('Ideal,1,1;','Ideal,1,1,ZoneHVAC:IdealLoadsAirSystem,Ideal,2,2;'))
    assert inspect(native)['status']=='unavailable'


def test_nodelist_binding_and_other_equipment_scopes_are_explicit(native):
    text=native[1].read_text().replace('Box,Equipment,Supply,,','Box,Equipment,Inlets,,')
    text=text.replace('Ideal,1,1;','Ideal,1,1,ZoneHVAC:UnitHeater,Other heater,2,2;')+'NodeList,Inlets,Supply,Other supply;'
    native[1].write_text(text);zones,systems,other=model_systems(native[1])
    assert systems['IDEAL']['zone_name']=='BOX' and zones=={'BOX'} and other[0]['name']=='OTHER HEATER'
    r=inspect(native);assert r['summary']['coverage']['scope']=='declared_ideal_systems_only'
    assert len(r['summary']['coverage']['other_equipment'])==1


def test_views_cannot_impersonate_native_tables(native):
    with sqlite3.connect(native[0]) as con:
        con.execute('ALTER TABLE Zones RENAME TO HiddenZones');con.execute('CREATE VIEW Zones AS SELECT * FROM HiddenZones')
    assert inspect(native)['summary'] is None


def test_changed_source_withdraws_result(native,monkeypatch):
    import backend.ideal_loads as module
    real=module._read
    def changing(*args):
        result=real(*args);native[1].write_text(native[1].read_text()+'! source changed');return result
    monkeypatch.setattr(module,'_read',changing)
    result=inspect(native);assert result['status']=='unavailable' and result['summary'] is None


def test_actual_two_system_coincident_peak_is_not_sum_of_system_peaks(tmp_path):
    raw=json.loads((Path(__file__).parents[1]/'fixtures/test/native_ideal_coincident_projection.json').read_text())
    sql,model=tmp_path/'two.sql',tmp_path/'two.idf'
    with sqlite3.connect(sql) as con:
        for name,data in raw['tables'].items():
            con.execute('CREATE TABLE '+name+' ('+','.join('"'+c+'"' for c in data['columns'])+')')
            con.executemany('INSERT INTO '+name+' VALUES ('+','.join('?' for _ in data['columns'])+')',data['rows'])
    model.write_text(raw['model_idf']);r=inspect_ideal_loads(sql,model,environment_index=1)
    assert r['status']=='calculated_model_scenario',r.get('reason')
    summary=r['summary'];peak=summary['aggregate']['supply_total_cooling_W']['peak']['value']
    summed=sum(s['results']['supply_total_cooling_W']['peak']['value'] for s in summary['systems'])
    assert peak==pytest.approx(raw['oracle']['expected_coincident_supply_total_cooling_W'],abs=1)
    assert summed==pytest.approx(raw['oracle']['expected_sum_individual_peaks_W'],abs=1)
    assert peak<summed-1000
    for profile in summary['peak_day_profiles']:
        if 'cooling' in profile['selected_for']:
            assert profile['covered_systems']['supply_total_cooling_W']==pytest.approx([raw['oracle']['expected_coincident_supply_total_cooling_W']]*24,abs=1)


def test_two_systems_must_not_share_an_ambiguous_supply_node(tmp_path):
    raw=json.loads((Path(__file__).parents[1]/'fixtures/test/native_ideal_coincident_projection.json').read_text())
    model=tmp_path/'conflict.idf';model.write_text(raw['model_idf'].replace('Supply_B','Supply_A'))
    from backend.hourly_thermal import HourlyEvidenceError
    with pytest.raises(HourlyEvidenceError,match='ambiguous supply node'):model_systems(model)
