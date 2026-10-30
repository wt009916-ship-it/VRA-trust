"""Weather quality and API boundaries. Synthetic values here are unit-test inputs only."""
import copy
import csv
import io
from datetime import date, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from backend import core
from backend.agent import Chat
from backend.weather import AnalysisOptions, NASARequest, NASA_FIELDS, analyze_epw, analyze_nasa


def reference_path():
    return core.relative_file(core.ROOT, core.load_case('reference_5zone')['weather'])


def epw_variant(tmp_path, change):
    lines = list(csv.reader(io.StringIO(reference_path().read_text())))
    change(lines)
    path = tmp_path / 'modified.epw'
    with path.open('w', newline='') as f:
        csv.writer(f).writerows(lines)
    return path


def nasa_fixture(options):
    """Deliberately uniform test data; never used as product fallback."""
    keys = [(options.start+timedelta(days=n)).strftime('%Y%m%d') for n in range((options.end-options.start).days+1)]
    values = dict(T2M=21, T2M_MIN=18, T2M_MAX=24, RH2M=55, WS10M=3, ALLSKY_SFC_SW_DWN=3, PRECTOTCORR=2)
    return {'header': {'time_standard': 'LST', 'start': options.start.strftime('%Y%m%d'), 'end': options.end.strftime('%Y%m%d'), 'fill_value': -999},
            'geometry': {'coordinates': [options.longitude, options.latitude, 20]},
            'parameters': {k: {'units': v[1]} for k, v in NASA_FIELDS.items()},
            'properties': {'parameter': {k: dict.fromkeys(keys, v) for k, v in values.items()}}}


def nasa_options(**changes):
    return NASARequest(**dict(latitude=30.59, longitude=114.3, start=date(2025, 1, 1), end=date(2025, 12, 31), label='Synthetic test only', **changes))


def project(client):
    return client.post('/api/projects', json={'name': 'Weather test only', 'building': {'use': 'office', 'location': 'Test', 'region': 'CN-HB', 'area_m2': 100}}).json()['project_id']


def test_official_epw_legacy_hourly_and_modern_minutes(tmp_path):
    old = analyze_epw(reference_path(), AnalysisOptions())
    modern = analyze_epw(epw_variant(tmp_path, lambda lines: [r.__setitem__(4, '60') for r in lines[8:]]), AnalysisOptions())
    assert old['quality']['simulation_candidate'] and modern['quality']['simulation_candidate']
    assert old['quality']['records'] == 8760 and len(old['heatmap']) == 288
    assert len(old['daily']) == 365
    assert old['annual'] == modern['annual']
    assert old['annual']['solar_kwh_m2'] == pytest.approx(1619.948)
    assert old['rows'][0]['source_minute'] == 0 and modern['rows'][0]['source_minute'] == 60


@pytest.mark.parametrize('column,value,field,annual', [(6, '99.9', 'temperature_c', 'heating_degree_days'), (6, 'NaN', 'temperature_c', 'temperature_c'), (13, '9999', 'ghi_wh_m2', 'solar_kwh_m2'), (8, '999', 'humidity_pct', None), (21, '-1', 'wind_m_s', None), (12, '9999', 'infrared_wh_m2', None)])
def test_epw_missing_not_zero(tmp_path, column, value, field, annual):
    data = analyze_epw(epw_variant(tmp_path, lambda lines: lines[8].__setitem__(column, value)), AnalysisOptions())
    assert not data['quality']['simulation_candidate']
    assert data['quality']['invalid_fields'][field] == 1
    assert data['rows'][0][field] is None
    if annual:
        assert data['annual'][annual] is None


def test_epw_gap_duplicate_order_subhour_and_mixed_minutes(tmp_path):
    changes = [lambda ls: ls.pop(8), lambda ls: ls.__setitem__(9, ls[8][:]), lambda ls: ls.__setitem__(slice(8, 10), [ls[9], ls[8]]), lambda ls: ls[7].__setitem__(2, '2'), lambda ls: ls[8].__setitem__(4, '30'), lambda ls: ls[8].__setitem__(4, '60')]
    for change in changes:
        result = analyze_epw(epw_variant(tmp_path, change), AnalysisOptions())
        assert not result['quality']['simulation_candidate'], change
    missing_day = analyze_epw(epw_variant(tmp_path, lambda ls: ls.__delitem__(slice(8,32))), AnalysisOptions())
    assert missing_day['monthly'][0]['solar_kwh_m2'] is None
    assert missing_day['annual']['temperature_c'] is None
    duplicate = analyze_epw(epw_variant(tmp_path, lambda ls: ls.__setitem__(9,ls[8][:])), AnalysisOptions())
    assert duplicate['daily'][0]['temperature_c'] is None
    assert duplicate['daily'][0]['solar_kwh_m2'] is None
    assert duplicate['monthly'][0]['valid_temperature_days'] == 30


def test_leap_epw_and_original_year_kept(tmp_path):
    def leap(ls):
        march = next(i for i, r in enumerate(ls[8:],8) if r[1:3] == ['3','1'])
        extra = copy.deepcopy(ls[march-24:march])
        for r in extra:
            r[1:3] = ['02','29']
        ls[march:march] = extra
    data = analyze_epw(epw_variant(tmp_path, leap), AnalysisOptions())
    assert data['quality']['simulation_candidate'] and data['quality']['records'] == 8784
    assert len(data['daily']) == 366
    assert data['rows'][0]['date'] == '2000-01-01' and data['rows'][0]['source_year'] == 1999


def test_nasa_annual_arithmetic_missing_partial_and_zero():
    options = nasa_options()
    raw = nasa_fixture(options)
    data = analyze_nasa(raw, options)
    assert data['annual'] == dict(temperature_c=21, heating_degree_days=0, cooling_degree_days=0, solar_kwh_m2=1095)
    assert not data['quality']['simulation_candidate']
    raw['properties']['parameter']['T2M']['20250101'] = -999
    raw['properties']['parameter']['RH2M']['20250101'] = True
    damaged = analyze_nasa(raw, options)
    assert damaged['annual']['temperature_c'] is None and damaged['annual']['heating_degree_days'] is None
    assert damaged['rows'][0]['humidity_pct'] is None
    assert damaged['monthly'][0]['valid_temperature_days'] == 30
    options = options.model_copy(update={'end': date(2025, 1, 2)})
    data = analyze_nasa(nasa_fixture(options), options)
    assert not data['quality']['full_year'] and all(v is None for v in data['annual'].values())
    assert data['monthly'][0]['solar_kwh_m2'] == 6


def test_nasa_rejects_wrong_unit_location_and_time():
    options = nasa_options()
    for change in [lambda r: r['parameters']['ALLSKY_SFC_SW_DWN'].__setitem__('units', 'W/m2'), lambda r: r['geometry'].__setitem__('coordinates',[0,0,0]), lambda r: r['header'].__setitem__('time_standard','UTC'), lambda r: r['header'].__setitem__('start','20240101')]:
        raw = nasa_fixture(options)
        change(raw)
        with pytest.raises(core.ValidationError):
            analyze_nasa(raw, options)


def test_weather_epw_api_export_cache_and_tamper(client):
    pid = project(client)
    base = '/api/projects/'+pid+'/weather'
    f = client.post('/api/projects/'+pid+'/files', files={'file': ('weather.epw', reference_path().read_bytes())}).json()
    first = client.post(base+'/epw', json={'file_id': f['file_id']})
    assert first.status_code == 201, first.text
    data = first.json()
    assert client.post(base+'/epw', json={'file_id': f['file_id']}).json()['weather_id'] == data['weather_id']
    assert 'rows' not in client.get(base).json()[0]
    csv_response = client.get(base+'/'+data['weather_id']+'/data.csv')
    assert csv_response.status_code == 200 and len(csv_response.text.splitlines()) == 8761
    assert client.get('/api/projects/'+pid+'/evidence').json() == []  # No automatic review/evidence creation.
    task = client.app.state.agent.start(pid, Chat(message='分析天气和采暖度日'), background=False)
    assert task['status'] == 'succeeded' and task['answer']['weather'][0]['weather_id'] == data['weather_id']
    assert 'weather_summary' in task['answer']['basis']
    _, path = client.app.state.domain.file_record(pid, f['file_id'])
    path.write_bytes(path.read_bytes()+b'\nTAMPERED')
    assert client.get(base+'/'+data['weather_id']).status_code == 409
    assert client.get(base+'/'+data['weather_id']+'/data.csv').status_code == 409
    assert client.get(base).json()[0]['invalid'] is True


def test_weather_cross_project_and_auth(client):
    p1, p2 = project(client), project(client)
    f = client.post('/api/projects/'+p1+'/files', files={'file': ('weather.epw', reference_path().read_bytes())}).json()
    assert client.post('/api/projects/'+p2+'/weather/epw', json={'file_id': f['file_id']}).status_code == 409
    w = client.post('/api/projects/'+p1+'/weather/epw', json={'file_id': f['file_id']}).json()
    assert client.get('/api/projects/'+p2+'/weather/'+w['weather_id']).status_code == 409
    with TestClient(client.app) as stranger:
        assert stranger.get('/api/projects/'+p1+'/weather').status_code == 401
        login = stranger.post('/api/auth/register', json={'username': 'other_weather', 'display_name':'Other', 'password':'Another-test-pass-2026'}).json()
        stranger.headers['X-CSRF-Token'] = login['csrf_token']
        assert stranger.get('/api/projects/'+p1+'/weather').status_code == 404  # Hide another owner's project.
    client.headers.pop('X-CSRF-Token')
    assert client.post('/api/projects/'+p1+'/weather/epw', json={'file_id': f['file_id']}).status_code == 403


def test_nasa_api_real_boundary_with_stubbed_remote_cache_and_failure(client, monkeypatch):
    # Only the external HTTP transport is stubbed. Schema/storage/CSV/auth run normally.
    pid = project(client)
    options = nasa_options()
    payload = options.model_dump(mode='json')
    calls = []
    raw = nasa_fixture(options)
    original = httpx.Client
    def handler(req):
        calls.append(str(req.url))
        assert req.url.host == 'power.larc.nasa.gov'
        return httpx.Response(200, json=raw)
    monkeypatch.setattr('backend.weather.httpx.Client', lambda **kw: original(transport=httpx.MockTransport(handler), **kw))
    base = '/api/projects/'+pid+'/weather'
    response = client.post(base+'/nasa', json=payload)
    assert response.status_code == 201, response.text
    data = response.json()
    assert client.post(base+'/nasa', json=payload).json()['weather_id'] == data['weather_id']
    assert len(calls) == 1 and 'time-standard=LST' in calls[0]
    assert data['source_hash'] and data['provenance']['provider'] == 'NASA POWER'
    assert len(client.get(base+'/'+data['weather_id']+'/data.csv').text.splitlines()) == 366
    def failed(req):
        return httpx.Response(503)
    monkeypatch.setattr('backend.weather.httpx.Client', lambda **kw: original(transport=httpx.MockTransport(failed), **kw))
    assert client.post(base+'/nasa', json={**payload, 'refresh': True}).status_code == 409
    assert len(client.get(base).json()) == 1  # No fallback record on outage.


def test_weather_options_bounds_and_dates(client):
    pid = project(client)
    payload = nasa_options().model_dump(mode='json')
    for change in [{'latitude': True}, {'longitude': 181}, {'end': '2024-01-01'}, {'end': date.today().isoformat()}, {'start':'1983-01-01'}, {'start':'2024-12-31', 'end':'2025-01-02'}, {'heating_base_c': 28, 'cooling_base_c': 20}]:
        assert client.post('/api/projects/'+pid+'/weather/nasa', json={**payload, **change}).status_code == 422


def test_weather_quality_gate_blocks_missing_temperature(client, tmp_path):
    pid = client.post('/api/reference-projects').json()['project_id']
    domain = client.app.state.domain
    for ev in domain.store.list('evidence', pid):
        client.patch('/api/projects/'+pid+'/evidence/'+ev['evidence_id'], json={'expected_revision':ev['revision'], 'review_state':'confirmed', 'responsible_person':'Test only', 'review_note':'Reference fixture test'})
    assert domain.gate(pid)['can_simulate']
    old = next(ev for ev in domain.store.list('evidence',pid) if ev['type']=='epw')
    client.patch('/api/projects/'+pid+'/evidence/'+old['evidence_id'], json={'expected_revision':old['revision'], 'review_state':'rejected', 'responsible_person':'Test only', 'review_note':'Test damaged replacement'})
    damaged = epw_variant(tmp_path, lambda ls: ls[8].__setitem__(6, '99.9'))
    f = client.post('/api/projects/'+pid+'/files', files={'file': ('missing.epw', damaged.read_bytes())}).json()
    body = {k:old[k] for k in ['type','name','source_locator','authority','permission','responsible_person','acquisition_method','status']}
    ev = client.post('/api/projects/'+pid+'/evidence', json={**body,'source_file':f['file_id']}).json()
    client.patch('/api/projects/'+pid+'/evidence/'+ev['evidence_id'], json={'expected_revision':ev['revision'], 'review_state':'confirmed', 'responsible_person':'Test only','review_note':'Deliberately invalid test input'})
    gate = domain.gate(pid)
    assert not gate['can_simulate'] and any(b['code']=='INVALID_SOURCE' and b['field']=='epw' for b in gate['blockers'])
