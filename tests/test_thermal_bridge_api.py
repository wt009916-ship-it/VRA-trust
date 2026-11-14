import copy
import csv
import io
import json

import pytest

from backend import thermal_bridge
from test_api import create_project
from test_thermal_bridge import slab


def create(client, body=None):
    pid = create_project(client)['project_id']
    base = f'/api/projects/{pid}'
    response = client.post(base + '/thermal-bridges', json=body or slab())
    assert response.status_code == 201, response.text
    return base, response.json()


def evidence(client, base, file_id=None):
    return client.post(base + '/evidence', json={'type': 'manual_input', 'name': 'Synthetic thermal reference',
        'source_file': file_id, 'source_locator': 'Test row 1', 'authority': 'Independent test author', 'permission': 'Synthetic test only',
        'acquisition_method': 'Test', 'responsible_person': 'Test author', 'status': 'ASSUMED'}).json()


def test_history_download_report_are_current_and_project_scoped(client):
    body = slab()
    body['name'] = '<script>alert(1)</script>'
    base, record = create(client, body)
    path = base + '/thermal-bridges/' + record['thermalbridge_id']
    assert client.get(path).json()['result'] == record['result']
    history = client.get(base + '/thermal-bridges').json()
    assert history['next_offset'] is None and history['items'][0]['status'] == 'calculated'
    assert 'result' not in history['items'][0] and 'input' not in history['items'][0]
    assert client.get(base + '/thermal-bridges?limit=51').status_code == 422
    html = client.get(path + '/report.html').text
    assert '<script>' not in html and '&lt;script&gt;' in html
    assert 'W/m' in html and '不是完整热桥标准验证或节能合规结论' in html
    data = list(csv.DictReader(io.StringIO(client.get(path + '/temperatures.csv').text)))
    assert len(data) == record['result']['mesh_check']['fine_cells']
    assert data[0]['status'] == 'calculated'
    assert float(data[0]['cell_temperature_c']) == record['result']['temperature_c'][0][0]
    other = create_project(client)['project_id']
    assert client.get('/api/projects/' + other + '/thermal-bridges/' + record['thermalbridge_id']).status_code == 409
    client.cookies.clear()
    for suffix in ('', '/report.html', '/temperatures.csv'):
        assert client.get(path + suffix).status_code == 401


def test_missing_inputs_remain_null_without_csv(client):
    body = slab()
    body['regions'][0]['conductivity'] = None
    base, record = create(client, body)
    assert record['status'] == 'incomplete' and record['result']['temperature_c'] is None
    path = base + '/thermal-bridges/' + record['thermalbridge_id']
    assert client.get(path + '/temperatures.csv').status_code == 409
    assert '未进入求解器' in client.get(path + '/report.html').text


def test_csrf_and_capacity_and_numerical_failure_leave_no_record(client, monkeypatch):
    base = '/api/projects/' + create_project(client)['project_id']
    path = base + '/thermal-bridges'
    assert client.post(path, json=slab(), headers={'X-CSRF-Token': ''}).status_code == 403
    service = client.app.state.thermal_bridge
    with service.capacity:
        assert client.post(path, json=slab()).status_code == 429
    def fail(_):
        raise ValueError('Synthetic solver budget failure')
    with monkeypatch.context() as m:
        m.setattr(thermal_bridge, 'calculate', fail)
        response = client.post(path, json=slab())
        assert response.status_code == 409 and 'budget' in response.text
    assert client.get(path).json()['items'] == []
    assert client.post(path, json=slab()).status_code == 201  # capacity released after failure


@pytest.mark.parametrize('change', ['evidence', 'file', 'calculator', 'project'])
def test_stale_masks_results_on_all_read_paths_preserving_original(client, monkeypatch, change):
    base = '/api/projects/' + create_project(client)['project_id']
    uploaded = client.post(base + '/files', files={'file': ('reference.json', b'{"synthetic":true}')}).json()
    ev = evidence(client, base, uploaded['file_id'])
    body = slab()
    body['evidence_ids'] = [ev['evidence_id']]
    record = client.post(base + '/thermal-bridges', json=body).json()
    assert record['status'] == 'calculated' and record['source_status'] == 'USER_DECLARED'
    domain = client.app.state.domain
    if change == 'evidence':
        response = client.patch(base + '/evidence/' + ev['evidence_id'], json={'expected_revision': 1, 'review_state': 'rejected',
            'responsible_person': 'Test', 'review_note': 'Withdraw synthetic source'})
        assert response.status_code == 200
    elif change == 'file':
        _, path = domain.file_record(record['project_id'], uploaded['file_id'])
        path.write_bytes(b'changed source')
    elif change == 'project':
        old = domain.store.get('project', record['project_id'])
        domain.store.put('project', {**old, 'name': 'New project declaration'}, old['revision'])
    else:
        monkeypatch.setattr(thermal_bridge, 'version', lambda: 'new-solver-version')
    path = base + '/thermal-bridges/' + record['thermalbridge_id']
    current = client.get(path).json()
    assert current['status'] == 'stale' and current['result'] is None and current['stale_details']
    assert client.get(base + '/thermal-bridges').json()['items'][0]['status'] == 'stale'
    assert client.get(path + '/temperatures.csv').status_code == 409
    assert '当前结果不可用' in client.get(path + '/report.html').text
    assert domain.store.get('thermalbridge', record['thermalbridge_id'])['result'] == record['result']


def test_foreign_sources_rejected(client):
    first = '/api/projects/' + create_project(client)['project_id']
    second = '/api/projects/' + create_project(client)['project_id']
    body = slab()
    body['evidence_ids'] = [evidence(client, first)['evidence_id']]
    assert client.post(second + '/thermal-bridges', json=body).status_code == 409


def test_other_account_cannot_read_create_or_download(client):
    base, record = create(client)
    client.cookies.clear()
    login = client.post('/api/auth/register', json={'username': 'different_owner', 'display_name': 'Another test owner',
                                                  'password': 'Synthetic-test-password-2026'}).json()
    client.headers['X-CSRF-Token'] = login['csrf_token']
    path = base + '/thermal-bridges'
    assert client.post(path, json=slab()).status_code == 404
    for suffix in ('', '/' + record['thermalbridge_id'], '/' + record['thermalbridge_id'] + '/report.html',
                   '/' + record['thermalbridge_id'] + '/temperatures.csv'):
        assert client.get(path + suffix).status_code == 404


@pytest.mark.parametrize('change', ['project', 'calculator'])
def test_changed_dependency_during_solve_prevents_commit(client, monkeypatch, change):
    pid = create_project(client)['project_id']
    domain = client.app.state.domain
    actual = thermal_bridge.calculate
    def changed(body):
        result = actual(body)
        if change == 'project':
            project = domain.store.get('project', pid)
            domain.store.put('project', {**project, 'name': 'Changed during solve'}, project['revision'])
        else:
            monkeypatch.setattr(thermal_bridge, 'version', lambda: 'changed-during-solve')
        return result
    monkeypatch.setattr(thermal_bridge, 'calculate', changed)
    assert client.post('/api/projects/' + pid + '/thermal-bridges', json=slab()).status_code == 409
    assert domain.store.list('thermalbridge', pid) == []


def test_record_tampering_refused(client):
    base, record = create(client)
    domain = client.app.state.domain
    raw = copy.deepcopy(domain.store.get('thermalbridge', record['thermalbridge_id']))
    raw['result']['temperature_c'][0][0] = 999
    with domain.store.connect() as con:
        con.execute('UPDATE records SET body=? WHERE kind=? AND id=?', (json.dumps(raw), 'thermalbridge', record['thermalbridge_id']))
    assert client.get(base + '/thermal-bridges/' + record['thermalbridge_id']).status_code == 409


def test_solver_budget_failure_is_a_real_refusal():
    from backend import thermal_bridge_solver as solver
    import time
    body = thermal_bridge.normalize(thermal_bridge.Section(**slab()))
    with pytest.raises(ValueError, match='budget'):
        solver.solve(body, body['cell_size'], time.monotonic() - 1)
