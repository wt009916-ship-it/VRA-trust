import csv
from datetime import datetime, timedelta, timezone

import pytest

from backend import core
from backend.plant_calibration import PlantFit, analyze_plant
from test_model_workbench import project, upload


def settings(**kw):
    return PlantFit(**{**dict(file_id='file', building_ref='Synthetic unit test building', equipment_ref='test chiller',
        boundary='chiller_electricity', source_nature='simulation', source_note='Synthetic test only; no actual field calibration approval.',
        timestamp_column='time', power_column='p', cooling_column='q', flow_column='flow', return_temperature_column='ret',
        supply_temperature_column='supply', condenser_temperature_column='cond', power_unit='kW', cooling_unit='kW', flow_unit='m3/s',
        temperature_unit='C', interval_seconds=300, fluid_density_kg_m3=1000, fluid_heat_capacity_j_kgk=4000,
        balance_tolerance_percent=10, holdout_start='2024-01-01T05:00:00Z'), **kw})


def fixture(path, transform=None):
    with path.open('w', newline='') as f:
        w=csv.DictWriter(f, fieldnames=['time','p','q','flow','ret','supply','cond']);w.writeheader()
        for i in range(100):
            q=200+(i*73 % 800);lift=15+(i*7 % 20);p=10+.08*q+.00005*q*q+.002*q*lift
            row=dict(time=(datetime(2024,1,1,tzinfo=timezone.utc)+timedelta(minutes=5*i)).isoformat(),p=p,q=q,flow=q/20000,ret=12,supply=7,cond=7+lift)
            if transform:transform(row,i)
            w.writerow(row)
    return path


def test_recovers_independent_coefficients_and_keeps_holdout_error(tmp_path):
    path=fixture(tmp_path/'plant.csv')
    result,rows=analyze_plant(path,settings())
    assert result['status']=='candidate_requires_engineer_review'
    assert result['fit']['coefficients']==pytest.approx([10,80,50,20])
    assert result['fit']['holdout']['n']==40 and result['fit']['holdout']['cvrmse_percent']<1e-10
    assert 'measured_kwh' not in result['fit']['holdout'] and not result['calibrated']
    # Perturb only future measurements: fitted coefficients must be unchanged.
    path=fixture(path,lambda r,i:r.update(p=r['p']*1.2) if i>=60 else None)
    changed,_=analyze_plant(path,settings())
    assert changed['fit']['coefficients']==pytest.approx(result['fit']['coefficients'])
    assert changed['fit']['holdout']['cvrmse_percent']>10
    assert len(rows)==100 and result['imputed_rows']==0


def test_unit_mismatch_never_auto_multiplies_flow(tmp_path):
    path=fixture(tmp_path/'plant.csv',lambda r,i:r.update(flow=r['flow']/60))
    r,rows=analyze_plant(path,settings())
    assert r['balance_failed_rows']==100 and r['status']=='blocked' and r['fit']
    assert r['balance_error_median_percent']==pytest.approx(100*(1-1/60))
    assert rows[0]['water_heat_kw']==pytest.approx(rows[0]['cooling_kw']/60)


@pytest.mark.parametrize('bad',['nan','bad',1e308,-1])
def test_bad_rows_retained_not_repaired(tmp_path,bad):
    path=fixture(tmp_path/'plant.csv',lambda r,i:r.update(p=bad) if i==3 else None)
    r,rows=analyze_plant(path,settings())
    assert len(rows)==100 and r['excluded_rows']==1 and r['status']=='blocked'
    assert rows[3]['flags'] and 'predicted_power_kw' not in rows[3]


def test_duplicate_times_refuse_and_missing_times_not_filled(tmp_path):
    path=fixture(tmp_path/'plant.csv',lambda r,i:r.update(time='2024-01-01T00:00:00Z') if i==3 else None)
    r,_=analyze_plant(path,settings());assert r['fit'] is None and r['issues']['duplicate_timestamps']==1
    path=fixture(path,lambda r,i:r.update(time=r['time'].replace('+00:00','')))
    r,_=analyze_plant(path,settings());assert r['fit'] is None and r['valid_operating_rows']==0


def test_constant_conditions_not_identifiable(tmp_path):
    path=fixture(tmp_path/'plant.csv',lambda r,i:r.update(q=500,flow=.025,cond=30))
    r,_=analyze_plant(path,settings());assert r['fit'] is None and r['status']=='blocked'


def test_source_rules_binding_project_ownership_and_audit_pagination(client,tmp_path):
    pid=project(client);path=fixture(tmp_path/'plant.csv');fid=upload(client,pid,'plant.csv',path.read_bytes())
    base=f'/api/projects/{pid}/calibrations';r=client.post(base,json=settings(file_id=fid).model_dump())
    assert r.status_code==201,r.text
    key=r.json()['calibration_id'];assert client.get(base+'/'+key+'/rows').json()['total']==100
    other=project(client);assert client.get(f'/api/projects/{other}/calibrations/'+key).status_code==404
    assert client.get(base+'/'+key+'/rows?page=0').status_code==409
    record=client.app.state.domain.store.get('calibration',key)
    record['rules_hash']='0'*64
    client.app.state.domain.store.put('calibration',record,record['revision'])
    assert client.get(base+'/'+key).status_code==409
    with pytest.raises(core.ValidationError):analyze_plant(path,settings(power_column='q'))
