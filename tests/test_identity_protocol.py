"""Protocol rejection tests supplement the real Keycloak/Mailpit acceptance."""
import asyncio
import json
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi import HTTPException
from joserfc import jwt
from joserfc.jwk import RSAKey

from backend.identity_security import IdentitySettings, unseal
from test_identity import PASSWORD, enable, enroll

pytest_plugins = ['test_identity']


def test_mfa_expiry_session_binding_and_atomic_recovery(identity_client):
    c, app = identity_client
    secret = enroll(c)
    with app.state.domain.store.connect() as con:
        con.execute('UPDATE account_mfa SET expires=0')
    assert c.post('/api/auth/mfa/enable', json={'code': '123456'}).status_code == 409
    secret = enroll(c)
    codes = enable(c, secret)
    uid = c.get('/api/auth/me').json()['user']['id']
    mfa = app.state.identity.mfa

    def consume():
        try:
            mfa.check(uid, codes[0])
            return True
        except HTTPException:
            return False
    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(lambda _: consume(), range(2))) == [False, True]
    challenge = c.post('/api/auth/login', json={'username': 'identity_owner', 'password': PASSWORD}).json()['challenge']
    with app.state.domain.store.connect() as con:
        con.execute('UPDATE login_challenges SET expires=0')
    assert c.post('/api/auth/mfa/verify', json={'challenge': challenge, 'code': codes[1]}).status_code == 401


def test_rotate_then_disable_revokes_old_codes_and_sessions(identity_client):
    c, app = identity_client
    codes = enable(c, enroll(c))
    r = c.post('/api/auth/mfa/recovery-codes', json={'current_password': PASSWORD, 'factor_code': codes[0]})
    assert r.status_code == 200, r.text
    c.headers['X-CSRF-Token'] = r.json()['csrf_token']
    new = r.json()['recovery_codes']
    uid = r.json()['user']['id']
    with pytest.raises(HTTPException):
        app.state.identity.mfa.check(uid, codes[1])
    r = c.post('/api/auth/mfa/disable', json={'current_password': PASSWORD, 'factor_code': new[0]})
    assert r.status_code == 200, r.text
    assert r.json()['user']['assurance'] == 'pwd'
    c.headers['X-CSRF-Token'] = r.json()['csrf_token']
    assert c.get('/api/auth/security').json()['mfa'] == {'enabled': False, 'recovery_codes_remaining': 0}
    with app.state.domain.store.connect() as con:
        assert con.execute('SELECT COUNT(*) FROM sessions').fetchone()[0] == 1


def test_mail_failure_is_durable_and_expired_tokens_rejected(identity_client, monkeypatch):
    c, app = identity_client
    mail = app.state.identity.mail
    app.state.identity.config.save(IdentitySettings(smtp_enabled=True, smtp_host='127.0.0.1', smtp_port=8892,
                                                   smtp_tls='loopback', smtp_from='noreply@example.com'))
    assert c.post('/api/auth/email/bind', json={'current_password': PASSWORD, 'address': 'owner@example.com'}).status_code == 200
    with app.state.domain.store.connect() as con:
        payload = json.loads(unseal(con.execute('SELECT payload FROM identity_outbox').fetchone()[0]))
        token = payload['text'].split('/#verify-email/')[1].split()[0]
        con.execute('UPDATE email_tokens SET expires=0')
    assert c.post('/api/auth/email/verify', json={'token': token}).status_code == 400

    def unavailable(*args, **kwargs):
        raise ConnectionRefusedError('never expose SMTP password or reset link')
    monkeypatch.setattr('backend.identity_mail.smtplib.SMTP', unavailable)
    for _ in range(5):
        assert mail.deliver_pending()
        with app.state.domain.store.connect() as con:
            con.execute('UPDATE identity_outbox SET retry_at=0')
    with app.state.domain.store.connect() as con:
        row = con.execute('SELECT * FROM identity_outbox').fetchone()
        assert row['state'] == 'failed' and row['attempts'] == 5
        assert row['error'] == 'ConnectionRefusedError'
    assert not mail.deliver_pending()


@pytest.mark.parametrize('failure', ['valid', 'signature', 'issuer', 'audience', 'nonce', 'expired', 'azp', 'unlinked', 'browser', 'state_replay', 'changed_password'])
def test_oidc_claims_state_and_explicit_subject_mapping(identity_client, monkeypatch, failure):
    c, app = identity_client
    identity = app.state.identity
    uid = c.get('/api/auth/me').json()['user']['id']
    issuer = 'https://idp.example.com/realm'
    identity.config.save(IdentitySettings(oidc_enabled=True, oidc_issuer=issuer, oidc_client_id='vra', oidc_client_secret='fixture-only-secret'))
    key = RSAKey.generate_key(2048)
    key.ensure_kid()
    metadata = {'issuer': issuer, 'authorization_endpoint': issuer+'/authorize', 'token_endpoint': issuer+'/token',
                'jwks_uri': issuer+'/keys', 'code_challenge_methods_supported': ['S256']}
    real_client = httpx.AsyncClient
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json=metadata if 'well-known' in r.url.path else {'keys': [key.as_dict(private=False)]}))
    monkeypatch.setattr('backend.identity_sso.httpx.AsyncClient', lambda **kwargs: real_client(transport=transport, **kwargs))
    url, browser = asyncio.run(identity.sso.start())
    query = parse_qs(urlsplit(url).query)
    assert query['code_challenge_method'] == ['S256']
    assert query['code_challenge'][0]
    with identity.store.connect() as con:
        tx = json.loads(unseal(con.execute('SELECT payload FROM oidc_transactions').fetchone()[0]))
        assert tx['verifier'] != query['code_challenge'][0]
        if failure != 'unlinked':
            con.execute('INSERT INTO oidc_links VALUES (?,?,?)', (issuer, 'subject-one', uid))
    claims = {'iss': issuer, 'aud': 'vra', 'sub': 'subject-one', 'iat': int(time.time()), 'exp': int(time.time())+300, 'nonce': query['nonce'][0]}
    if failure == 'issuer': claims['iss'] = 'https://attacker.example.com'
    if failure == 'audience': claims['aud'] = 'another-client'
    if failure == 'nonce': claims['nonce'] = 'wrong-browser-nonce'
    if failure == 'expired': claims['exp'] = int(time.time())-90
    if failure == 'azp': claims.update(aud=['vra', 'other'], azp='other')
    token = jwt.encode({'alg': 'RS256', 'kid': key.kid}, claims, RSAKey.generate_key(2048) if failure == 'signature' else key)

    class Exchange:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def fetch_token(self, endpoint, **kwargs):
            assert kwargs['code_verifier'] == tx['verifier']
            if failure == 'changed_password':
                # Change after identity lookup but before session commit below.
                original = identity.auth.new_session
                def changed(*args, **kw):
                    with identity.store.connect() as con:
                        con.execute("UPDATE users SET password_hash='rotated' WHERE id=?", (uid,))
                    return original(*args, **kw)
                monkeypatch.setattr(identity.auth, 'new_session', changed)
            return {'id_token': token, 'access_token': 'fixture-access-token'}
    monkeypatch.setattr('backend.identity_sso.AsyncOAuth2Client', Exchange)
    if failure in {'valid', 'state_replay'}:
        assert asyncio.run(identity.sso.complete(query['state'][0], 'fixture-code', browser))[1]['assurance'] == 'oidc'
        with pytest.raises(HTTPException):
            asyncio.run(identity.sso.complete(query['state'][0], 'fixture-code', browser))
    else:
        with pytest.raises(HTTPException) as exc:
            asyncio.run(identity.sso.complete(query['state'][0], 'fixture-code', 'other-browser' if failure == 'browser' else browser))
        assert exc.value.status_code in {400, 401, 403}


def test_secrets_not_returned_and_destination_change_requires_new_secret(identity_client):
    _, app = identity_client
    config = app.state.identity.config
    config.save(IdentitySettings(oidc_enabled=True, oidc_issuer='https://idp.example.com', oidc_client_id='vra', oidc_client_secret='not-for-browser'))
    assert 'not-for-browser' not in json.dumps(config.public())
    assert 'not-for-browser' not in config.path.read_text()
    with pytest.raises(HTTPException):
        config.save(IdentitySettings(oidc_enabled=True, oidc_issuer='https://other.example.com', oidc_client_id='vra'))


def test_cross_site_navigation_only_allowed_for_validated_oidc_callback(identity_client):
    c, _ = identity_client
    # Invalid state still fails closed, but reaches the callback rather than being
    # rejected by generic Fetch Metadata protection before OIDC validation.
    r = c.get('/api/auth/sso/callback?state=invalid&code=invalid', headers={'Sec-Fetch-Site': 'cross-site'}, follow_redirects=False)
    assert r.status_code == 303 and r.headers['location'] == '/#sso-failed'
    assert c.get('/api/projects', headers={'Sec-Fetch-Site': 'cross-site'}).status_code == 403
    assert c.post('/api/auth/login', headers={'Sec-Fetch-Site': 'cross-site'}, json={'username': 'identity_owner', 'password': PASSWORD}).status_code == 403


def test_admin_second_factor_failures_are_rate_limited(identity_client):
    c, app = identity_client
    enable(c, enroll(c))
    uid = c.get('/api/auth/me').json()['user']['id']
    for _ in range(8):
        r = c.post(f'/api/admin/users/{uid}/revoke-access', json={'current_password': PASSWORD, 'factor_code': 'not-a-code'})
        assert r.status_code == 403
        assert c.get('/api/auth/me').status_code == 200
    assert c.post(f'/api/admin/users/{uid}/revoke-access', json={'current_password': PASSWORD, 'factor_code': 'not-a-code'}).status_code == 429


def test_unlink_rotates_local_session_and_revokes_old_oidc_access(identity_client):
    c, app = identity_client
    uid = c.get('/api/auth/me').json()['user']['id']
    old, _ = app.state.auth.new_session(uid, assurance='oidc')
    with app.state.domain.store.connect() as con:
        con.execute('INSERT INTO oidc_links VALUES (?,?,?)', ('https://idp.example.com', 'subject-one', uid))
    r = c.post('/api/auth/sso/unlink', json={'current_password': PASSWORD, 'issuer': 'https://idp.example.com'})
    assert r.status_code == 200 and r.json()['user']['assurance'] == 'pwd'
    assert app.state.auth.session(old) is None
    assert app.state.identity.sso.status(uid)['linked_issuers'] == []
