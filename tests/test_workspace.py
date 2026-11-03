from fastapi.testclient import TestClient

from test_api import create_project, reference


def test_workspace_is_owner_scoped_and_resumes_saved_intakes(client):
    p = reference(client)
    batch = client.post('/api/intakes', json={'project_id': p['project_id']}).json()
    response = client.get('/api/workspace')
    assert response.status_code == 200
    data = response.json()
    assert data['counts']['projects'] == 1
    assert data['counts']['pending_evidence'] == 4
    assert data['counts']['unfinished_intakes'] == 1
    assert data['projects'][0]['next_action']['view'] == 'evidence'
    assert data['intakes'][0]['id'] == batch['id']
    assert 'source_file' not in str(data)
    token = client.post('/api/projects/'+p['project_id']+'/tokens', json={'name': 'scoped'}).json()['token']
    with TestClient(client.app) as other:
        assert other.get('/api/workspace').status_code == 401
        assert other.get('/api/workspace', headers={'Authorization': 'Bearer '+token}).status_code == 403
        session = other.post('/api/auth/register', json={'username': 'other_owner', 'display_name': 'Other', 'password': 'Different-owner-password!'}).json()
        other.headers['X-CSRF-Token'] = session['csrf_token']
        foreign = create_project(other)
        assert other.get('/api/workspace').json()['projects'][0]['project_id'] == foreign['project_id']
        assert len(other.get('/api/workspace').json()['projects']) == 1
        assert other.get('/api/workspace').json()['intakes'] == []
    assert len(client.get('/api/workspace').json()['projects']) == 1


def test_workspace_current_status_is_revalidated_not_raw_job_success(client, monkeypatch):
    p = reference(client)
    # A persisted job may say succeeded while the current validity check says stale.
    # This test isolates that contract without fabricating a usable physics result.
    domain = client.app.state.domain
    rid = 'run_'+'a'*32
    domain.store.add_job({'run_id': rid, 'project_id': p['project_id'], 'created_at': p['created_at']})
    domain.store.finish(rid, 'succeeded')
    monkeypatch.setattr(domain, 'view', lambda _: {'run_id': rid, 'status': 'stale', 'created_at': p['created_at']})
    data = client.get('/api/workspace').json()
    assert data['projects'][0]['status'] == 'stale'
    assert data['projects'][0]['latest_run']['status'] == 'stale'
    assert 'metrics' not in data['projects'][0]['latest_run']
    assert data['counts']['active_runs'] == 0
    domain.store.finish(rid, 'running')
    assert client.get('/api/workspace').json()['counts']['active_runs'] == 1


def test_workspace_empty_and_source_free_projects_have_real_next_action(client):
    assert client.get('/api/workspace').json()['counts'] == {'projects': 0, 'pending_evidence': 0, 'active_runs': 0, 'unfinished_intakes': 0}
    p = create_project(client)
    project = client.get('/api/workspace').json()['projects'][0]
    assert project['project_id'] == p['project_id']
    assert project['status'] == 'preparing'
    assert project['next_action']['view'] == 'intake'


def test_intake_review_draft_is_persistent_versioned_and_never_auto_commits(client):
    batch = client.post('/api/intakes', json={}).json()
    iid = batch['id']
    uploaded = client.post('/api/intakes/'+iid+'/files', files={'file': ('project.txt', '项目名称：测试工程'.encode(), 'text/plain')})
    assert uploaded.status_code == 201
    assert client.post('/api/intakes/'+iid+'/analyze', json={}).status_code == 202
    path = '/api/intakes/'+iid+'/draft'
    body = {'expected_revision': 0, 'fields': {'name': '<核对草稿>', 'area_m2': '', 'region': 'CN-JX'}}
    assert client.put(path, json=body, headers={'X-CSRF-Token': ''}).status_code == 403
    assert client.put(path, json={**body, 'fields': {'admin': 'yes'}}).status_code == 422
    saved = client.put(path, json=body)
    assert saved.status_code == 200, saved.text
    assert saved.json()['revision'] == 1
    assert client.get('/api/intakes/'+iid).json()['draft']['fields'] == body['fields']
    assert client.get('/api/projects').json() == []
    assert client.put(path, json=body).status_code == 409
    with TestClient(client.app) as other:
        session = other.post('/api/auth/register', json={'username': 'draft_other', 'display_name': 'Other', 'password': 'Another-owner-password!'}).json()
        other.headers['X-CSRF-Token'] = session['csrf_token']
        assert other.put(path, json={**body, 'expected_revision': 1}).status_code == 404
    body['expected_revision'] = 1
    body['fields']['area_m2'] = '2300'
    assert client.put(path, json=body).json()['revision'] == 2
