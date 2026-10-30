import json
import sqlite3

from fastapi.testclient import TestClient

from test_intake_admin import PROJECT

ADMIN_PASSWORD = 'Test-only-long-pass-2026'
MEMBER_PASSWORD = 'Member-password-2026!'


def create_member(client, name='managed_user'):
    r = client.post('/api/admin/users', json={'username': name, 'display_name': 'Managed member',
                    'password': MEMBER_PASSWORD, 'current_password': ADMIN_PASSWORD})
    assert r.status_code == 201, r.text
    return r.json()


def login(client, name, password):
    r = client.post('/api/auth/login', json={'username': name, 'password': password})
    if r.status_code == 200:
        client.headers['X-CSRF-Token'] = r.json()['csrf_token']
    return r


def test_member_creation_reauth_csrf_and_password_policy(client):
    body = {'username': 'managed_user', 'display_name': 'Member', 'password': MEMBER_PASSWORD,
            'current_password': 'Wrong-admin-password!'}
    assert client.post('/api/admin/users', json=body).status_code == 403
    assert len(client.get('/api/admin/overview').json()['users']) == 1
    body['current_password'] = ADMIN_PASSWORD
    assert client.post('/api/admin/users', json=body, headers={'X-CSRF-Token': ''}).status_code == 403
    body['password'] = 'aaaaaaaaaaaa!'
    assert client.post('/api/admin/users', json=body).status_code == 422
    user = create_member(client)
    assert 'password' not in user and 'salt' not in user
    assert client.post('/api/admin/users', json={**body, 'password': MEMBER_PASSWORD}).status_code == 409
    with TestClient(client.app) as member:
        assert login(member, user['username'], MEMBER_PASSWORD).status_code == 200
        assert member.get('/api/admin/database').status_code == 403
        assert member.get('/api/admin/database/collections/users').status_code == 403
        assert member.post('/api/admin/database/backups', json={'current_password': MEMBER_PASSWORD}).status_code == 403


def test_reset_revokes_sessions_tokens_and_preserves_projects(client):
    user = create_member(client)
    with TestClient(client.app) as member, TestClient(client.app) as bearer:
        login(member, user['username'], MEMBER_PASSWORD)
        pid = member.post('/api/projects', json=PROJECT).json()['project_id']
        token = member.post('/api/projects/'+pid+'/tokens', json={'name': 'before reset'}).json()['token']
        new_password = 'Replacement-password-2026!'
        path = '/api/admin/users/'+user['id']+'/password'
        assert client.post(path, json={'current_password': 'Incorrect-password!', 'new_password': new_password}).status_code == 403
        assert member.get('/api/projects/'+pid).status_code == 200
        assert client.post(path, json={'current_password': ADMIN_PASSWORD, 'new_password': new_password}).status_code == 200
        assert member.get('/api/projects').status_code == 401
        assert bearer.get('/api/projects/'+pid, headers={'Authorization': 'Bearer '+token}).status_code == 401
        assert login(member, user['username'], MEMBER_PASSWORD).status_code == 401
        assert login(member, user['username'], new_password).status_code == 200
        assert member.get('/api/projects/'+pid).status_code == 200
        overview = client.get('/api/admin/overview').json()
        assert any(r['action'] == 'password_reset_by_admin' for r in overview['audit'])
        assert new_password not in json.dumps(overview) and 'password_hash' not in json.dumps(overview)
        admin = client.get('/api/auth/me').json()['user']['id']
        assert client.post('/api/admin/users/'+admin+'/password', json={'current_password': ADMIN_PASSWORD, 'new_password': new_password}).status_code == 409


def test_account_edit_conflict_and_access_revoke(client):
    u = create_member(client)
    path = '/api/admin/users/'+u['id']+'/profile'
    body = {'current_password': ADMIN_PASSWORD, 'username': 'renamed_member', 'display_name': 'New display',
            'expected_username': u['username'], 'expected_display_name': u['display_name']}
    with TestClient(client.app) as member:
        login(member, u['username'], MEMBER_PASSWORD)
        assert client.put(path, json=body).status_code == 200
        assert member.get('/api/auth/me').status_code == 401
        assert client.put(path, json=body).status_code == 409
        assert login(member, 'renamed_member', MEMBER_PASSWORD).status_code == 200
        assert client.post('/api/admin/users/'+u['id']+'/revoke-access', json={'current_password': ADMIN_PASSWORD}).status_code == 200
        assert member.get('/api/auth/me').status_code == 401


def test_database_search_pagination_history_and_secret_redaction(client):
    projects = [client.post('/api/projects', json={**PROJECT, 'name': 'Data project '+str(i)}).json() for i in range(3)]
    p = projects[0]
    store = client.app.state.domain.store
    store.put('project', {**p, 'name': 'Updated project', 'nested': {'password_hash': 'hidden-hash', 'api_key': 'hidden-key', 'visible': 7}}, p['revision'])
    database = client.get('/api/admin/database').json()
    assert next(r['count'] for r in database['collections'] if r['id'] == 'projects') == 3
    page = client.get('/api/admin/database/collections/projects?page_size=2').json()
    assert page['total'] == 3 and len(page['items']) == 2
    assert len(client.get('/api/admin/database/collections/projects?page_size=2&page=2').json()['items']) == 1
    assert client.get('/api/admin/database/collections/projects?q=updated').json()['total'] == 1
    assert client.get('/api/admin/database/collections/projects?q=%25').json()['total'] == 0
    detail = client.get('/api/admin/database/collections/projects/'+p['project_id']).json()
    assert len(detail['history']) == 2 and detail['history'][1]['nested'] == {'visible': 7}
    for c in database['collections']:
        r = client.get('/api/admin/database/collections/'+c['id']+'?q=test')
        assert r.status_code == 200, (c, r.text)
        assert 'password_hash' not in r.text and 'token_hash' not in r.text and 'csrf' not in r.text
    assert client.get('/api/admin/database/collections/sqlite_master').status_code == 404
    assert client.get('/api/admin/database/collections/projects?page_size=1000').status_code == 422
    assert client.post('/api/admin/database/check', json={}).json()['passed']


def test_backup_snapshot_integrity_authorization_and_tamper(client):
    pid = client.post('/api/projects', json=PROJECT).json()['project_id']
    response = client.post('/api/admin/database/backups', json={'current_password': ADMIN_PASSWORD})
    assert response.status_code == 201, response.text
    meta = response.json()
    assert meta['integrity'] == 'ok' and len(meta['sha256']) == 64
    path = '/api/admin/database/backups/'+meta['id']+'/download'
    with TestClient(client.app) as stranger:
        assert stranger.get(path).status_code == 401
    file = client.app.state.domain.store.root/'admin-backups'/(meta['id']+'.sqlite3')
    con = sqlite3.connect(file)
    assert con.execute('pragma integrity_check').fetchone()[0] == 'ok'
    assert con.execute("select count(*) from records where kind='project' and id=?", (pid,)).fetchone()[0] == 1
    con.close()
    assert client.get(path).content.startswith(b'SQLite format 3')
    assert client.get('/api/admin/database/backups').json()[0]['id'] == meta['id']
    file.write_bytes(file.read_bytes()+b'changed')
    assert client.get(path).status_code == 409
