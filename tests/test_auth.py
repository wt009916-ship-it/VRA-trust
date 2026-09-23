import secrets
import time
import pytest
from fastapi.testclient import TestClient
from backend.api import create_app
from backend.auth import digest
from backend.schema import ProjectCreate


@pytest.fixture
def app(tmp_path):
    return create_app(tmp_path / 'accounts', start_worker=False)


def register(client, username='engineer_one'):
    password = secrets.token_urlsafe(18)
    result = client.post('/api/auth/register', json={'username':username,'display_name':'测试工程师','password':password})
    assert result.status_code == 200, result.text
    client.headers['X-CSRF-Token'] = result.json()['csrf_token']
    return password, result


def project(client):
    return client.post('/api/projects', json={'name':'私有项目','building':{'use':'office','location':'Golden','region':'US-CO','area_m2':927.2}}).json()


def test_anonymous_cannot_access_api_or_reports(app):
    with TestClient(app) as client:
        assert client.get('/api/auth/status').json()['setup_required']
        for url in ['/api/projects','/api/factor-profiles','/api/runs/run_'+'a'*32+'/report.pdf','/api/runs/run_'+'a'*32+'/artifacts']:
            assert client.get(url).status_code == 401


def test_password_session_cookie_and_logout(app):
    with TestClient(app) as client:
        password, response = register(client)
        cookie = response.headers['set-cookie']
        assert 'HttpOnly' in cookie and 'SameSite=strict' in cookie and 'Max-Age=43200' in cookie
        token = client.cookies.get('vra_session')
        with app.state.domain.store.connect() as con:
            user = con.execute('SELECT * FROM users').fetchone()
            session = con.execute('SELECT * FROM sessions').fetchone()
        assert password not in str(tuple(user)) and token not in str(tuple(session))
        assert session['token_hash'] == digest(token)
        assert 'password' not in response.text and 'salt' not in response.text
        assert client.post('/api/auth/logout').status_code == 200
        client.cookies.set('vra_session', token, domain='testserver.local', path='/')
        assert client.get('/api/auth/me').status_code == 401
        assert client.post('/api/auth/login', json={'username':'engineer_one','password':password}).status_code == 200
        assert client.cookies.get('vra_session') != token


def test_csrf_and_cross_site_rejected(app):
    with TestClient(app) as client:
        register(client)
        client.headers.pop('X-CSRF-Token')
        assert client.post('/api/projects', json={}).status_code == 403
        client.headers['X-CSRF-Token'] = 'wrong-token'
        assert client.post('/api/auth/logout').status_code == 403
        assert client.post('/api/auth/login', json={}, headers={'Origin':'https://foreign.example'}).status_code == 403
        assert client.get('/api/projects', headers={'Sec-Fetch-Site':'cross-site'}).status_code == 403


def test_accounts_isolate_projects_files_evidence_runs_and_downloads(app):
    with TestClient(app) as alice, TestClient(app) as bob:
        register(alice)
        p = project(alice)
        pid = p['project_id']
        file = alice.post(f'/api/projects/{pid}/files', files={'file':('bill.csv',b'energy\n10')}).json()
        rid = 'run_' + 'a' * 32
        app.state.domain.store.add_job({'run_id':rid,'project_id':pid})
        register(bob, 'engineer_two')
        assert bob.get('/api/projects').json() == []
        for suffix in ['', '/evidence','/gate','/runs', '/files/'+file['file_id']]:
            assert bob.get(f'/api/projects/{pid}'+suffix).status_code == 404
        assert bob.put(f'/api/projects/{pid}/building', json={}).status_code == 404
        assert bob.post('/api/runs', json={'project_id':pid,'scheme_id':'baseline'}).status_code == 404
        for suffix in ['', '/result','/evidence','/claims','/report.json','/report.html','/report.pdf','/artifacts']:
            assert bob.get('/api/runs/'+rid+suffix).status_code == 404
        assert bob.post('/api/comparisons', json={'run_ids':[rid,'run_'+'b'*32]}).status_code == 404
        assert len(alice.get('/api/projects').json()) == 1


def test_first_account_migrates_legacy_once_without_changing_evidence(app):
    old = app.state.domain.create_project(ProjectCreate(name='既有项目',building={'use':'office','location':'Golden','region':'US-CO','area_m2':927.2}))
    with TestClient(app) as first, TestClient(app) as second:
        register(first)
        assert first.get('/api/projects').json()[0] == old
        register(second, 'engineer_two')
        assert second.get('/api/projects').json() == []
        assert app.state.domain.store.get('project', old['project_id']) == old


def test_expired_session_and_wrong_password(app):
    with TestClient(app) as client:
        register(client)
        response = client.post('/api/auth/login', json={'username':'engineer_one','password':'definitely-wrong-password'})
        assert response.status_code == 401
        with app.state.domain.store.connect() as con:
            con.execute('UPDATE sessions SET expires=?', (time.time()-1,))
        assert client.get('/api/projects').status_code == 401


def test_login_throttle_persists_in_database(app):
    with TestClient(app) as client:
        auth = app.state.auth
        for _ in range(8):
            auth.throttle('blocked_user','testclient')
        result = client.post('/api/auth/login', json={'username':'blocked_user','password':'wrong-long-password'})
        assert result.status_code == 429


def test_validation_and_secure_cookie_option(app, monkeypatch):
    monkeypatch.setenv('VRA_COOKIE_SECURE','true')
    with TestClient(app, base_url='https://testserver') as client:
        assert client.post('/api/auth/register', json={'username':'bad name','display_name':'x','password':'short'}).status_code == 422
        _, response = register(client)
        assert 'Secure' in response.headers['set-cookie']
        assert client.get('/api/auth/me').status_code == 200


def test_session_survives_app_restart_and_contract_documents_auth(app):
    with TestClient(app) as first:
        register(first)
        token = first.cookies.get('vra_session')
    restarted = create_app(app.state.domain.store.root, start_worker=False)
    with TestClient(restarted) as client:
        client.cookies.set('vra_session', token, domain='testserver.local', path='/')
        assert client.get('/api/auth/me').status_code == 200
        contract = client.get('/openapi.json').json()
        assert contract['paths']['/api/projects']['post']['security'] == [{'sessionCookie':[], 'csrfHeader':[]}]
        assert 'security' not in contract['paths']['/api/auth/login']['post']
