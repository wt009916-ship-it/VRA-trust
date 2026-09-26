import json
import os

import httpx
import pytest

from backend import core
from backend.agent import Chat
from backend.gateway import Gateway, ProviderSettings, protect
from backend.robustness import Axis, Search, set_conductivity, objects, stability_status
from backend.spatial import Reconstruction, geometry
from backend.trust import descendants
from test_api import create_project


def test_dag_selective_descendants_and_cycle_refusal():
    nodes = [{'id': i, 'depends_on': d} for i, d in [('energy', []), ('eui', ['energy']), ('factor', []), ('carbon', ['energy', 'factor']), ('certificate', ['carbon', 'eui'])]]
    assert descendants(nodes, ['factor']) == ['factor', 'carbon', 'certificate']
    assert 'energy' not in descendants(nodes, ['factor'])
    with pytest.raises(core.ValidationError, match='cycle'):
        descendants([{'id': 'a', 'depends_on': ['b']}, {'id': 'b', 'depends_on': ['a']}], ['a'])
    with pytest.raises(core.ValidationError, match='Unknown'):
        descendants(nodes, ['missing'])


def test_factor_contract_revision_and_project_auth(client):
    p = create_project(client)['project_id']
    path = '/api/projects/' + p + '/carbon-factors'
    body = {'expected_revision': 0, 'region': '*', 'scenario': True, 'factors': {'Electricity': {'value': .5, 'unit': 'kgCO2/kWh', 'source': 'test assumption', 'factor_id': 'test'}}}
    assert client.put(path, json=body).status_code == 200
    assert client.put(path, json=body).status_code == 409
    body['expected_revision'] = 1
    body['factors']['Electricity']['unit'] = 'kg/kJ'
    assert client.put(path, json=body).status_code == 409
    body['factors']['Electricity']['value'] = -1
    assert client.put(path, json=body).status_code == 422
    client.cookies.clear()
    assert client.get(path).status_code == 401


def test_local_agent_real_gate_timeline_and_fail_closed_provider(client):
    pid = create_project(client)['project_id']
    agent = client.app.state.agent
    task = agent.start(pid, Chat(message='我能推荐最佳方案吗？'), background=False)
    assert task['status'] == 'succeeded'
    assert task['answer']['can_simulate'] is False
    assert task['answer']['can_recommend'] is False
    assert [e['tool'] for e in task['events']] == ['project_get', 'evidence_list', 'evidence_validate', 'project_diagnose']
    assert all(e['status'] == 'succeeded' and e['result_hash'] and e['duration_ms'] >= 0 for e in task['events'])
    assert task['llm_commentary'] is None
    assert client.post(f'/api/projects/{pid}/agent/chat', json={'message': 'hello', 'mode': 'provider'}).status_code == 409


def test_agent_whitelist_scope_and_compute_permission(client, monkeypatch):
    pid = create_project(client)['project_id']
    agent = client.app.state.agent
    with pytest.raises(core.ValidationError, match='Unknown'):
        agent.call(pid, 'shell_exec', {}, False)
    assert agent.call(pid, 'simulation_create', {}, False)['status'] == 'ACTION_NOT_AUTHORIZED'
    monkeypatch.setattr(agent.store, 'job', lambda rid: {'project_id': 'different'})
    with pytest.raises(core.ValidationError, match='Cross-project'):
        agent.call(pid, 'simulation_result', {'run_id': 'stolen'}, False)


def test_provider_protocol_tool_return_and_no_hidden_reasoning(client, monkeypatch):
    gateway = client.app.state.gateway
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'test-secret-key-not-live')
    gateway.save(ProviderSettings(enabled=True))
    def handle(request):
        assert str(request.url) == Gateway.endpoint
        body = json.loads(request.content)
        assert body['tools'] and body['thinking']['type'] == 'disabled'
        return httpx.Response(200, json={'choices': [{'message': {'role': 'assistant', 'content': None,
            'reasoning_content': 'not displayed', 'tool_calls': [{'id': 'call1', 'type': 'function', 'function': {'name': 'evidence_validate', 'arguments': '{}'}}]}}]})
    answer = gateway.complete([{'role': 'user', 'content': 'test'}], client.app.state.agent.tools(), transport=httpx.MockTransport(handle))
    assert answer['tool_calls'][0]['function']['name'] == 'evidence_validate'
    assert 'reasoning_content' not in answer
    assert 'test-secret-key' not in json.dumps(gateway.public())
    with pytest.raises(core.ValidationError, match='HTTP 401'):
        gateway.complete([], [], transport=httpx.MockTransport(lambda req: httpx.Response(401, text='secret must not echo')))


@pytest.mark.skipif(os.name != 'nt', reason='Windows-specific OS secret encryption')
def test_windows_key_encrypted_at_rest_and_cleared(client):
    key = 'test-key-dpapi-encryption-not-live'
    assert protect(protect(key), True) == key
    r = client.put('/api/developer/provider', json={'enabled': False, 'api_key': key}).json()
    assert r['key_configured'] and key not in json.dumps(r)
    assert key not in client.app.state.gateway.path.read_text()
    assert client.put('/api/developer/provider', json={'enabled': False, 'clear_key': True}).json()['key_configured'] is False


def test_provider_configuration_admin_only(client):
    assert client.get('/api/developer/provider').status_code == 200
    session = client.post('/api/auth/register', json={'username': 'other_member', 'display_name': 'Member', 'password': 'Member-test-password!'}).json()
    client.headers['X-CSRF-Token'] = session['csrf_token']
    assert client.get('/api/developer/provider').status_code == 403
    assert client.put('/api/developer/provider', json={'enabled': True}).status_code == 403


def test_provider_agent_calls_actual_registry_under_protocol_fixture(client, monkeypatch):
    pid = create_project(client)['project_id']
    agent = client.app.state.agent
    monkeypatch.setattr(agent.gateway, 'public', lambda: {'enabled': True, 'key_configured': True})
    responses = iter([{'role': 'assistant', 'content': None, 'tool_calls': [{'id': 'call1', 'type': 'function', 'function': {'name': 'evidence_validate', 'arguments': '{}'}}]}, {'role': 'assistant', 'content': '需要补证，见工具结果'}])
    monkeypatch.setattr(agent.gateway, 'complete', lambda messages, tools: next(responses))
    result = agent.start(pid, Chat(message='检查资料', mode='provider'), background=False)
    assert result['status'] == 'succeeded'
    assert len(result['events']) == 7
    assert result['events'][-2]['result']['can_simulate'] is False
    assert result['events'][-1]['tool'] == 'llm.request'
    assert result['answer']['can_recommend'] is False


def test_material_mutation_targets_only_conductivity():
    original = 'Material, Wall, Rough, .2, .5, 900, 1000;\nMaterial, Other, Rough, .1, .2, 800, 1200;'
    altered = objects(set_conductivity(original, 'Wall', .9))
    assert altered[0][4] == '.9' or altered[0][4] == '0.9'
    assert altered[0][3] == '.2' and altered[1] == objects(original)[1]
    with pytest.raises(core.ValidationError):
        set_conductivity(original, 'unknown', 1)
    with pytest.raises(ValueError):
        Axis(material='Wall', values=[.2, .2], source='testing domain')


@pytest.mark.parametrize('points,total,status', [
    ([], 3, 'NOT_ASSESSED'),
    ([{'flipped': False}], 2, 'NO_FLIP_WITHIN_BUDGET'),
    ([{'flipped': False}], 1, 'STABLE_ON_ENUMERATED_GRID'),
    ([{'flipped': True}], 2, 'COUNTEREXAMPLE_FOUND'),
    ([{'flipped': None, 'indeterminate': True}], 1, 'RANKING_INDETERMINATE'),
])
def test_search_status_never_overstates_scope(points, total, status):
    assert stability_status(points, total) == status


def test_manual_geometry_confirmation_and_stale(client):
    pid = create_project(client)['project_id']
    ev = client.post(f'/api/projects/{pid}/evidence', json={'type': 'manual_input', 'name': 'Measured wall dimensions', 'source_locator': 'wall field sheet A-17', 'authority': 'test only', 'permission': 'fixture', 'acquisition_method': 'manual test', 'responsible_person': 'engineer', 'status': 'DOCUMENTED'}).json()
    wall = {'id': 'W-1', 'x1': 0, 'z1': 0, 'x2': 4, 'z2': 0, 'thickness_m': .2, 'evidence_id': ev['evidence_id'], 'source_locator': 'A17 wall 1', 'status': 'CONFIRMED'}
    body = {'expected_revision': 0, 'floor_height_m': 3, 'floors': 2, 'responsible_person': 'reviewer', 'review_note': 'Coordinates checked against fixture', 'walls': [wall]}
    path = f'/api/projects/{pid}/geometry'
    assert client.put(path, json=body).status_code == 409
    review = f'/api/projects/{pid}/evidence/{ev["evidence_id"]}'
    assert client.patch(review, json={'expected_revision': 1, 'review_state': 'confirmed', 'responsible_person': 'reviewer', 'review_note': 'Fixture dimensions verified'}).status_code == 200
    result = client.put(path, json=body).json()
    assert result['status'] == 'CONFIRMED'
    assert len(result['components']) == 2 and result['components'][1]['center'] == [2, 4.5, 0]
    assert result['components'][0]['affected_claims'] == []
    assert result['components'][0]['simulation_mapping'] == 'NOT_LINKED_TO_IDF'
    assert client.put(path, json=body).status_code == 409
    client.patch(review, json={'expected_revision': 2, 'review_state': 'pending', 'responsible_person': 'reviewer', 'review_note': 'Revoke evidence after conflict'})
    assert client.get(path).json()['status'] == 'STALE'


def test_geometry_deterministic_and_degenerate_rejected():
    schema = {'walls': [{'id': 'W', 'x1': 0, 'x2': 0, 'z1': 0, 'z2': 3, 'thickness_m': .2, 'evidence_id': 'test', 'source_locator': 'A17', 'status': 'UNKNOWN', 'insulation': None}], 'floors': 1, 'floor_height_m': 3}
    assert geometry(schema) == geometry(schema)
    schema['walls'][0]['z2'] = 0
    with pytest.raises(ValueError):
        Reconstruction(**schema, expected_revision=0, responsible_person='engineer', review_note='test invalid geometry')


@pytest.fixture
def search_evidence_fixture(client, monkeypatch):
    """Synthetic completed search for evidence invalidation, not physics validation."""
    pid = create_project(client)['project_id']
    file = client.post(f'/api/projects/{pid}/files', files={'file': ('material.csv', b'conductivity,0.2', 'text/csv')}).json()
    evidence = client.post(f'/api/projects/{pid}/evidence', json={
        'type': 'literature', 'name': 'Test material range', 'source_file': file['file_id'],
        'source_locator': 'Fixture row 1', 'authority': 'test only', 'permission': 'test fixture',
        'acquisition_method': 'test upload', 'responsible_person': 'tester', 'status': 'ASSUMED',
    }).json()
    domain, search = client.app.state.domain, client.app.state.robustness
    views = {
        'fixture_baseline': {'project_id': pid, 'status': 'succeeded', 'scheme_id': 'baseline', 'metrics': {'annual_energy_kwh': 100}, 'provenance': {}},
        'fixture_r1': {'project_id': pid, 'status': 'succeeded', 'scheme_id': 'R1', 'metrics': {'annual_energy_kwh': 90}, 'provenance': {}},
    }
    monkeypatch.setattr(domain, 'view', lambda rid: views[rid])
    monkeypatch.setattr(domain, 'compare', lambda ids: {})
    monkeypatch.setattr(search, 'materials', lambda ids: [{'name': 'Wall'}])
    def complete(record):
        domain.store.put('search', {**record, 'status': 'succeeded'}, record['revision'])
        search.capacity.release()
    monkeypatch.setattr(search, 'execute', complete)
    body = Search(run_ids=list(views), axes=[Axis(material='Wall', values=[.2, .3], source='Test-only range', evidence_id=evidence['evidence_id'])], budget=2)
    return pid, evidence, file, search, body


def review_axis(client, pid, evidence, state='confirmed'):
    response = client.patch(f'/api/projects/{pid}/evidence/{evidence["evidence_id"]}', json={
        'expected_revision': evidence['revision'], 'review_state': state,
        'responsible_person': 'tester', 'review_note': 'Test-only source reviewed',
    })
    assert response.status_code == 200
    return response.json()


def test_search_requires_reviewed_axis_and_freezes_its_source_nature(client, search_evidence_fixture):
    pid, evidence, file, search, body = search_evidence_fixture
    with pytest.raises(core.ValidationError):
        search.start(pid, body, background=False)
    reviewed = review_axis(client, pid, evidence)
    study = search.start(pid, body, background=False)
    snapshot = study['axis_evidence_snapshot'][evidence['evidence_id']]
    assert snapshot == reviewed
    assert snapshot['status'] == 'ASSUMED'
    assert search.view(pid, study['search_id'])['status'] == 'succeeded'


@pytest.mark.parametrize('change', ['review', 'tamper', 'missing_snapshot'])
def test_axis_changes_revoke_search_without_rewriting_history(client, search_evidence_fixture, change):
    pid, evidence, file, search, body = search_evidence_fixture
    reviewed = review_axis(client, pid, evidence)
    study = search.start(pid, body, background=False)
    if change == 'review':
        review_axis(client, pid, reviewed, 'pending')
    elif change == 'tamper':
        _, path = search.domain.file_record(pid, file['file_id'])
        path.write_text('changed source', encoding='utf-8')
    else:
        old = {**study}
        old.pop('axis_evidence_snapshot')
        study = search.store.put('search', old, study['revision'])
    before = search.store.history('search', study['search_id'])
    current = search.view(pid, study['search_id'])
    assert current['status'] == 'stale' and current['stability_status'] == 'STALE'
    assert current['stale_reasons']
    assert search.store.history('search', study['search_id']) == before


def test_axis_cannot_bind_another_projects_evidence(client, search_evidence_fixture):
    pid, evidence, file, search, body = search_evidence_fixture
    review_axis(client, pid, evidence)
    other = create_project(client)['project_id']
    with pytest.raises(core.ValidationError, match='Cross-project'):
        search.axis_evidence(other, body.axes)
