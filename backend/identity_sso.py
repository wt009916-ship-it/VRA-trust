"""OIDC authorization-code + PKCE with server state and explicit subject linking."""
import hashlib
import hmac
import json
import secrets
import time
from urllib.parse import urlsplit

import httpx
from authlib.integrations.httpx_client import AsyncOAuth2Client
from fastapi import HTTPException
from joserfc import jwt
from joserfc.jwk import KeySet
from joserfc.jwt import JWTClaimsRegistry

from .auth import digest
from .identity_security import seal, trusted_url, unseal


class SSO:
    cookie = 'vra_oidc_state'

    def __init__(self, identity):
        self.identity, self.store = identity, identity.store
        with self.store.connect() as con:
            con.executescript('''
                CREATE TABLE IF NOT EXISTS oidc_links (
                    issuer TEXT NOT NULL, subject TEXT NOT NULL, user_id TEXT NOT NULL,
                    PRIMARY KEY(issuer,subject), UNIQUE(issuer,user_id));
                CREATE TABLE IF NOT EXISTS oidc_transactions (
                    state_hash TEXT PRIMARY KEY, browser_hash TEXT NOT NULL, payload TEXT NOT NULL,
                    expires REAL NOT NULL);
            ''')

    def status(self, uid):
        config, _ = self.identity.config.read()
        with self.store.connect() as con:
            linked = con.execute('SELECT issuer FROM oidc_links WHERE user_id=?', (uid,)).fetchall()
        return {'configured': config.oidc_enabled, 'linked_issuers': [r['issuer'] for r in linked]}

    def fingerprint(self):
        public = self.identity.config.public()
        return digest(json.dumps({k: v for k, v in public.items() if k.startswith('oidc') or k == 'public_url'}, sort_keys=True))

    async def metadata(self):
        config, _ = self.identity.config.read()
        if not config.oidc_enabled:
            raise HTTPException(503, '工作区尚未启用企业登录')
        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
                r = await client.get(config.oidc_issuer+'/.well-known/openid-configuration')
                r.raise_for_status()
                data = r.json()
            if data['issuer'] != config.oidc_issuer:
                raise ValueError('issuer mismatch')
            issuer_url = urlsplit(config.oidc_issuer)
            allowed = {issuer_url.scheme+'://'+issuer_url.netloc, *config.oidc_endpoint_origins}
            for field in ('authorization_endpoint', 'token_endpoint', 'jwks_uri'):
                endpoint = urlsplit(trusted_url(data[field]))
                if endpoint.scheme+'://'+endpoint.netloc not in allowed:
                    raise ValueError('provider endpoint origin is not explicitly allowed')
            if 'S256' not in data.get('code_challenge_methods_supported', []):
                raise ValueError('provider does not advertise PKCE S256')
            return data
        except (httpx.HTTPError, KeyError, ValueError):
            raise HTTPException(503, '企业身份平台元数据不可用或不符合OIDC/PKCE要求') from None

    async def start(self, *, uid=None, session_hash=None, remember=False):
        config, _ = self.identity.config.read()
        metadata = await self.metadata()
        state, browser, nonce, verifier = [secrets.token_urlsafe(32) for _ in range(4)]
        row = None
        if uid:
            with self.store.connect() as con:
                row = con.execute('SELECT password_hash FROM users WHERE id=? AND disabled=0', (uid,)).fetchone()
            if not row:
                raise HTTPException(401, '账号不可用')
        async with AsyncOAuth2Client(client_id=config.oidc_client_id, scope='openid profile email',
                                     redirect_uri=config.public_url+'/api/auth/sso/callback',
                                     code_challenge_method='S256') as client:
            url, _ = client.create_authorization_url(metadata['authorization_endpoint'], state=state,
                nonce=nonce, code_verifier=verifier, prompt='login' if uid else 'select_account')
        data = {'nonce': nonce, 'verifier': verifier, 'user_id': uid, 'session_hash': session_hash,
                'password_version': row['password_hash'] if row else None, 'remember': bool(remember),
                'config_version': self.fingerprint()}
        with self.store.connect() as con:
            con.execute('DELETE FROM oidc_transactions WHERE expires<?', (time.time(),))
            con.execute('INSERT INTO oidc_transactions VALUES (?,?,?,?)',
                        (digest(state), digest(browser), seal(json.dumps(data)), time.time()+300))
        return url, browser

    async def complete(self, state, code, browser):
        with self.store.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            row = con.execute('SELECT * FROM oidc_transactions WHERE state_hash=?', (digest(state),)).fetchone()
            if not row or row['expires'] < time.time() or not hmac.compare_digest(row['browser_hash'], digest(browser)):
                raise HTTPException(400, '企业登录校验失败，请从登录页重新开始')
            con.execute('DELETE FROM oidc_transactions WHERE state_hash=?', (digest(state),))
            data = json.loads(unseal(row['payload']))
        if data['config_version'] != self.fingerprint():
            raise HTTPException(409, '企业登录配置已改变，请重新开始')
        config, _ = self.identity.config.read()
        metadata = await self.metadata()
        try:
            async with AsyncOAuth2Client(client_id=config.oidc_client_id,
                    client_secret=self.identity.config.secret('oidc_client_secret'),
                    token_endpoint_auth_method='client_secret_basic',
                    redirect_uri=config.public_url+'/api/auth/sso/callback', timeout=15) as client:
                tokens = await client.fetch_token(metadata['token_endpoint'], code=code,
                                                  code_verifier=data['verifier'], grant_type='authorization_code')
            async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
                keys = await client.get(metadata['jwks_uri'])
                keys.raise_for_status()
            claims = jwt.decode(tokens['id_token'], KeySet.import_key_set(keys.json()), algorithms=['RS256', 'ES256']).claims
            JWTClaimsRegistry(leeway=30, iss={'essential': True, 'value': config.oidc_issuer},
                aud={'essential': True, 'value': config.oidc_client_id}, exp={'essential': True},
                iat={'essential': True}, sub={'essential': True},
                nonce={'essential': True, 'value': data['nonce']}).validate(claims)
            if not isinstance(claims['sub'], str) or not claims['sub'] or len(claims['sub']) > 255:
                raise ValueError('invalid subject')
            audience = claims['aud']
            if (isinstance(audience, list) and len(audience) > 1 and claims.get('azp') != config.oidc_client_id) or claims.get('azp', config.oidc_client_id) != config.oidc_client_id:
                raise ValueError('invalid authorized party')
            if claims.get('at_hash'):
                import base64
                expected = base64.urlsafe_b64encode(hashlib.sha256(tokens['access_token'].encode()).digest()[:16]).rstrip(b'=').decode()
                if not hmac.compare_digest(expected, claims['at_hash']):
                    raise ValueError('access token hash mismatch')
        except Exception:
            raise HTTPException(401, '企业身份验证失败，未创建本地登录会话') from None
        if data['user_id']:
            with self.store.connect() as con:
                con.execute('BEGIN IMMEDIATE')
                active = con.execute('SELECT 1 FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.user_id=? AND s.expires>? AND u.password_hash=? AND u.disabled=0',
                    (data['session_hash'], data['user_id'], time.time(), data['password_version'])).fetchone()
                if not active:
                    raise HTTPException(401, '绑定前的本地会话已失效，请重新登录后绑定')
                existing = con.execute('SELECT user_id FROM oidc_links WHERE issuer=? AND subject=?', (config.oidc_issuer, claims['sub'])).fetchone()
                if existing and existing['user_id'] != data['user_id']:
                    raise HTTPException(409, '此企业身份已绑定其他账号')
                own = con.execute('SELECT subject FROM oidc_links WHERE issuer=? AND user_id=?', (config.oidc_issuer, data['user_id'])).fetchone()
                if own and own['subject'] != claims['sub']:
                    raise HTTPException(409, '此账号已绑定其他企业身份，请先显式解除绑定')
                con.execute('INSERT OR IGNORE INTO oidc_links VALUES (?,?,?)', (config.oidc_issuer, claims['sub'], data['user_id']))
                self.identity.mfa.audit(con, data['user_id'], 'oidc_subject_linked')
            return {'linked': True}
        with self.store.connect() as con:
            account = con.execute('SELECT u.* FROM oidc_links l JOIN users u ON u.id=l.user_id WHERE l.issuer=? AND l.subject=? AND u.disabled=0', (config.oidc_issuer, claims['sub'])).fetchone()
        # No auto-link by email and no implicit account/administrator provisioning.
        if not account:
            raise HTTPException(403, '企业身份未绑定可用账号，请先用本地账号登录并绑定')
        if self.identity.mfa.enabled(account['id']):
            return self.identity.mfa.challenge(account, data['remember'], primary_method='oidc')
        return self.identity.auth.new_session(account['id'], data['remember'], assurance='oidc',
                                               expected_password_hash=account['password_hash'])
