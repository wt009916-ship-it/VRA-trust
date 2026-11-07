"""First independent synthetic load probe. New files only; no product changes."""
import hashlib
import json
import sqlite3
import sys
import tempfile
import uuid
from pathlib import Path

repo = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo))
from backend.execution import Policy, supervise
from backend.private_storage import private_mkdir

root = Path(tempfile.gettempdir()) / ('vra-designload-probe-' + uuid.uuid4().hex)
private_mkdir(root)
for name in ('logs', 'output'):
    private_mkdir(root / name)
objects = []
def obj(kind, *fields):
    objects.append(kind + ',' + ','.join(map(str, fields)) + ';')

obj('Version', '9.0')
obj('Timestep', 6)
obj('Building', 'Synthetic steady box', 0, 'Suburbs', .0001, .0001, 'MinimalShadowing', 100, 10)
obj('HeatBalanceAlgorithm', 'ConductionTransferFunction')
obj('SimulationControl', 'Yes', 'No', 'No', 'Yes', 'No')
obj('Site:Location', 'Synthetic sea-level site', 0, 0, 0, 0)
for name, month, kind, temperature, dew in [('Synthetic winter', 1, 'WinterDesignDay', -10, -10),
                                          ('Synthetic summer', 7, 'SummerDesignDay', 35, 10)]:
    obj('SizingPeriod:DesignDay', name, month, 21, kind, temperature, 0, '', '',
        'Dewpoint', dew, '', '', '', '', 101325, 0, 0, 'No', 'No', 'No',
        'ASHRAEClearSky', '', '', '', '', 0)
obj('GlobalGeometryRules', 'UpperLeftCorner', 'Counterclockwise', 'World')
obj('Zone', 'Box', 0, 0, 0, 0, 1, 1, 3, 75, 25)
obj('Material:NoMass', 'R2', 'Smooth', 2, .9, .7, .7)
obj('Construction', 'Envelope', 'R2')
obj('SurfaceProperty:OtherSideCoefficients', 'Ambient', 25, 0, 0, 1, 0, 0, 0)
faces = [
    ('South', 'Wall', [(0,0,3),(0,0,0),(5,0,0),(5,0,3)]),
    ('East', 'Wall', [(5,0,3),(5,0,0),(5,5,0),(5,5,3)]),
    ('North', 'Wall', [(5,5,3),(5,5,0),(0,5,0),(0,5,3)]),
    ('West', 'Wall', [(0,5,3),(0,5,0),(0,0,0),(0,0,3)]),
    ('Roof', 'Roof', [(0,5,3),(0,0,3),(5,0,3),(5,5,3)]),
    ('Floor', 'Floor', [(0,0,0),(0,5,0),(5,5,0),(5,0,0)])]
for name, kind, points in faces:
    obj('BuildingSurface:Detailed', name, kind, 'Envelope', 'Box', 'OtherSideCoefficients',
        'Ambient', 'NoSun', 'NoWind', 0, 4, *[v for p in points for v in p])
    obj('SurfaceProperty:ConvectionCoefficients', name, 'Inside', 'Value', 10)
obj('ScheduleTypeLimits', 'Any')
for name, value in [('Heat', 20), ('Cool', 25), ('Control', 4)]:
    obj('Schedule:Constant', name, 'Any', value)
obj('ThermostatSetpoint:DualSetpoint', 'Setpoints', 'Heat', 'Cool')
obj('ZoneControl:Thermostat', 'Control', 'Box', 'Control', 'ThermostatSetpoint:DualSetpoint', 'Setpoints')
obj('Sizing:Parameters', 1, 1, 1)
obj('Sizing:Zone', 'Box', 'SupplyAirTemperature', 12, '', 'SupplyAirTemperature', 50, '',
    .008, .008, 'NoOA', 1, 1, 'DesignDay', 0, 0, 0, 0, 'DesignDay', 0, 0, 0, 0)
obj('DesignSpecification:OutdoorAir', 'NoOA', 'Flow/Zone', 0, 0, 0, 0)
obj('ZoneHVAC:EquipmentConnections', 'Box', 'Equipment', 'Supply', '', 'Zone air', 'Return')
obj('ZoneHVAC:EquipmentList', 'Equipment', 'SequentialLoad', 'ZoneHVAC:IdealLoadsAirSystem', 'Ideal', 1, 1)
obj('ZoneHVAC:IdealLoadsAirSystem', 'Ideal', '', 'Supply', '', '', 50, 12, .009, .009,
    'NoLimit', '', '', 'NoLimit', '', '', '', '', 'None', '', 'None')
obj('Output:SQLite', 'SimpleAndTabular')
obj('Output:Table:SummaryReports', 'HVACSizingSummary')
for name in ['Site Outdoor Air Drybulb Temperature', 'Zone Mean Air Temperature',
             'Surface Inside Face Convection Heat Transfer Coefficient',
             'Surface Inside Face Net Surface Thermal Radiation Heat Gain Rate',
             'Surface Inside Face Temperature', 'Surface Outside Face Temperature',
             'Zone Ideal Loads Zone Sensible Heating Rate', 'Zone Ideal Loads Zone Sensible Cooling Rate']:
    obj('Output:Variable', '*', name, 'Hourly')
model = root / 'input.idf'
model.write_text('! Synthetic independent heat balance benchmark, not a real building.\n' + '\n'.join(objects), encoding='ascii')
expected = {'Heating': 110 * 30 / (1 / 10 + 2 + 1 / 25), 'Cooling': 110 * 10 / (1 / 10 + 2 + 1 / 25)}
record = {'root': str(root), 'model_sha256': hashlib.sha256(model.read_bytes()).hexdigest(),
          'scope': 'exploratory independent synthetic benchmark, not delivered product capability',
          'expected_W': expected, 'tolerance': 'max(1 W, expected*0.005), set before run',
          'status': 'not_started'}
receipt = Path(__file__).parent / 'steady-probe-v1.json'
assert not receipt.exists()
try:
    record['execution'] = supervise(['F:/EnergyPlusV9-0-1/energyplus.exe', '-d', str(root / 'output'), str(model)],
                                   root, root / 'logs', Policy(), 60, output=root / 'output')
    with sqlite3.connect('file:' + (root/'output/eplusout.sql').as_posix() + '?mode=ro', uri=True) as con:
        con.row_factory = sqlite3.Row
        record['sizes'] = [dict(row) for row in con.execute('SELECT * FROM ZoneSizes')]
        record['conditions'] = [dict(row) for row in con.execute('''SELECT e.EnvironmentName,d.Name,d.KeyValue,d.Units,
            COUNT(*) n,MIN(r.Value) minimum,MAX(r.Value) maximum FROM ReportData r
            JOIN ReportDataDictionary d USING(ReportDataDictionaryIndex) JOIN Time t USING(TimeIndex)
            JOIN EnvironmentPeriods e USING(EnvironmentPeriodIndex)
            WHERE e.EnvironmentType=1 AND COALESCE(t.WarmupFlag,0)=0
            GROUP BY e.EnvironmentName,d.Name,d.KeyValue,d.Units''')]
    record['load_checks'] = [{'type': row['LoadType'], 'expected': expected[row['LoadType']],
       'actual': row['CalcDesLoad'], 'absolute_error': abs(row['CalcDesLoad'] - expected[row['LoadType']]),
       'within_tolerance': abs(row['CalcDesLoad'] - expected[row['LoadType']]) <= max(1, expected[row['LoadType']] * .005)}
       for row in record['sizes']]
    record['status'] = 'ran; load checks recorded, boundary review still required'
except Exception as exc:
    record['status'] = 'failed'
    record['error'] = type(exc).__name__ + ': ' + str(exc)
    record['execution'] = getattr(exc, 'receipt', record.get('execution'))
finally:
    with receipt.open('x', encoding='utf-8') as stream:
        json.dump(record, stream, indent=2)
print(json.dumps({k: v for k, v in record.items() if k not in {'conditions', 'execution'}}))
if record['status'] == 'failed':
    raise SystemExit(1)
