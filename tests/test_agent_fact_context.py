"""Dimension and scope meaning, checked through real calculator and read APIs."""
from fractions import Fraction

import pytest

from backend import agent_missing, agent_requests
from backend.agent_semantics import facts, model_projection, readable, Statement
from test_api import create_project
from test_agent_professional import create_record, thermal_input


@pytest.mark.parametrize('floor_area', [17., 1700.])
def test_thermal_area_normalization_is_intrinsic_not_missing_floor_area(client, floor_area):
    p = create_project(client)
    changed = client.put(f"/api/projects/{p['project_id']}/building",
        json={'expected_revision': p['revision'], 'building': {**p['building'], 'area_m2': floor_area}})
    assert changed.status_code == 200
    body = thermal_input()
    body['layers'][0].update(thickness=150., conductivity=.6)
    r = create_record(client, p['project_id'], 'thermal', body)
    # .12 + .05 + .15/.6 + .06/(.03*1.25) = 2.02, independent of floor area.
    expected = Fraction(101, 50)
    values = {f['fact']: f for f in facts(r, 'thermal')}
    assert float(values['total_resistance_m2k_w']['value']) == pytest.approx(float(expected))
    assert float(values['u_w_m2k']['value']) == pytest.approx(float(1 / expected))
    assert all(f['area_m2'] is None and f['area_basis'] == 'intrinsic_area_normalized_property' for f in values.values())
    projected = model_projection(readable(r, 'thermal'), 'thermal')
    assert projected['calculation_context']['area_basis'] == 'intrinsic_area_normalized_property'
    assert projected['calculation_context']['resistance_definition'] == 'R=sum(d/lambda_effective)+Rsi+Rse; m2 K/W'
    description = Statement.model_json_schema()['properties']['area_m2']['description']
    assert '不是总量' in description and '面积分母' in description and 'area_basis' in description


def test_lifecycle_total_and_area_intensity_share_period_but_not_denominator(client):
    pid = create_project(client)['project_id']
    r = create_record(client, pid, 'lifecycle')
    f = {x['fact']: x for x in facts(r, 'lifecycle')}
    total, intensity = f['boundary_total_kgco2e'], f['kgco2e_m2_over_study_period']
    assert total['area_m2'] is None and total['area_basis'] == 'no_area_normalization'
    assert intensity['area_m2'] == 927.2 and intensity['area_basis'] == 'explicit_area_denominator'
    # 1597.6 kg / 927.2 m2 over 12 years; do not divide by 12 again.
    assert float(intensity['value']) == pytest.approx(float(Fraction(7988, 4636)), rel=1e-10)
    assert all(x['study_years'] == 12 and x['time_basis'] == 'whole_study_period_not_annual' for x in f.values())
    assert 'stage.construction' not in f
    c = model_projection(readable(r, 'lifecycle'), 'lifecycle')['calculation_context']
    assert c['excluded_stages'] == ['construction'] and c['area_m2'] == 927.2


@pytest.mark.parametrize('existing', [False, True])
def test_catalog_availability_does_not_infer_history_or_numeric_validity(client, existing):
    pid = create_project(client)['project_id']
    if existing:
        body = thermal_input()
        body['rsi_m2k_w'] = None
        record = create_record(client, pid, 'thermal', body)
        assert record['status'] == 'incomplete'
    request = {'request_key': 'wall_presence', 'kind': 'thermal', 'purpose': 'availability', 'record_id': None}
    result = agent_requests.availability(client.app.state.domain, pid, [request], ['wall_presence'])
    row = result['references'][0]['availability']
    assert row['state'] == ('records_present' if existing else 'no_record_available')
    assert row['knowledge_limits'] == {
        'historical_calculation': 'not_assessed', 'current_numeric_validity': 'not_assessed',
        'application_capability': 'not_assessed', 'building_data_sufficiency': 'not_assessed'}
    assert not {'explanation_facts', 'result'} & row.keys()
    absent = agent_missing.assess(client.app.state.domain, pid,
                                 agent_missing.Missing(kind='thermal', record_id='thermal_' + 'a' * 32))
    assert absent['missing']['knowledge_limits'] == row['knowledge_limits']
    assert absent['missing']['scope'] == 'requested_record_in_project'
