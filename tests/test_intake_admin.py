"""Real parsers and transactional admission; fixtures are not customer validation."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api import create_app
from backend.auth import digest
from backend.intake import parse_source

PROJECT = {'name': 'Test retrofit', 'building': {'use': 'office', 'location': 'Golden', 'region': 'US-CO', 'area_m2': 100}}
PASSWORD = 'Invite-test-pass-2026!'


def register(client, name, invitation=None):
    body = {'username': name, 'display_name': name, 'password': PASSWORD}
    if invitation:
        body['invitation'] = invitation
    response = client.post('/api/auth/register', json=body)
    if response.status_code == 200:
        client.headers['X-CSRF-Token'] = response.json()['csrf_token']
    return response


def batch(client, files):
    b = client.post('/api/intakes', json={}).json()
    for name, data in files:
        r = client.post('/api/intakes/'+b['id']+'/files', files={'file': (name, data)})
        assert r.status_code == 201, r.text
    assert client.post('/api/intakes/'+b['id']+'/analyze').status_code == 202
    return client.get('/api/intakes/'+b['id']).json()


def test_invitation_default_one_use_disabled_sessions_and_tokens(tmp_path, monkeypatch):
    monkeypatch.delenv('VRA_REGISTRATION_MODE')
    app = create_app(tmp_path/'accounts', start_worker=False)
    with TestClient(app) as owner, TestClient(app) as member, TestClient(app) as stranger:
        assert owner.get('/api/admin/overview').status_code == 401
        assert register(owner, 'owner').status_code == 200
        assert register(member, 'member').status_code == 403
        invite = owner.post('/api/admin/invitations', json={'label':'Team','days':1}).json()
        with app.state.domain.store.connect() as con:
            stored = dict(con.execute('SELECT * FROM invitations').fetchone())
        assert stored['token_hash'] == digest(invite['invitation'])
        assert invite['invitation'] not in json.dumps(stored)
        assert register(member, 'member', invite['invitation']).status_code == 200
        uid = member.get('/api/auth/me').json()['user']['id']
        assert register(stranger, 'stranger', invite['invitation']).status_code == 403
        assert member.get('/api/admin/overview').status_code == 403
        pid = member.post('/api/projects', json=PROJECT).json()['project_id']
        token = member.post(f'/api/projects/{pid}/tokens', json={'name':'external'}).json()['token']
        assert owner.patch('/api/admin/users/'+uid, json={'disabled': True}).status_code == 200
        assert member.get('/api/projects').status_code == 401
        assert stranger.get('/api/projects/'+pid, headers={'Authorization':'Bearer '+token}).status_code == 401
        assert member.post('/api/auth/login', json={'username':'member','password':PASSWORD}).status_code == 401
        assert owner.patch('/api/admin/users/'+uid, json={'disabled': False}).status_code == 200
        assert member.post('/api/auth/login', json={'username':'member','password':PASSWORD}).status_code == 200
        admin_id = owner.get('/api/auth/me').json()['user']['id']
        assert owner.patch('/api/admin/users/'+admin_id, json={'disabled':True}).status_code == 409
        overview = owner.get('/api/admin/overview').json()
        assert overview['database']['persistent'] and len(overview['audit']) >= 5
        assert 'salt' not in json.dumps(overview) and 'password_hash' not in json.dumps(overview)


@pytest.mark.parametrize('username,password', [('123456','Numeric-test-pass!'), ('validuser','123456789012'), ('validuser','aaaaaaaaaaaa!')])
def test_weak_registration_rejected(client, username, password):
    assert client.post('/api/auth/register', json={'username':username,'display_name':'test','password':password}).status_code == 422


def test_intake_conflicts_failures_provenance_commit_idempotence(client):
    brief = json.dumps(PROJECT).encode()
    b = batch(client, [('project.json', brief), ('conflict.txt', b'area_m2: 200'), ('broken.pdf', b'not a PDF')])
    assert b['status'] == 'review' and b['conflicts'] == ['area_m2']
    assert 'area_m2' not in b['suggestions'] and b['suggestions']['name'] == PROJECT['name']
    assert b['files'][2]['status'] == 'failed'
    assert b['candidates'][0]['file_id'] and b['candidates'][0]['locator']
    assert client.get('/api/projects').json() == []
    path = '/api/intakes/'+b['id']+'/commit'
    assert client.post(path, json={'reviewed':True}).status_code == 422
    assert client.post(path, json={'project':PROJECT, 'reviewed':False}).status_code == 409
    response = client.post(path, json={'project':PROJECT,'reviewed':True})
    assert response.status_code == 200, response.text
    result = response.json()
    assert client.post(path, json={'project':PROJECT,'reviewed':True}).json()['project_id'] == result['project_id']
    assert len(client.get('/api/projects').json()) == 1
    evidence = client.get('/api/projects/'+result['project_id']+'/evidence').json()
    assert len(evidence) == 3 and all(e['review_state'] == 'pending' for e in evidence)
    assert any(e['value']['analysis_status'] == 'failed' for e in evidence)
    for source in b['files']:
        downloaded = client.get('/api/projects/'+result['project_id']+'/files/'+source['file_id'])
        assert downloaded.status_code == 200


def test_intake_epw_uses_real_parser_and_creates_weather_workspace(client):
    epw = Path('fixtures/demo/reference_5zone/weather.epw').read_bytes()
    b = batch(client, [('weather.epw', epw)])
    assert b['suggestions'] == {}  # Weather station is not the building location.
    facts = b['files'][0]['analysis']['facts']
    assert facts['quality']['records'] == 8760
    assert facts['annual']['solar_kwh_m2'] == pytest.approx(1619.948)
    r = client.post('/api/intakes/'+b['id']+'/commit', json={'project':PROJECT,'reviewed':True})
    assert r.status_code == 200, r.text
    pid = r.json()['project_id']
    assert len(client.get('/api/projects/'+pid+'/weather').json()) == 1
    assert not client.get('/api/projects/'+pid+'/gate').json()['can_simulate']


def test_inbox_private_durable_and_no_changed_source_commit(client):
    b = batch(client, [('brief.txt', b'name: fixture')])
    app = client.app
    with TestClient(app) as other:
        assert register(other, 'other').status_code == 200
        assert other.get('/api/intakes/'+b['id']).status_code == 404
        assert other.post('/api/intakes/'+b['id']+'/analyze').status_code == 404
    restarted = create_app(app.state.domain.store.root, start_worker=False)
    with TestClient(restarted) as same:
        login = same.post('/api/auth/login', json={'username':'test_owner','password':'Test-only-long-pass-2026'})
        assert login.status_code == 200
        assert same.get('/api/intakes/'+b['id']).json()['status'] == 'review'
    source = app.state.domain.store.root / b['files'][0]['path']
    source.write_text('tampered')
    assert client.post('/api/intakes/'+b['id']+'/commit', json={'project':PROJECT,'reviewed':True}).status_code == 409
    assert client.get('/api/projects').json() == []


def test_xlsx_and_pdf_real_parsers(tmp_path):
    import openpyxl
    from reportlab.pdfgen.canvas import Canvas
    xlsx = tmp_path/'equipment.xlsx'
    book = openpyxl.Workbook()
    book.active.append(['equipment','power_kw'])
    book.active.append(['fan',2])
    book.save(xlsx)
    assert parse_source(xlsx)['facts']['sheets'][0]['rows'] == 2
    pdf = tmp_path/'brief.pdf'
    canvas = Canvas(str(pdf))
    canvas.drawString(30,750,'area_m2: 350.5 m2')
    canvas.save()
    parsed = parse_source(pdf)
    assert parsed['candidates'][0]['value'] == 350.5
    assert parsed['candidates'][0]['locator'] == 'PDF 第 1 页'


def test_agent_tasks_have_distinct_tools_and_unknown_request_is_partial(client):
    from backend.agent import Chat
    pid = client.post('/api/projects', json=PROJECT).json()['project_id']
    agent = client.app.state.agent
    expected = {'weather': 'weather_summary', 'model': 'model_validate',
                'simulation': 'simulation_status', 'materials': 'material_list', 'evidence': 'evidence_list'}
    summaries = []
    for task, tool in expected.items():
        result = agent.start(pid, Chat(message='检查', task=task), background=False)
        assert result['status'] == 'succeeded'
        assert tool in result['answer']['basis']
        assert result['resolved_task'] == task
        summaries.append(result['answer']['summary'])
    assert len(set(summaries)) == 5
    result = agent.start(pid, Chat(message='帮我做一下那个东西'), background=False)
    assert result['status'] == 'partial' and result['answer']['needs_clarification']
    assert not agent.store.jobs(pid)


def test_metadata_amendment_retains_file_and_history_reopens_review(client):
    b = batch(client, [('brief.txt', b'name: fixture')])
    pid = client.post('/api/intakes/'+b['id']+'/commit', json={'project':PROJECT,'reviewed':True}).json()['project_id']
    ev = client.get('/api/projects/'+pid+'/evidence').json()[0]
    path = f'/api/projects/{pid}/evidence/{ev["evidence_id"]}'
    metadata = {'expected_revision':1, 'source_locator':'现场调研表第 1 页', 'authority':'项目业主 2026-10-23',
                'permission':'测试授权声明', 'responsible_person':'测试工程师'}
    amended = client.put(path+'/metadata', json=metadata)
    assert amended.status_code == 200
    assert amended.json()['hash'] == ev['hash'] and amended.json()['review_state'] == 'pending'
    assert client.put(path+'/metadata', json=metadata).status_code == 409
    assert len(client.get(path+'/history').json()) == 2


def test_commit_rolls_back_all_records_on_database_failure(client):
    import sqlite3
    b = batch(client, [('brief.txt', b'name: fixture')])
    with client.app.state.domain.store.connect() as con:
        con.executescript("CREATE TRIGGER reject_inbox_evidence BEFORE INSERT ON records WHEN NEW.kind='evidence' BEGIN SELECT RAISE(ABORT, 'test disk failure'); END;")
    with pytest.raises(sqlite3.IntegrityError):
        client.post('/api/intakes/'+b['id']+'/commit', json={'project':PROJECT,'reviewed':True})
    assert client.get('/api/projects').json() == []
    assert client.get('/api/intakes/'+b['id']).json()['status'] == 'review'


def test_password_change_requires_current_password_revokes_old_credentials(client):
    old_cookie = client.cookies.get('vra_session')
    response = client.post('/api/auth/password', json={'current_password':'wrong-passphrase!','new_password':'Replacement-test-password!2026'})
    assert response.status_code == 401
    changed = client.post('/api/auth/password', json={'current_password':'Test-only-long-pass-2026','new_password':'Replacement-test-password!2026'})
    assert changed.status_code == 200
    client.headers['X-CSRF-Token'] = changed.json()['csrf_token']
    assert client.cookies.get('vra_session') != old_cookie
    with TestClient(client.app) as old:
        old.cookies.set('vra_session', old_cookie, domain='testserver.local', path='/')
        assert old.get('/api/projects').status_code == 401
        assert old.post('/api/auth/login', json={'username':'test_owner','password':'Test-only-long-pass-2026'}).status_code == 401
        assert old.post('/api/auth/login', json={'username':'test_owner','password':'Replacement-test-password!2026'}).status_code == 200


def test_invitation_revoke_expiry_and_discard_owner_scope(client, monkeypatch):
    monkeypatch.delenv('VRA_REGISTRATION_MODE')
    invitation = client.post('/api/admin/invitations', json={'label':'expired'}).json()
    with client.app.state.domain.store.connect() as con:
        con.execute('UPDATE invitations SET expires=0 WHERE id=?', (invitation['id'],))
    with TestClient(client.app) as guest:
        assert register(guest, 'expired_user', invitation['invitation']).status_code == 403
    invitation = client.post('/api/admin/invitations', json={'label':'revoked'}).json()
    assert client.delete('/api/admin/invitations/'+invitation['id']).status_code == 200
    with TestClient(client.app) as guest:
        assert register(guest, 'revoked_user', invitation['invitation']).status_code == 403
    b = batch(client, [('draft.txt', b'draft file')])
    path = client.app.state.domain.store.root / b['files'][0]['path']
    with TestClient(client.app) as guest:
        invitation = client.post('/api/admin/invitations', json={'label':'guest'}).json()
        assert register(guest, 'guest_user', invitation['invitation']).status_code == 200
        assert guest.delete('/api/intakes/'+b['id']).status_code == 404
    assert path.is_file()
    assert client.delete('/api/intakes/'+b['id']).json()['deleted']
    assert not path.exists() and client.get('/api/intakes/'+b['id']).status_code == 404


def test_existing_database_migrates_without_password_or_project_changes(tmp_path):
    from backend.auth import Auth, password_hash
    from backend.store import Store
    store = Store(tmp_path/'old')
    salt = 'ab'*16
    hashed = password_hash('Legacy-test-password!', salt)
    with store.connect() as con:
        con.execute('CREATE TABLE users(id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, display_name TEXT NOT NULL, salt TEXT NOT NULL,password_hash TEXT NOT NULL)')
        con.execute('INSERT INTO users VALUES (?,?,?,?,?)', ('user_legacy','legacy','Existing owner',salt,hashed))
    auth = Auth(store)
    assert not auth.setup_required() and auth.is_admin('user_legacy')
    with store.connect() as con:
        row = con.execute('SELECT * FROM users').fetchone()
        assert row['password_hash'] == hashed and row['salt'] == salt and row['disabled'] == 0
        assert con.execute('PRAGMA user_version').fetchone()[0] == 2


def test_explicit_fields_do_not_guess_area_or_send_document_preview():
    from backend.intake import text_candidates
    from backend.agent import provider_context
    assert not text_candidates('area_m2: 1,2 m2', 'test')
    assert not text_candidates('drawing shows 500 m2 somewhere', 'test')
    assert text_candidates('area_m2: 1,200.5 m2', 'test')[0]['value'] == 1200.5
    original = {'value': {'facts': {'text_preview': 'private extracted page', 'pages':1}, 'candidates':[{'excerpt':'private line','value':500}]}}
    public = provider_context(original)
    assert 'private' not in json.dumps(public) and public['value']['facts']['pages'] == 1
    assert original['value']['facts']['text_preview'] == 'private extracted page'


def test_dxf_batch_runs_existing_geometry_pipeline(client, tmp_path):
    import ezdxf
    drawing = ezdxf.new()
    drawing.header['$INSUNITS'] = 6
    drawing.modelspace().add_lwpolyline([(0,0),(10,0),(10,10),(0,10)], close=True)
    path = tmp_path/'room.dxf'
    drawing.saveas(path)
    b = batch(client, [(path.name, path.read_bytes())])
    response = client.post('/api/intakes/'+b['id']+'/commit', json={'project':PROJECT,'reviewed':True})
    assert response.status_code == 200
    prepared = list(response.json()['prepared'].values())
    assert prepared[0]['status'] == 'awaiting_review'
    imports = client.app.state.domain.store.list('import', response.json()['project_id'])
    assert len(imports[0]['candidate']['rooms']) == 1
    assert imports[0]['candidate']['rooms'][0]['height_m'] == 3  # Default candidate setting, not measured height.
    assert '层高' in ''.join(imports[0]['candidate']['warnings'])
