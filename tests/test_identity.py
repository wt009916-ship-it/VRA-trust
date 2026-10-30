from urllib.parse import parse_qs,urlsplit
import pytest
import pyotp
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from backend.api import create_app

PASSWORD='Identity-isolation-long-pass-2026!'

@pytest.fixture
def identity_client(tmp_path,monkeypatch):
    monkeypatch.setenv('VRA_IDENTITY_KEY',Fernet.generate_key().decode())
    app=create_app(tmp_path/'identity',start_worker=False)
    with TestClient(app) as c:
        r=c.post('/api/auth/register',json={'username':'identity_owner','display_name':'Isolated identity owner','password':PASSWORD})
        assert r.status_code==200,r.text
        c.headers['X-CSRF-Token']=r.json()['csrf_token']
        yield c,app

def enroll(c):
    r=c.post('/api/auth/mfa/enroll',json={'current_password':PASSWORD})
    assert r.status_code==200,r.text
    return parse_qs(urlsplit(r.json()['provisioning_uri']).query)['secret'][0]

def enable(c,secret):
    r=c.post('/api/auth/mfa/enable',json={'code':pyotp.TOTP(secret).now()})
    assert r.status_code==200,r.text
    c.headers['X-CSRF-Token']=r.json()['csrf_token']
    return r.json()['recovery_codes']

def test_mfa_enrollment_login_replay_and_recovery(identity_client):
    c,app=identity_client
    secret=enroll(c)
    assert c.post('/api/auth/mfa/enable',json={'code':'not-valid'}).status_code==401
    codes=enable(c,secret)
    assert len(codes)==10
    status=c.get('/api/auth/security').json()
    assert status['mfa']=={'enabled':True,'recovery_codes_remaining':10}
    with app.state.domain.store.connect() as con:
        assert secret not in con.execute('SELECT secret FROM account_mfa').fetchone()[0]
        used_step=con.execute('SELECT last_step FROM account_mfa').fetchone()[0]
        assert codes[0].replace('-','') not in str(con.execute('SELECT * FROM mfa_recovery').fetchall())
    c.post('/api/auth/logout');c.headers.pop('X-CSRF-Token')
    login=c.post('/api/auth/login',json={'username':'identity_owner','password':PASSWORD})
    assert login.status_code==200 and login.json()['mfa_required']
    assert 'set-cookie' not in login.headers and c.get('/api/projects').status_code==401
    challenge=login.json()['challenge']
    assert c.post('/api/auth/mfa/verify',json={'challenge':challenge,'code':pyotp.TOTP(secret).at(used_step*30)}).status_code==401
    r=c.post('/api/auth/mfa/verify',json={'challenge':challenge,'code':codes[0]})
    assert r.status_code==200 and r.json()['user']['assurance']=='pwd+otp'
    assert c.post('/api/auth/mfa/verify',json={'challenge':challenge,'code':codes[1]}).status_code==401
    c.headers['X-CSRF-Token']=r.json()['csrf_token']
    assert c.get('/api/auth/security').json()['mfa']['recovery_codes_remaining']==9

def test_wrong_codes_exhaust_challenge_and_old_sessions_revoked(identity_client):
    c,app=identity_client
    old=c.cookies.get('vra_session')
    secret=enroll(c);enable(c,secret)
    with TestClient(app) as old_client:
        old_client.cookies.set('vra_session',old)
        assert old_client.get('/api/projects').status_code==401
    login=c.post('/api/auth/login',json={'username':'identity_owner','password':PASSWORD}).json()
    for _ in range(5):assert c.post('/api/auth/mfa/verify',json={'challenge':login['challenge'],'code':'invalid'}).status_code==401
    with app.state.domain.store.connect() as con:
        assert con.execute('SELECT attempts FROM login_challenges').fetchone()[0]==5

def test_mail_token_single_use_reset_and_mfa_preserved(identity_client):
    from backend.identity_security import IdentitySettings,unseal
    import json
    c,app=identity_client
    identity=app.state.identity
    identity.config.save(IdentitySettings(smtp_enabled=True,smtp_host='127.0.0.1',smtp_port=8892,smtp_tls='loopback',smtp_from='noreply@example.com'))
    assert c.post('/api/auth/email/bind',json={'current_password':PASSWORD,'address':'owner@example.com'}).status_code==200
    with app.state.domain.store.connect() as con:
        mail=json.loads(unseal(con.execute('SELECT payload FROM identity_outbox').fetchone()[0]))
    token=mail['text'].split('/#verify-email/')[1].split()[0]
    assert c.post('/api/auth/email/verify',json={'token':token}).status_code==200
    assert c.post('/api/auth/email/verify',json={'token':token}).status_code==400
    known=c.post('/api/auth/recovery/request',json={'address':'owner@example.com'})
    unknown=c.post('/api/auth/recovery/request',json={'address':'unknown@example.com'})
    assert known.json()==unknown.json()
    with app.state.domain.store.connect() as con:
        mails=[json.loads(unseal(r[0])) for r in con.execute('SELECT payload FROM identity_outbox')]
    token=next(m['text'] for m in mails if '/#reset-password/' in m['text']).split('/#reset-password/')[1].split()[0]
    secret=enroll(c);codes=enable(c,secret)
    assert c.post('/api/auth/recovery/complete',json={'token':token,'new_password':'New-identity-password-for-recovery!'}).status_code==401
    r=c.post('/api/auth/recovery/complete',json={'token':token,'new_password':'New-identity-password-for-recovery!','factor_code':codes[0]})
    assert r.status_code==200,r.text
    assert c.get('/api/auth/me').status_code==401
    assert identity.mfa.enabled(app.state.auth.verify_credentials(__import__('backend.auth',fromlist=['Credentials']).Credentials(username='identity_owner',password='New-identity-password-for-recovery!'))['id'])
    assert c.post('/api/auth/recovery/complete',json={'token':token,'new_password':'Another-independent-password!'}).status_code==400

def test_external_insecure_identity_endpoints_rejected(identity_client):
    from backend.identity_security import IdentitySettings
    from pydantic import ValidationError
    for body in [{'public_url':'http://production.example.com'},{'smtp_host':'192.168.1.3','smtp_tls':'loopback'},{'oidc_enabled':True,'oidc_issuer':'http://idp.example.com','oidc_client_id':'client'}]:
        with pytest.raises(ValidationError):IdentitySettings(**body)
