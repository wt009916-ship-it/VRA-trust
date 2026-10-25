"""Local accounts, hashed sessions and project ownership. No default credentials."""
import hashlib
import hmac
import os
import re
import secrets
import sqlite3
import time
import uuid

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, SecretStr


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    username: str = Field(pattern=r"^[A-Za-z0-9_\-]{3,32}$")
    password: SecretStr = Field(min_length=1, max_length=128)


class Registration(Credentials):
    password: SecretStr = Field(min_length=12, max_length=128)
    display_name: str = Field(min_length=1, max_length=40)
    invitation: SecretStr | None = Field(default=None, max_length=200)


class PasswordChange(BaseModel):
    model_config = ConfigDict(extra='forbid')
    current_password: SecretStr = Field(min_length=1, max_length=128)
    new_password: SecretStr = Field(min_length=12, max_length=128)


def validate_password(password):
    if len(password) < 12 or not re.search(r'[A-Za-z]', password) or password.isalnum() or len(set(password)) < 5:
        raise HTTPException(422, '密码至少 12 位，包含字母和符号，不能为重复字符')


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(password, salt):
    # OWASP scrypt minimum: N=2^17, r=8, p=1 (128 MiB).
    return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=131072,
                          r=8, p=1, maxmem=256 * 1024 * 1024).hex()


class Auth:
    cookie = "vra_session"
    ttl = 12 * 3600

    def __init__(self, store):
        self.store = store
        with store.connect() as con:
            con.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL,
                    display_name TEXT NOT NULL, salt TEXT NOT NULL, password_hash TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL,
                    csrf TEXT NOT NULL, expires REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS project_owners (
                    project_id TEXT PRIMARY KEY, user_id TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS auth_attempts (bucket TEXT NOT NULL, timestamp REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS auth_attempt_bucket ON auth_attempts(bucket,timestamp);
            """)
            columns = {r[1] for r in con.execute('PRAGMA table_info(users)')}
            if 'disabled' not in columns:
                con.execute('ALTER TABLE users ADD COLUMN disabled INTEGER NOT NULL DEFAULT 0')
            con.executescript('''
                CREATE TABLE IF NOT EXISTS invitations (
                    id TEXT PRIMARY KEY, token_hash TEXT UNIQUE NOT NULL, label TEXT NOT NULL,
                    expires REAL NOT NULL, used_by TEXT, revoked INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS admin_audit (
                    id INTEGER PRIMARY KEY, actor TEXT NOT NULL, action TEXT NOT NULL,
                    target TEXT NOT NULL, timestamp REAL NOT NULL);
                PRAGMA user_version=2;
            ''')

    def registration_mode(self):
        return 'open' if os.environ.get('VRA_REGISTRATION_MODE') == 'open' else 'invitation'

    def setup_required(self):
        with self.store.connect() as con:
            return con.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0

    def throttle(self, username, address):
        now = time.time()
        with self.store.connect() as con:
            con.execute("BEGIN IMMEDIATE")
            con.execute("DELETE FROM auth_attempts WHERE timestamp < ?", (now - 900,))
            buckets = [("user:" + username.lower(), 8), ("ip:" + address, 40)]
            for bucket, maximum in buckets:
                if con.execute("SELECT COUNT(*) FROM auth_attempts WHERE bucket=?", (bucket,)).fetchone()[0] >= maximum:
                    raise HTTPException(429, "尝试次数过多，请 15 分钟后再试")
            con.executemany("INSERT INTO auth_attempts VALUES (?,?)", [(b, now) for b, _ in buckets])

    def register(self, body):
        password = body.password.get_secret_value()
        if not re.search(r'[A-Za-z]', body.username):
            raise HTTPException(422, '用户名必须包含字母，不能使用纯数字')
        validate_password(password)
        salt = secrets.token_hex(16)
        hashed = password_hash(body.password.get_secret_value(), salt)
        uid = "user_" + uuid.uuid4().hex
        name = body.display_name.strip()
        if not name:
            raise HTTPException(422, "显示名称不能为空")
        try:
            with self.store.connect() as con:
                con.execute("BEGIN IMMEDIATE")
                first = con.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
                if not first and self.registration_mode() != 'open':
                    invite = digest(body.invitation.get_secret_value()) if body.invitation else ''
                    changed = con.execute('UPDATE invitations SET used_by=? WHERE token_hash=? AND used_by IS NULL AND revoked=0 AND expires>?', (uid, invite, time.time()))
                    if changed.rowcount != 1:
                        raise HTTPException(403, '需要管理员提供的有效邀请码；邀请码只能使用一次')
                con.execute("INSERT INTO users (id,username,display_name,salt,password_hash) VALUES (?,?,?,?,?)", (uid, body.username.lower(), name, salt, hashed))
                con.execute('INSERT INTO admin_audit(actor,action,target,timestamp) VALUES (?,?,?,?)', (uid, 'account_registered', uid, time.time()))
                if first:
                    # One atomic migration; never expose legacy projects to subsequent registrations.
                    con.execute("INSERT OR IGNORE INTO project_owners SELECT DISTINCT id,? FROM records WHERE kind='project'", (uid,))
        except sqlite3.IntegrityError:
            raise HTTPException(409, "这个用户名已被使用") from None
        return self.new_session(uid)

    def login(self, body):
        with self.store.connect() as con:
            row = con.execute("SELECT * FROM users WHERE username=?", (body.username.lower(),)).fetchone()
        salt = row["salt"] if row else "00" * 16
        candidate = password_hash(body.password.get_secret_value(), salt)
        if row is None or not hmac.compare_digest(row["password_hash"], candidate) or row['disabled']:
            raise HTTPException(401, "用户名或密码不正确")
        return self.new_session(row["id"])

    def new_session(self, uid):
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with self.store.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            if not con.execute('SELECT 1 FROM users WHERE id=? AND disabled=0', (uid,)).fetchone():
                raise HTTPException(401, '账号不可用，请联系管理员')
            con.execute("DELETE FROM sessions WHERE expires < ?", (time.time(),))
            con.execute("INSERT INTO sessions VALUES (?,?,?,?)", (digest(token), uid, csrf, time.time() + self.ttl))
        user = self.session(token)
        if not user:
            raise HTTPException(401, '会话已失效，请重新登录')
        return token, user

    def session(self, token):
        if not token or len(token) > 256:
            return None
        with self.store.connect() as con:
            row = con.execute("SELECT u.id,u.username,u.display_name,s.csrf FROM sessions s JOIN users u ON u.id=s.user_id WHERE token_hash=? AND expires>? AND u.disabled=0", (digest(token), time.time())).fetchone()
        return {**dict(row), 'is_admin': self.is_admin(row['id'])} if row else None

    def is_admin(self, user_id):
        with self.store.connect() as con:
            first = con.execute('SELECT id FROM users ORDER BY rowid LIMIT 1').fetchone()
        return bool(first and first[0] == user_id)

    def logout(self, token):
        with self.store.connect() as con:
            con.execute("DELETE FROM sessions WHERE token_hash=?", (digest(token),))

    def change_password(self, uid, body):
        password = body.new_password.get_secret_value()
        validate_password(password)
        with self.store.connect() as con:
            row = con.execute('SELECT * FROM users WHERE id=? AND disabled=0', (uid,)).fetchone()
        if not row or not hmac.compare_digest(row['password_hash'], password_hash(body.current_password.get_secret_value(), row['salt'])):
            raise HTTPException(401, '当前密码不正确')
        salt = secrets.token_hex(16)
        hashed = password_hash(password, salt)
        with self.store.connect() as con:
            changed = con.execute('UPDATE users SET salt=?,password_hash=? WHERE id=? AND password_hash=? AND disabled=0', (salt, hashed, uid, row['password_hash']))
            if changed.rowcount != 1:
                raise HTTPException(409, '账号状态已变化，请重新登录')
            con.execute('DELETE FROM sessions WHERE user_id=?', (uid,))
            con.execute('UPDATE api_tokens SET revoked=1 WHERE user_id=?', (uid,))
            con.execute('INSERT INTO admin_audit(actor,action,target,timestamp) VALUES (?,?,?,?)', (uid, 'password_changed', uid, time.time()))
        return self.new_session(uid)

    def own(self, project_id, user_id):
        with self.store.connect() as con:
            con.execute("INSERT INTO project_owners VALUES (?,?)", (project_id, user_id))

    def allows(self, project_id, user_id):
        with self.store.connect() as con:
            return con.execute("SELECT 1 FROM project_owners WHERE project_id=? AND user_id=?", (project_id, user_id)).fetchone() is not None

    def require_project(self, project_id, user_id):
        if not self.allows(project_id, user_id):
            raise HTTPException(404, "项目不存在或无访问权限")

    def require_run(self, run_id, user_id):
        try:
            self.require_project(self.store.job(run_id)["project_id"], user_id)
        except (KeyError, ValueError):
            raise HTTPException(404, "运行不存在或无访问权限") from None
