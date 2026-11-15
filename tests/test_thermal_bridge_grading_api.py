import csv
import io

from backend import thermal_bridge
from test_api import create_project
from test_thermal_bridge import slab
from test_thermal_bridge_grading import GRADED, COMPOSITE


def test_graded_composite_saves_current_field_report_csv_and_preserves_original_on_withdrawal(client):
    pid = create_project(client)['project_id']
    base = f'/api/projects/{pid}/thermal-bridges'
    body = {**COMPOSITE['input'], 'mesh_strategy': GRADED, 'cell_size': 4.}
    response = client.post(base, json=body)
    assert response.status_code == 201, response.text
    record = response.json()
    assert record['status'] == 'calculated' and record['input']['mesh_strategy'] == GRADED
    path = base + '/' + record['thermalbridge_id']
    assert client.get(path).json()['result'] == record['result']
    assert GRADED in client.get(path + '/report.html').text
    rows = list(csv.DictReader(io.StringIO(client.get(path + '/temperatures.csv').text)))
    assert len(rows) == record['result']['mesh_check']['fine_cells']
    assert float(rows[-1]['cell_temperature_c']) == record['result']['temperature_c'][-1][-1]
    domain = client.app.state.domain
    project = domain.store.get('project', pid)
    domain.store.put('project', {**project, 'name': 'Revised declared building'}, project['revision'])
    assert client.get(path).json()['result'] is None
    assert client.get(path + '/temperatures.csv').status_code == 409
    assert '当前结果不可用' in client.get(path + '/report.html').text
    assert domain.store.get('thermalbridge', record['thermalbridge_id'])['result'] == record['result']


def test_graded_solver_version_withdraws_current_result_and_failure_releases_capacity(client, monkeypatch):
    pid = create_project(client)['project_id']
    path = f'/api/projects/{pid}/thermal-bridges'
    body = {**slab(), 'mesh_strategy': GRADED}
    with monkeypatch.context() as m:
        m.setattr(thermal_bridge.solver, 'MAX_ITERATIONS', 0)
        refused = client.post(path, json=body)
        assert refused.status_code == 409 and 'budget' in refused.text
    assert client.get(path).json()['items'] == []
    record = client.post(path, json=body).json()
    assert record['status'] == 'calculated'
    monkeypatch.setattr(thermal_bridge, 'version', lambda: 'changed-mesh-method')
    current = client.get(path + '/' + record['thermalbridge_id']).json()
    assert current['status'] == 'stale' and current['result'] is None


def test_graded_auth_csrf_input_and_cross_project_guards(client):
    pid = create_project(client)['project_id']
    path = f'/api/projects/{pid}/thermal-bridges'
    body = {**slab(), 'mesh_strategy': GRADED}
    assert client.post(path, json=body, headers={'X-CSRF-Token': ''}).status_code == 403
    assert client.post(path, json={**body, 'mesh_strategy': 'invented'}).status_code == 422
    assert client.get(path).json()['items'] == []
    record = client.post(path, json=body).json()
    other = create_project(client)['project_id']
    assert client.get(f'/api/projects/{other}/thermal-bridges/' + record['thermalbridge_id']).status_code == 409
    client.cookies.clear()
    assert client.post(path, json=body).status_code == 401
    for suffix in ('', '/report.html', '/temperatures.csv'):
        assert client.get(path + '/' + record['thermalbridge_id'] + suffix).status_code == 401
