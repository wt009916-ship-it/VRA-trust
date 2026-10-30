import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from backend.api import create_app
from backend.auth import validate_password

PASSWORD='A separate long passphrase for session checks'

def test_policy_accepts_passphrases_and_blocks_known_common_values():
    for good in [PASSWORD,'a different independent phrase','中文口令支持空格 用于测试随机独立会话确认']:
        validate_password(good)
    for bad in ['too-short!', 'passwordpassword', 'aaaaaaaaaaaaaaaaaaaa', '12345678901234567890']:
        with pytest.raises(HTTPException): validate_password(bad)

def test_remember_cookie_and_safe_owned_session_management(tmp_path):
    app=create_app(tmp_path/'auth-policy',start_worker=False)
    with TestClient(app) as first, TestClient(app) as other:
        r=first.post('/api/auth/register',json={'username':'session_owner','display_name':'Isolated account','password':PASSWORD})
        assert r.status_code==200,r.text
        assert 'Max-Age' not in r.headers['set-cookie']
        first.headers['X-CSRF-Token']=r.json()['csrf_token']
        r=other.post('/api/auth/login',json={'username':'session_owner','password':PASSWORD,'remember_device':True})
        assert r.status_code==200 and 'Max-Age=43200' in r.headers['set-cookie']
        other.headers['X-CSRF-Token']=r.json()['csrf_token']
        sessions=first.get('/api/auth/sessions')
        assert sessions.status_code==200 and len(sessions.json())==2
        assert sum(s['current'] for s in sessions.json())==1
        assert all(s['expires_at']>s['created_at'] for s in sessions.json())
        assert not any(s in sessions.text for s in ['token_hash','csrf','password_hash',first.cookies.get('vra_session')])
        bad=first.post('/api/auth/sessions/revoke-others',json={'current_password':'wrong-password'})
        assert bad.status_code==401 and other.get('/api/auth/me').status_code==200
        first.headers.pop('X-CSRF-Token')
        assert first.post('/api/auth/sessions/revoke-others',json={'current_password':PASSWORD}).status_code==403
        first.headers['X-CSRF-Token']=r.json()['csrf_token'] # The other session token cannot authorize this browser.
        assert first.post('/api/auth/sessions/revoke-others',json={'current_password':PASSWORD}).status_code==403
        first.headers['X-CSRF-Token']=first.get('/api/auth/me').json()['csrf_token']
        assert first.post('/api/auth/sessions/revoke-others',json={'current_password':PASSWORD}).json()=={'revoked':1}
        assert other.get('/api/auth/me').status_code==401
        assert first.get('/api/auth/me').status_code==200

def test_security_headers_on_denials_and_strict_remember_value(tmp_path):
    app=create_app(tmp_path/'auth-headers',start_worker=False)
    with TestClient(app) as client:
        r=client.get('/api/auth/sessions')
        assert r.status_code==401 and r.headers['cache-control']=='no-store'
        assert r.headers['x-content-type-options']=='nosniff'
        assert 'frame-ancestors' in r.headers['content-security-policy']
        r=client.post('/api/auth/login',json={'username':'engineer','password':PASSWORD,'remember_device':'true'})
        assert r.status_code==422 and r.headers['cache-control']=='no-store'


def test_expensive_password_hashes_have_bounded_capacity(tmp_path):
    from backend.auth import _hash_slots
    app=create_app(tmp_path/'hash-budget',start_worker=False)
    assert _hash_slots.acquire(blocking=False)
    assert _hash_slots.acquire(blocking=False)
    try:
        with TestClient(app) as client:
            r=client.post('/api/auth/login',json={'username':'unregistered_user','password':PASSWORD})
            assert r.status_code==429 and r.headers['retry-after']=='2'
            assert r.headers['cache-control']=='no-store'
    finally:
        _hash_slots.release()
        _hash_slots.release()
