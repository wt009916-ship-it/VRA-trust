"""Independent adversarial weather contract; all variations preserve their source."""
import csv
import hashlib
import io

import pytest

from backend import core
from backend.input_validation import validate_epw


@pytest.fixture
def weather_rows():
    path = core.ROOT / 'fixtures/demo/reference_5zone/weather.epw'
    return list(csv.reader(io.StringIO(path.read_text(encoding='utf-8-sig'))))


def save_weather(tmp_path, rows):
    path = tmp_path / 'variation.epw'
    with path.open('w', encoding='utf-8', newline='') as stream:
        csv.writer(stream).writerows(rows)
    return path


@pytest.mark.parametrize('row,column,value', [
    (0, 6, '900'), (0, 7, '-181'), (0, 8, '13'), (0, 9, 'NaN'),
    (8, 6, '99.9'), (8, 6, '-70'), (8, 6, '70'), (8, 7, '99.9'),
    (8, 8, '999'), (8, 8, '-1'), (8, 8, '111'),
    (8, 9, '-1'), (8, 9, '101.325'), (8, 9, '31000'), (8, 9, '120000'),
    (8, 14, 'NaN'), (8, 14, '9999'), (8, 14, '-1'), (8, 15, 'inf'),
    (8, 15, '9999'), (8, 20, '361'), (8, 21, '41'), (8, 21, '999'),
    (8, 23, '11'), (8, 24, 'nan'), (8, 26, '1'), (8, 27, 'bogus'),
    (8, 30, '-1'), (8, 32, '1.1'), (8, 33, '-1'), (8, 4, '30'),
    (8, 0, 'NaN'), (7, 5, '2/1'), (7, 4, 'Someday'),
])
def test_invalid_weather_rejected_with_locator(tmp_path, weather_rows, row, column, value):
    weather_rows[row][column] = value
    with pytest.raises(core.ValidationError, match=r'EPW.*(?:line|行)'):
        validate_epw(save_weather(tmp_path, weather_rows))


def test_receipt_bound_to_original_bytes():
    path = core.ROOT / 'fixtures/demo/reference_5zone/weather.epw'
    before = path.read_bytes()
    result = validate_epw(path)
    assert result['source_sha256'] == hashlib.sha256(before).hexdigest()
    assert result['hours'] == 8760 and result['status'] == 'accepted_with_conditions'
    assert result['station']['latitude_deg'] == 39.74
    assert result['policy_version'] and result['validator_sha256']
    assert result['conditions'] and result['application_imputation_count'] == 0
    assert path.read_bytes() == before


def test_ir_derivation_requires_present_opaque_cover(tmp_path, weather_rows):
    weather_rows[8][12] = '9999'
    path = save_weather(tmp_path, weather_rows)
    receipt = validate_epw(path)
    item = next(x for x in receipt['conditions'] if x['code'] == 'NATIVE_SKY_DERIVATION')
    assert item['count'] == 1 and item['first_line'] == 9
    weather_rows[8][23] = '99'
    with pytest.raises(core.ValidationError, match='opaque_sky_cover'):
        validate_epw(save_weather(tmp_path, weather_rows))


def test_ignored_missing_is_visible_not_zero(tmp_path, weather_rows):
    weather_rows[8][10] = '9999'
    receipt = validate_epw(save_weather(tmp_path, weather_rows))
    item = next(x for x in receipt['conditions'] if x['field'] == 'extraterrestrial_horizontal_radiation')
    assert item['code'] == 'UNUSED_FIELD_MISSING' and item['count'] >= 1
    assert receipt['fields']['extraterrestrial_horizontal_radiation']['missing_count'] >= 1


def test_mixed_minute_conventions_rejected(tmp_path, weather_rows):
    weather_rows[8][4] = '60'
    with pytest.raises(core.ValidationError, match='minute'):
        validate_epw(save_weather(tmp_path, weather_rows))


def test_hourly_60_minute_convention_supported(tmp_path, weather_rows):
    for row in weather_rows[8:]:
        row[4] = '60'
    receipt = validate_epw(save_weather(tmp_path, weather_rows))
    assert receipt['minute_convention'] == 60


def test_leap_day_header_conflict_rejected(tmp_path, weather_rows):
    feb28 = [row.copy() for row in weather_rows[8:] if row[1:3] == ['2', '28']]
    for row in feb28:
        row[2] = '29'
    index = next(i for i, row in enumerate(weather_rows[8:], 8) if row[1:3] == ['3', '1'])
    weather_rows[index:index] = feb28
    with pytest.raises(core.ValidationError, match='LeapYear'):
        validate_epw(save_weather(tmp_path, weather_rows))
    weather_rows[4][1] = 'Yes'
    assert validate_epw(save_weather(tmp_path, weather_rows))['hours'] == 8784


@pytest.mark.parametrize('column,value', [(0, '9' * 5000), (1, '١'), (6, '1_000'), (26, '0.0')])
def test_foreign_numeric_syntax_rejected(tmp_path, weather_rows, column, value):
    weather_rows[8][column] = value
    with pytest.raises(core.ValidationError, match='EPW line 9'):
        validate_epw(save_weather(tmp_path, weather_rows))


@pytest.mark.parametrize('row,column,value', [(8, 6, '99.9'), (8, 8, '999'), (8, 9, '-1'),
                                            (8, 14, 'NaN'), (0, 6, '900')])
def test_authenticated_gate_blocks_original_counterexamples(client, tmp_path, weather_rows, monkeypatch, row, column, value):
    from test_api import reference
    pid = reference(client)['project_id']
    domain = client.app.state.domain
    original = next(e for e in domain.store.list('evidence', pid) if e['type'] == 'epw')
    url = '/api/projects/' + pid
    rejected = client.patch(url + '/evidence/' + original['evidence_id'], json={
        'expected_revision': 1, 'review_state': 'rejected', 'responsible_person': 'Test reviewer',
        'review_note': 'Replace with deliberately malformed synthetic weather'})
    assert rejected.status_code == 200
    weather_rows[row][column] = value
    raw = save_weather(tmp_path, weather_rows).read_bytes()
    file = client.post(url + '/files', files={'file': ('counterexample.epw', raw)})
    assert file.status_code == 201
    keys = ['type', 'name', 'source_locator', 'authority', 'permission', 'acquisition_method', 'responsible_person', 'status']
    body = {key: original[key] for key in keys}
    body['source_file'] = file.json()['file_id']
    assert client.post(url + '/evidence', json=body).status_code == 201
    # Confirm only non-rejected evidence; no reactivation of original versions.
    for evidence in domain.store.list('evidence', pid):
        if evidence['review_state'] == 'pending':
            assert client.patch(url + '/evidence/' + evidence['evidence_id'], json={
                'expected_revision': evidence['revision'], 'review_state': 'confirmed',
                'responsible_person': 'Test reviewer', 'review_note': 'Intentional malformed input test'}).status_code == 200
    gate = client.get(url + '/gate').json()
    assert not gate['can_simulate'] and gate['weather_quality'] is None
    assert any(b['code'] == 'INVALID_SOURCE' and b['field'] == 'epw' for b in gate['blockers'])
    monkeypatch.setattr(core, 'engine_path', lambda: pytest.fail('Rejected weather reached the engine'))
    assert client.post('/api/runs', json={'project_id': pid, 'scheme_id': 'baseline'}).status_code == 409
    assert client.get(url + '/runs').json() == []
    assert client.get(url + '/files/' + file.json()['file_id']).content == raw


def test_direct_core_has_no_weather_bypass(tmp_path, weather_rows, monkeypatch):
    import copy
    weather_rows[8][14] = '9999'
    path = save_weather(tmp_path, weather_rows)
    (tmp_path / 'baseline.idf').write_bytes((core.ROOT / 'fixtures/demo/reference_5zone/baseline.idf').read_bytes())
    engine = tmp_path / 'engine.exe'
    engine.write_bytes(b'not executed')
    monkeypatch.setattr(core, 'engine_path', lambda: engine)
    monkeypatch.setattr(core.execution, 'supervise', lambda *a, **k: pytest.fail('Invalid weather executed native code'))
    case = copy.deepcopy(core.load_case('reference_5zone'))
    case['weather'] = path.name
    case['schemes'][0]['model'] = 'baseline.idf'
    result = core.run_simulation('reference_5zone', 'baseline', 'reference_scenario', tmp_path / 'run_invalid',
                                 case_override=case, file_root=tmp_path)
    assert result['status'] == 'failed' and result['metrics'] is None
    manifest = core.read_json(tmp_path / 'run_invalid/manifest.json')
    assert manifest['engine_calls_executed'] == 0 and 'version_resources' not in manifest
    assert (tmp_path / 'run_invalid/input/weather.epw').read_bytes() == path.read_bytes()
