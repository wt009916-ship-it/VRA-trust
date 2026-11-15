"""Regression cases derived from the independent 2026-11-04 audit."""
import copy
import sqlite3

import pytest
from pydantic import ValidationError

from backend import core
from backend.input_validation import validate_epw, validate_idf, validate_hourly_rows, annual_hour_keys
from backend.robustness import Axis
from backend.spatial import Wall
from backend.trust import Factor


@pytest.mark.parametrize('mutation', [
    'UPDATE Time SET Interval=0 WHERE rowid=1',
    'UPDATE Time SET Hour=2 WHERE rowid=1',
    'UPDATE Time SET Day=32 WHERE Month=1 AND Day=1',
    'INSERT INTO Time SELECT * FROM Time WHERE rowid=1',
])
def test_corrupt_hourly_coverage_rejected(native_sql, mutation):
    with sqlite3.connect(native_sql) as con:
        con.execute(mutation)
    with pytest.raises(core.ValidationError):
        core.parse_sql(native_sql)


def test_compensated_interval_corruption_rejected(native_sql):
    with sqlite3.connect(native_sql) as con:
        con.execute('UPDATE Time SET Interval=0 WHERE rowid=1')
        con.execute('UPDATE Time SET Interval=120 WHERE rowid=2')
    with pytest.raises(core.ValidationError):
        core.parse_sql(native_sql)


def test_sql_conversion_overflow_is_rejected(native_sql):
    with sqlite3.connect(native_sql) as con:
        con.execute("UPDATE TabularDataWithStrings SET Value='1e308',Units='GJ' WHERE TableName='Site and Source Energy' AND RowName='Total Site Energy'")
    with pytest.raises(core.ValidationError, match='converted energy'):
        core.parse_sql(native_sql)


def test_free_text_is_not_reported_as_completed_engineering_task(client):
    from test_api import create_project
    from backend.agent import Chat
    pid = create_project(client)['project_id']
    task = client.app.state.agent.start(pid, Chat(message='Compute structural safety and remember room Q731'), background=False)
    assert task['answer']['workflow_completed'] is True
    assert task['answer']['task_completion'] == 'not_assessed'
    assert task['answer']['execution_scope'] == 'open_task_unverified'
    assert task['answer']['can_simulate'] is None
    assert not any(e['tool'] == 'evidence_validate' for e in task['events'])
    assert task['answer']['task_notice']


def test_leap_calendar_and_missing_hour():
    rows = [(*key, 60) for key in annual_hour_keys(True)]
    validate_hourly_rows(rows)
    with pytest.raises(core.ValidationError):
        validate_hourly_rows(rows[:-1])


@pytest.mark.parametrize('value', [True, False, '0.1'])
def test_no_implicit_engineering_number_coercion(value):
    with pytest.raises(ValidationError):
        Axis(material='test', values=[value, .2], source='audit source')
    with pytest.raises(ValidationError):
        Factor(value=value, source='audit source', factor_id='v1')
    with pytest.raises(ValidationError):
        Wall(id='w', x1=0, z1=0, x2=2, z2=0, thickness_m=value,
             evidence_id='test', source_locator='A-1', status='UNKNOWN')


def test_carbon_product_and_sum_overflow():
    profile = copy.deepcopy(core.get_profile('reference_scenario'))
    profile['factors']['Electricity']['value'] = 100
    with pytest.raises(core.ValidationError, match='carbon product'):
        core.calculate_carbon({'Electricity': 1e308}, profile, 'US-CO')
    for factor in profile['factors'].values():
        factor['value'] = 1
    with pytest.raises(core.ValidationError, match='carbon total'):
        core.calculate_carbon({'Electricity': 1e308, 'Natural Gas': 1e308}, profile, 'US-CO')


def test_header_only_and_negative_material_rejected(tmp_path):
    idf = tmp_path / 'broken.idf'
    idf.write_text('Version,9.0; Output:SQLite,SimpleAndTabular;')
    with pytest.raises(core.ValidationError, match='missing required'):
        validate_idf(idf)
    ref = core.ROOT / 'fixtures/demo/reference_5zone'
    from backend.robustness import set_conductivity
    idf.write_text(set_conductivity((ref / 'baseline.idf').read_text(), 'IN46', -1))
    with pytest.raises(core.ValidationError, match='Invalid Material'):
        validate_idf(idf)
    weather = tmp_path / 'broken.epw'
    weather.write_text('LOCATION,NOT_WEATHER')
    with pytest.raises(core.ValidationError):
        validate_epw(weather)
    lines = (ref / 'weather.epw').read_text().splitlines()
    lines[9] = lines[8]  # duplicate hour, total row count unchanged
    weather.write_text('\n'.join(lines))
    with pytest.raises(core.ValidationError):
        validate_epw(weather)


def test_provider_test_is_admin_only_and_does_not_execute_tools(client, monkeypatch):
    calls = []
    monkeypatch.setattr(client.app.state.gateway, 'complete', lambda *args, **response_options: {'tool_calls': [
        {'function': {'name': 'simulation_create', 'arguments': '{}'}}]})
    monkeypatch.setattr(client.app.state.agent, 'call', lambda *args: calls.append(args))
    response = client.post('/api/developer/provider/test')
    assert response.status_code == 200
    assert response.json()['tools_executed'] == 0 and not calls
    session = client.post('/api/auth/register', json={'username': 'member_audit', 'display_name': 'Member',
                          'password': 'Test-only-password-2026'}).json()
    client.headers['X-CSRF-Token'] = session['csrf_token']
    assert client.post('/api/developer/provider/test').status_code == 403


def test_gate_rejects_confirmed_header_only_model(client):
    from test_api import reference
    project = reference(client)['project_id']
    domain = client.app.state.domain
    ev = next(e for e in domain.store.list('evidence', project) if e['type'] == 'idf' and e['scheme_id'] == 'baseline')
    client.patch(f'/api/projects/{project}/evidence/{ev["evidence_id"]}', json={
        'expected_revision': 1, 'review_state': 'rejected', 'responsible_person': 'test', 'review_note': 'Replace with malformed test'})
    f = client.post(f'/api/projects/{project}/files', files={'file': ('broken.idf', b'Version,9.0; Output:SQLite,SimpleAndTabular;')}).json()
    body = {k: ev[k] for k in ['type', 'name', 'source_locator', 'authority', 'permission', 'acquisition_method', 'responsible_person', 'status', 'scheme_id']}
    body['source_file'] = f['file_id']
    new_ev = client.post(f'/api/projects/{project}/evidence', json=body).json()
    client.patch(f'/api/projects/{project}/evidence/{new_ev["evidence_id"]}', json={
        'expected_revision': 1, 'review_state': 'confirmed', 'responsible_person': 'test', 'review_note': 'Intentional malformed test'})
    gate = client.get(f'/api/projects/{project}/gate').json()
    assert not gate['can_simulate']
    assert any(b['code'] == 'INVALID_SOURCE' and b['field'] == 'idf' for b in gate['blockers'])
