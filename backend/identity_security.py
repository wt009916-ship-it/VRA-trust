"""Encrypted identity configuration and local second-factor state."""
import base64
import hmac
import io
import json
import os
import secrets
import threading
import time
from urllib.parse import urlsplit

import pyotp
import qrcode
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from pydantic import Field, SecretStr, model_validator

from .auth import digest, password_hash
from .gateway import protect
from .schema import Contract


def seal(value):
    key = os.environ.get('VRA_IDENTITY_KEY')
    if key:
        return 'fernet:'+Fernet(key.encode()).encrypt(value.encode()).decode()
    if os.name == 'nt':
        return 'dpapi:'+protect(value)
    raise HTTPException(503, '请由部署管理员注入 VRA_IDENTITY_KEY 后使用身份安全功能')


def unseal(value):
    try:
        if value.startswith('fernet:'):
            return Fernet(os.environ['VRA_IDENTITY_KEY'].encode()).decrypt(value[7:].encode()).decode()
        if value.startswith('dpapi:'):
            return protect(value[6:], decrypt=True)
    except (KeyError, ValueError, InvalidToken):
        pass
    raise HTTPException(503, '身份密钥不可用，请联系部署管理员；不会退回明文验证')


def trusted_url(value, *, origin=False):
    p = urlsplit(value)
    local = p.hostname in {'127.0.0.1', 'localhost', '::1'}
    if (p.scheme != 'https' and not (p.scheme == 'http' and local)) or not p.hostname:
        raise ValueError('身份与公共地址须为HTTPS；仅回环地址允许HTTP联调')
    if p.username or p.password or p.query or p.fragment or (origin and p.path not in ('', '/')):
        raise ValueError('地址不得含凭据、查询或片段；公共地址只填写站点源')
    return value.rstrip('/')


class IdentitySettings(Contract):
    public_url: str = 'http://127.0.0.1:8767'
    oidc_enabled: bool = False
    oidc_issuer: str = ''
    oidc_client_id: str = ''
    oidc_endpoint_origins: list[str] = Field(default_factory=list, max_length=8)
    oidc_client_secret: SecretStr | None = Field(default=None, max_length=4096)
    smtp_enabled: bool = False
    smtp_host: str = Field(default='localhost', min_length=1, max_length=253)
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_tls: str = Field(default='starttls', pattern='^(starttls|tls|loopback)$')
    smtp_username: str = Field(default='', max_length=254)
    smtp_password: SecretStr | None = Field(default=None, max_length=4096)
    smtp_from: str = Field(default='', max_length=254)

    @model_validator(mode='after')
    def addresses(self):
        self.public_url = trusted_url(self.public_url, origin=True)
        if self.oidc_enabled:
            self.oidc_issuer = trusted_url(self.oidc_issuer)
            if not self.oidc_client_id:
                raise ValueError('启用OIDC须填写Client ID')
        self.oidc_endpoint_origins = [trusted_url(v, origin=True) for v in self.oidc_endpoint_origins]
        if self.smtp_tls == 'loopback' and self.smtp_host not in {'127.0.0.1', 'localhost', '::1'}:
            raise ValueError('不加密SMTP只允许回环隔离验收')
        if '\r' in self.smtp_host or '\n' in self.smtp_host:
            raise ValueError('SMTP主机无效')
        if self.smtp_enabled:
            from email_validator import validate_email
            self.smtp_from = validate_email(self.smtp_from, check_deliverability=False).normalized
        return self


class IdentityConfig:
    def __init__(self, store):
        self.path = store.root/'private'/'identity.json'
        self.lock = threading.RLock()

    def read(self):
        saved = json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {}
        config = IdentitySettings.model_validate({k: v for k, v in saved.items() if not k.endswith('_sealed')})
        return config, saved

    def public(self):
        config, saved = self.read()
        return {**config.model_dump(exclude={'smtp_password', 'oidc_client_secret'}),
                'oidc_secret_configured': bool(saved.get('oidc_client_secret_sealed')),
                'smtp_secret_configured': bool(saved.get('smtp_password_sealed')),
                'secret_storage': 'environment-key' if os.environ.get('VRA_IDENTITY_KEY') else 'Windows DPAPI' if os.name == 'nt' else 'not configured'}

    def save(self, body):
        with self.lock:
            return self._save(body)

    def _save(self, body):
        previous, old = self.read()
        if (body.oidc_issuer, body.oidc_client_id) != (previous.oidc_issuer, previous.oidc_client_id) and old.get('oidc_client_secret_sealed') and not body.oidc_client_secret:
            raise HTTPException(422, '更换企业身份平台时须提供对应的新Client Secret')
        if (body.smtp_host, body.smtp_port, body.smtp_username) != (previous.smtp_host, previous.smtp_port, previous.smtp_username) and old.get('smtp_password_sealed') and not body.smtp_password:
            raise HTTPException(422, '更换邮件服务时须提供对应的新SMTP密码')
        saved = body.model_dump(exclude={'smtp_password', 'oidc_client_secret'})
        for key in ('smtp_password', 'oidc_client_secret'):
            value = getattr(body, key)
            if value and value.get_secret_value():
                saved[key+'_sealed'] = seal(value.get_secret_value())
            elif old.get(key+'_sealed'):
                saved[key+'_sealed'] = old[key+'_sealed']
        if body.oidc_enabled and not saved.get('oidc_client_secret_sealed'):
            raise HTTPException(422, '本接入使用机密OIDC客户端，请配置Client Secret')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix('.tmp')
        temp.write_text(json.dumps(saved, ensure_ascii=False), encoding='utf-8')
        if os.name != 'nt':
            temp.chmod(0o600)
        temp.replace(self.path)

    def secret(self, key):
        _, saved = self.read()
        value = saved.get(key+'_sealed')
        return unseal(value) if value else ''


class MFA:
    def __init__(self, auth):
        self.auth, self.store = auth, auth.store
        with self.store.connect() as con:
            con.executescript('''
                CREATE TABLE IF NOT EXISTS account_mfa (
                    user_id TEXT PRIMARY KEY, secret TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 0,
                    last_step INTEGER NOT NULL DEFAULT -1, session_hash TEXT, expires REAL);
                CREATE TABLE IF NOT EXISTS mfa_recovery (
                    user_id TEXT NOT NULL, code_hash TEXT NOT NULL, used_at REAL,
                    PRIMARY KEY(user_id,code_hash));
                CREATE TABLE IF NOT EXISTS login_challenges (
                    token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL, password_version TEXT NOT NULL,
                    remember INTEGER NOT NULL, expires REAL NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, primary_method TEXT NOT NULL DEFAULT 'pwd');
            ''')

    def enabled(self, uid):
        with self.store.connect() as con:
            return bool(con.execute('SELECT 1 FROM account_mfa WHERE user_id=? AND enabled=1', (uid,)).fetchone())

    def status(self, uid):
        with self.store.connect() as con:
            remaining = con.execute('SELECT COUNT(*) FROM mfa_recovery WHERE user_id=? AND used_at IS NULL', (uid,)).fetchone()[0]
        return {'enabled': self.enabled(uid), 'recovery_codes_remaining': remaining}

    def password(self, uid, password):
        with self.store.connect() as con:
            row = con.execute('SELECT * FROM users WHERE id=? AND disabled=0', (uid,)).fetchone()
        if not row or not hmac.compare_digest(row['password_hash'], password_hash(password, row['salt'])):
            raise HTTPException(403, '当前密码不正确')
        return row

    def enroll(self, uid, token, password):
        row = self.password(uid, password)
        if self.enabled(uid):
            raise HTTPException(409, '已启用双重验证；请先按当前验证方式管理')
        secret = pyotp.random_base32()
        with self.store.connect() as con:
            con.execute('INSERT INTO account_mfa VALUES (?,?,0,-1,?,?) ON CONFLICT(user_id) DO UPDATE SET secret=excluded.secret,session_hash=excluded.session_hash,expires=excluded.expires',
                        (uid, seal(secret), digest(token), time.time()+600))
        uri = pyotp.TOTP(secret).provisioning_uri(row['username'], issuer_name='稀土智暖 VRA-Trust')
        output = io.BytesIO()
        qrcode.make(uri).save(output, format='PNG')
        return {'provisioning_uri': uri, 'qr_image': 'data:image/png;base64,'+base64.b64encode(output.getvalue()).decode(), 'expires_in': 600}

    @staticmethod
    def match(secret, code, now):
        if not code or not code.isdigit() or len(code) != 6:
            return None
        totp = pyotp.TOTP(secret)
        step = int(now)//30
        for counter in (step-1, step, step+1):
            if counter >= 0 and hmac.compare_digest(totp.at(counter*30), code):
                return counter
        return None

    def factor(self, con, uid, code, *, pending=False):
        row = con.execute('SELECT * FROM account_mfa WHERE user_id=?', (uid,)).fetchone()
        if not row or (not pending and not row['enabled']):
            return False
        now = time.time()
        step = self.match(unseal(row['secret']), code, now)
        if step is not None and step > row['last_step']:
            con.execute('UPDATE account_mfa SET last_step=? WHERE user_id=?', (step, uid))
            return True
        if not pending and code:
            canonical = code.replace('-', '').replace(' ', '').lower()
            return con.execute('UPDATE mfa_recovery SET used_at=? WHERE user_id=? AND code_hash=? AND used_at IS NULL',
                               (now, uid, digest(canonical))).rowcount == 1
        return False

    def check(self, uid, code):
        if not self.enabled(uid):
            return
        with self.store.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            valid = self.factor(con, uid, code)
        if not valid:
            raise HTTPException(401, '双重验证码无效或已使用；请等待下一组验证码，或使用未用过的恢复码')

    def recovery(self, con, uid):
        codes = [secrets.token_hex(10) for _ in range(10)]
        con.execute('DELETE FROM mfa_recovery WHERE user_id=?', (uid,))
        con.executemany('INSERT INTO mfa_recovery VALUES (?,?,NULL)', [(uid, digest(c)) for c in codes])
        return ['-'.join(c[i:i+5] for i in range(0,20,5)) for c in codes]

    def enable(self, uid, token, code):
        with self.store.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            row = con.execute('SELECT * FROM account_mfa WHERE user_id=?', (uid,)).fetchone()
            if not row or row['enabled'] or row['session_hash'] != digest(token) or row['expires'] < time.time():
                raise HTTPException(409, '绑定已过期或状态改变，请重新开始')
            if not self.factor(con, uid, code, pending=True):
                raise HTTPException(401, '认证器验证码不正确')
            con.execute('UPDATE account_mfa SET enabled=1,session_hash=NULL,expires=NULL WHERE user_id=?', (uid,))
            codes = self.recovery(con, uid)
            self.revoke(con, uid)
            self.audit(con, uid, 'mfa_enabled')
        return codes

    def manage(self, uid, password, code, *, disable=False):
        version = self.password(uid, password)['password_hash']
        with self.store.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            row = con.execute('SELECT password_hash FROM users WHERE id=? AND disabled=0', (uid,)).fetchone()
            if not row or row['password_hash'] != version or not self.enabled(uid):
                raise HTTPException(409, '账号状态已改变，请重新验证')
            if not self.factor(con, uid, code):
                raise HTTPException(401, '双重验证码无效或已使用')
            if disable:
                con.execute('DELETE FROM account_mfa WHERE user_id=?', (uid,))
                con.execute('DELETE FROM mfa_recovery WHERE user_id=?', (uid,))
                codes = []
            else:
                codes = self.recovery(con, uid)
            self.revoke(con, uid)
            self.audit(con, uid, 'mfa_disabled' if disable else 'mfa_recovery_rotated')
        return codes

    @staticmethod
    def audit(con, uid, action):
        con.execute('INSERT INTO admin_audit(actor,action,target,timestamp) VALUES (?,?,?,?)', (uid, action, uid, time.time()))

    @staticmethod
    def revoke(con, uid):
        con.execute('DELETE FROM sessions WHERE user_id=?', (uid,))
        con.execute('DELETE FROM login_challenges WHERE user_id=?', (uid,))
        con.execute('UPDATE api_tokens SET revoked=1 WHERE user_id=?', (uid,))

    def challenge(self, row, remember, primary_method='pwd'):
        token = secrets.token_urlsafe(32)
        with self.store.connect() as con:
            con.execute('DELETE FROM login_challenges WHERE expires<?', (time.time(),))
            con.execute('INSERT INTO login_challenges VALUES (?,?,?,?,?,0,?)',
                        (digest(token), row['id'], row['password_hash'], int(remember), time.time()+300, primary_method))
        return {'mfa_required': True, 'challenge': token, 'expires_in': 300}

    def complete(self, challenge, code):
        with self.store.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            row = con.execute('SELECT c.*,u.password_hash,u.disabled FROM login_challenges c JOIN users u ON u.id=c.user_id WHERE c.token_hash=?', (digest(challenge),)).fetchone()
            valid = bool(row and row['expires'] > time.time() and row['attempts'] < 5 and not row['disabled'] and row['password_version'] == row['password_hash'])
            if valid:
                con.execute('UPDATE login_challenges SET attempts=attempts+1 WHERE token_hash=?', (digest(challenge),))
                valid = self.factor(con, row['user_id'], code)
                if valid:
                    con.execute('DELETE FROM login_challenges WHERE token_hash=?', (digest(challenge),))
        if not valid:
            raise HTTPException(401, '登录验证无效、过期或验证码已使用，请重试')
        return self.auth.new_session(row['user_id'], bool(row['remember']), assurance=row['primary_method']+'+otp',
                                     expected_password_hash=row['password_version'])
