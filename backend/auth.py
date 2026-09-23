"""Local accounts, hashed sessions and project ownership. No default credentials."""
import hashlib
import hmac
import secrets
import sqlite3
import time
import uuid

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, SecretStr


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)
    username: str = Field(pattern=r"^[A-Za-z0-9_\-]{3,32}$")
    password: SecretStr = Field(min_length=10, max_length=128)


class Registration(Credentials):
    display_name: str = Field(min_length=1, max_length=40)


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
                con.execute("INSERT INTO users VALUES (?,?,?,?,?)", (uid, body.username.lower(), name, salt, hashed))
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
        if row is None or not hmac.compare_digest(row["password_hash"], candidate):
            raise HTTPException(401, "用户名或密码不正确")
        return self.new_session(row["id"])

    def new_session(self, uid):
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with self.store.connect() as con:
            con.execute("DELETE FROM sessions WHERE expires < ?", (time.time(),))
            con.execute("INSERT INTO sessions VALUES (?,?,?,?)", (digest(token), uid, csrf, time.time() + self.ttl))
        return token, self.session(token)

    def session(self, token):
        if not token or len(token) > 256:
            return None
        with self.store.connect() as con:
            row = con.execute("SELECT u.id,u.username,u.display_name,s.csrf FROM sessions s JOIN users u ON u.id=s.user_id WHERE token_hash=? AND expires>?", (digest(token), time.time())).fetchone()
        return dict(row) if row else None

    def logout(self, token):
        with self.store.connect() as con:
            con.execute("DELETE FROM sessions WHERE token_hash=?", (digest(token),))

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
