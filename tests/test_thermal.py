from decimal import Decimal

import pytest
from pydantic import ValidationError

from backend.thermal import Assembly, calculate
from test_api import create_project


def body():
    return {'name': 'Auditor assembly', 'rsi_m2k_w': .13, 'rse_m2k_w': .04,
            'surface_basis': 'Explicit hypothetical surface films', 'application': 'Uniform dry wall, no thermal bridge',
            'layers': [{'name': 'masonry', 'thickness': 200, 'thickness_unit': 'mm', 'conductivity': .8,
                        'conductivity_unit': 'W/(m K)', 'source': 'Auditor independent arithmetic input',
                        'correction_basis': 'Dry declared test condition'},
                       {'name': 'insulation', 'thickness': 8, 'thickness_unit': 'cm', 'conductivity': 40,
                        'conductivity_unit': 'mW/(m K)', 'source': 'Auditor independent arithmetic input',
                        'correction_basis': 'Dry declared test condition'}]}


def test_multilayer_decimal_oracle_and_units():
    r = calculate(Assembly(**body()))
    expected = Decimal(1) / (Decimal('.13') + Decimal('.04') + Decimal('.2') / Decimal('.8') + Decimal('.08') / Decimal('.04'))
    assert r['u_w_m2k'] == pytest.approx(float(expected), rel=1e-12)
    assert r['layer_resistance_m2k_w'] == pytest.approx(2.25)
    assert r['energy_saving_rate'] is None
    assert r['compliance_status'] == 'NOT_ASSESSED'


def test_single_layer_correction_and_missing_values():
    data = body(); data['layers'] = data['layers'][:1]
    assert calculate(Assembly(**data))['layers'][0]['resistance_m2k_w'] == .25
    data['layers'][0]['correction_factor'] = 2
    assert calculate(Assembly(**data))['layers'][0]['resistance_m2k_w'] == .125
    data['rsi_m2k_w'] = None
    r = calculate(Assembly(**data))
    assert r['u_w_m2k'] is None and r['layer_resistance_m2k_w'] == .125
    data['layers'][0]['conductivity'] = None
    r = calculate(Assembly(**data))
    assert r['layer_resistance_m2k_w'] is None and r['u_w_m2k'] is None


@pytest.mark.parametrize('field,value', [('thickness', -1), ('thickness', 0), ('thickness', True),
    ('conductivity', 0), ('conductivity', -1), ('conductivity', '0.8'), ('conductivity', float('nan')),
    ('conductivity', 1e308), ('thickness_unit', 'ft'), ('conductivity_unit', 'kgCO2/kWh'), ('correction_factor', .5)])
def test_invalid_units_numbers_and_extremes(field, value):
    data = body(); data['layers'][0][field] = value
    with pytest.raises(ValidationError):
        Assembly(**data)


def test_same_material_unit_conflict():
    data = body(); data['layers'][1]['name'] = 'masonry'
    with pytest.raises(ValidationError, match='Conflicting'):
        Assembly(**data)
    data['layers'][1]['conductivity'] = 800
    Assembly(**data)  # equivalent mW and W values are allowed


def test_history_export_comparison_and_project_isolation(client):
    pid = create_project(client)['project_id']; path = f'/api/projects/{pid}/thermal'
    data = body(); first = client.post(path, json=data)
    assert first.status_code == 201
    a = first.json(); data['layers'][1]['thickness'] = 10
    b = client.post(path, json=data).json()
    assert a['thermal_id'] != b['thermal_id']
    assert len(client.get(path).json()) == 2
    r = client.post(f'/api/projects/{pid}/thermal-comparisons', json={'thermal_ids': [a['thermal_id'], b['thermal_id']]}).json()
    assert r['results'][1]['u_reduction_pct'] == pytest.approx((1 - (1/2.92)/(1/2.42))*100)
    assert r['recommendation'] is None
    assert client.get(path+'/'+a['thermal_id']).json()['result'] == a['result']
    assert '2.42' in client.get(path+'/'+a['thermal_id']+'/report.html').text
    other = create_project(client)['project_id']
    assert client.get(f'/api/projects/{other}/thermal/'+a['thermal_id']).status_code == 409
    data['surface_basis'] = 'Another assumption'
    c = client.post(path, json=data).json()
    assert client.post(f'/api/projects/{pid}/thermal-comparisons', json={'thermal_ids': [a['thermal_id'], c['thermal_id']]}).status_code == 409
    client.cookies.clear()
    assert client.get(path).status_code == 401


def test_evidence_revision_stales_result_without_overwriting_history(client):
    pid = create_project(client)['project_id']; base = f'/api/projects/{pid}'
    ev = client.post(base+'/evidence', json={'type': 'manual_input', 'name': 'test measurement', 'source_locator': 'record1',
        'authority': 'test lab', 'permission': 'synthetic data', 'acquisition_method': 'test', 'responsible_person': 'auditor',
        'status': 'MEASURED'}).json()
    data = body(); data['layers'][0]['evidence_id'] = ev['evidence_id']
    a = client.post(base+'/thermal', json=data).json()
    client.patch(base+'/evidence/'+ev['evidence_id'], json={'expected_revision': 1, 'review_state': 'confirmed',
        'responsible_person': 'auditor', 'review_note': 'New review invalidates prior evidence snapshot'})
    current = client.get(base+'/thermal/'+a['thermal_id']).json()
    assert current['status'] == 'stale' and current['result'] is None
    raw = client.app.state.domain.store.get('thermal', a['thermal_id'])
    assert raw['result'] == a['result'] and raw['revision'] == 1


def test_thermal_report_escapes_untrusted_names(client):
    pid = create_project(client)['project_id']; data = body(); data['name'] = '<script>alert(1)</script>'
    a = client.post(f'/api/projects/{pid}/thermal', json=data).json()
    text = client.get(f'/api/projects/{pid}/thermal/{a["thermal_id"]}/report.html').text
    assert '<script>' not in text and '&lt;script&gt;' in text


def test_thermal_source_tampering_and_calculator_change(client, monkeypatch):
    from backend import thermal
    pid = create_project(client)['project_id']; base = f'/api/projects/{pid}'
    f = client.post(base+'/files', files={'file': ('material.json', b'{"synthetic":true}')}).json()
    ev = client.post(base+'/evidence', json={'type': 'literature', 'name': 'Material reference',
        'source_file': f['file_id'], 'source_locator': 'all', 'authority': 'Auditor', 'permission': 'test',
        'acquisition_method': 'test', 'responsible_person': 'Auditor', 'status': 'IMPORTED'}).json()
    client.patch(base+'/evidence/'+ev['evidence_id'], json={'expected_revision': 1, 'review_state': 'confirmed',
        'responsible_person': 'Auditor', 'review_note': 'Synthetic material reference inspected'})
    data = body()
    for layer in data['layers']:
        layer['evidence_id'] = ev['evidence_id']
    record = client.post(base+'/thermal', json=data).json()
    assert record['source_status'] == 'HUMAN_REVIEWED_SOURCES'
    path = base+'/thermal/'+record['thermal_id']
    with monkeypatch.context() as m:
        m.setattr(thermal, 'version', lambda: 'new-calculator')
        changed = client.get(path).json()
        assert changed['status'] == 'stale' and changed['result'] is None
    _, file_path = client.app.state.domain.file_record(pid, f['file_id'])
    file_path.write_bytes(b'{"tampered":true}')
    changed = client.get(path).json()
    assert changed['status'] == 'stale' and changed['result'] is None
    assert changed['source_status'] == 'USER_DECLARED'
    assert client.post(base+'/thermal', json=data).status_code == 409


def test_factor_source_review_tied_to_version_and_document(client):
    pid = create_project(client)['project_id']; base = f'/api/projects/{pid}'
    factor = {'expected_revision': 0, 'region': '*', 'scenario': False, 'factors': {'Electricity': {
        'value': .5, 'source': 'Synthetic arithmetic source', 'factor_id': 'synthetic-v1',
        'publisher': 'Auditor', 'document_version': 'v1', 'reference_year': 2025}}}
    assert client.put(base+'/carbon-factors', json=factor).status_code == 200
    assert client.get(base+'/carbon-factor-assurance').json()['status'] == 'USER_DECLARED'
    f = client.post(base+'/files', files={'file': ('test.json', b'{"test_only":true}')}).json()
    ev = client.post(base+'/evidence', json={'type': 'literature', 'name': 'source', 'source_file': f['file_id'], 'source_locator': 'all',
        'authority': 'test', 'permission': 'test', 'acquisition_method': 'test', 'responsible_person': 'test', 'status': 'IMPORTED'}).json()
    review = {'factor_revision': 1, 'evidence_ids': [ev['evidence_id']], 'note': 'Synthetic source review test only'}
    assert client.post(base+'/carbon-factor-reviews', json=review).status_code == 409
    client.patch(base+'/evidence/'+ev['evidence_id'], json={'expected_revision': 1, 'review_state': 'confirmed', 'responsible_person': 'test', 'review_note': 'Test source version inspected'})
    assert client.post(base+'/carbon-factor-reviews', json=review).status_code == 201
    assert client.get(base+'/carbon-factor-assurance').json()['status'] == 'HUMAN_SOURCE_REVIEWED'
    client.patch(base+'/evidence/'+ev['evidence_id'], json={'expected_revision': 2, 'review_state': 'pending', 'responsible_person': 'test', 'review_note': 'Withdraw source confirmation'})
    assert client.get(base+'/carbon-factor-assurance').json()['status'] == 'REVIEW_STALE'
    factor['expected_revision'] = 1; factor['factors']['Electricity']['value'] = .6
    assert client.put(base+'/carbon-factors', json=factor).status_code == 200
    assert client.get(base+'/carbon-factor-assurance').json()['status'] == 'USER_DECLARED'
    assert client.post(base+'/carbon-factor-reviews', json=review).status_code == 409
