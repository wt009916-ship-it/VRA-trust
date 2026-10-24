"""Session-only administrator console; no passwords, source data or keys in summaries."""
import secrets
import time
import hmac
import re
import sqlite3
import uuid

from fastapi import HTTPException, Request
from pydantic import Field, SecretStr

from .auth import digest, password_hash, validate_password
from .domain import identifier
from .schema import Contract


class InvitationCreate(Contract):
    label: str = Field(min_length=1, max_length=80)
    days: int = Field(default=7, ge=1, le=30)


class AccountStatus(Contract):
    disabled: bool


class AdminConfirm(Contract):
    current_password: SecretStr = Field(min_length=10, max_length=128)


class AccountCreate(AdminConfirm):
    username: str = Field(pattern=r'^[A-Za-z0-9_-]{3,32}$')
    display_name: str = Field(min_length=1, max_length=40)
    password: SecretStr = Field(min_length=12, max_length=128)


class AccountEdit(AdminConfirm):
    username: str = Field(pattern=r'^[A-Za-z0-9_-]{3,32}$')
    display_name: str = Field(min_length=1, max_length=40)
    expected_username: str
    expected_display_name: str


class PasswordReset(AdminConfirm):
    new_password: SecretStr = Field(min_length=12, max_length=128)


def register_admin(app, domain, auth):
    def require(request):
        user = request.state.user
        if user.get('api_project') or not auth.is_admin(user['id']):
            raise HTTPException(403, '此页面仅允许工作区管理员访问')
        return user['id']

    def audit(con, actor, action, target):
        con.execute('INSERT INTO admin_audit(actor,action,target,timestamp) VALUES (?,?,?,?)',
                    (actor, action, target, time.time()))

    def confirm(request, body):
        actor = require(request)
        bucket = 'admin-confirm:'+actor
        with domain.store.connect() as con:
            if con.execute('SELECT COUNT(*) FROM auth_attempts WHERE bucket=? AND timestamp>?', (bucket, time.time()-900)).fetchone()[0] >= 8:
                raise HTTPException(429, '管理员密码确认失败过多，请 15 分钟后重试')
            row = con.execute('SELECT salt,password_hash FROM users WHERE id=? AND disabled=0', (actor,)).fetchone()
        if not row or not hmac.compare_digest(row['password_hash'], password_hash(body.current_password.get_secret_value(), row['salt'])):
            with domain.store.connect() as con:
                con.execute('INSERT INTO auth_attempts VALUES (?,?)', (bucket, time.time()))
            raise HTTPException(403, '管理员当前密码不正确')
        with domain.store.connect() as con:
            con.execute('DELETE FROM auth_attempts WHERE bucket=?', (bucket,))
        return actor

    def revoke_access(con, uid):
        con.execute('DELETE FROM sessions WHERE user_id=?', (uid,))
        con.execute('UPDATE api_tokens SET revoked=1 WHERE user_id=?', (uid,))

    @app.post('/api/admin/users', status_code=201)
    def create_account(body: AccountCreate, request: Request):
        actor = confirm(request, body)
        validate_password(body.password.get_secret_value())
        if not re.search(r'[A-Za-z]', body.username):
            raise HTTPException(422, '新用户名必须包含字母')
        uid, salt = 'user_'+uuid.uuid4().hex, secrets.token_hex(16)
        hashed = password_hash(body.password.get_secret_value(), salt)
        try:
            with domain.store.connect() as con:
                con.execute('INSERT INTO users(id,username,display_name,salt,password_hash) VALUES (?,?,?,?,?)',
                            (uid, body.username.lower(), body.display_name, salt, hashed))
                audit(con, actor, 'account_created_by_admin', uid)
        except sqlite3.IntegrityError:
            raise HTTPException(409, '用户名已存在') from None
        return {'id': uid, 'username': body.username.lower(), 'display_name': body.display_name}

    @app.put('/api/admin/users/{user_id}/profile')
    def edit_account(user_id: str, body: AccountEdit, request: Request):
        actor = confirm(request, body)
        if body.username.lower() != body.expected_username and not re.search(r'[A-Za-z]', body.username):
            raise HTTPException(422, '新用户名必须包含字母')
        try:
            with domain.store.connect() as con:
                changed = con.execute('UPDATE users SET username=?,display_name=? WHERE id=? AND username=? AND display_name=?',
                    (body.username.lower(), body.display_name, user_id, body.expected_username, body.expected_display_name))
                if changed.rowcount != 1:
                    raise HTTPException(409, '账号已修改或不存在，请刷新')
                if body.username.lower() != body.expected_username:
                    revoke_access(con, user_id)
                audit(con, actor, 'account_profile_updated', user_id)
        except sqlite3.IntegrityError:
            raise HTTPException(409, '用户名已存在') from None
        return {'updated': True, 'reauthenticate': body.username.lower() != body.expected_username and user_id == actor}

    @app.post('/api/admin/users/{user_id}/password')
    def reset_password(user_id: str, body: PasswordReset, request: Request):
        actor = confirm(request, body)
        if user_id == actor:
            raise HTTPException(409, '请使用页面右上角“修改我的密码”')
        validate_password(body.new_password.get_secret_value())
        salt = secrets.token_hex(16)
        hashed = password_hash(body.new_password.get_secret_value(), salt)
        with domain.store.connect() as con:
            if con.execute('UPDATE users SET salt=?,password_hash=? WHERE id=?', (salt, hashed, user_id)).rowcount != 1:
                raise HTTPException(404, '账号不存在')
            revoke_access(con, user_id)
            audit(con, actor, 'password_reset_by_admin', user_id)
        return {'reset': True, 'access_revoked': True}

    @app.post('/api/admin/users/{user_id}/revoke-access')
    def revoke_user(user_id: str, body: AdminConfirm, request: Request):
        actor = confirm(request, body)
        with domain.store.connect() as con:
            if not con.execute('SELECT 1 FROM users WHERE id=?', (user_id,)).fetchone():
                raise HTTPException(404, '账号不存在')
            revoke_access(con, user_id)
            audit(con, actor, 'account_access_revoked', user_id)
        return {'revoked': True, 'reauthenticate': user_id == actor}

    from .admin_data import register_database
    register_database(app, domain, require, confirm, audit, AdminConfirm)

    @app.get('/api/admin/overview')
    def overview(request: Request):
        require(request)
        from .document_reader import capability
        with domain.store.connect() as con:
            return {
                'document_ocr': capability(),
                'database': {'engine': 'SQLite', 'persistent': True,
                             'journal_mode': con.execute('PRAGMA journal_mode').fetchone()[0],
                             'schema_version': con.execute('PRAGMA user_version').fetchone()[0]},
                'registration_mode': auth.registration_mode(),
                'users': [{**dict(r), 'is_admin': auth.is_admin(r['id']),
                           'sessions': con.execute('SELECT COUNT(*) FROM sessions WHERE user_id=? AND expires>?', (r['id'], time.time())).fetchone()[0],
                           'projects': con.execute('SELECT COUNT(*) FROM project_owners WHERE user_id=?', (r['id'],)).fetchone()[0]}
                          for r in con.execute('SELECT id,username,display_name,disabled FROM users ORDER BY rowid')],
                'invitations': [dict(r) for r in con.execute('SELECT id,label,expires,used_by,revoked FROM invitations ORDER BY rowid DESC LIMIT 100')],
                'audit': [dict(r) for r in con.execute('SELECT * FROM admin_audit ORDER BY id DESC LIMIT 100')],
                'projects': con.execute("SELECT COUNT(DISTINCT id) FROM records WHERE kind='project'").fetchone()[0],
                'jobs': [dict(r) for r in con.execute('SELECT state,COUNT(*) AS count FROM jobs GROUP BY state')],
            }

    @app.post('/api/admin/invitations', status_code=201)
    def invite(body: InvitationCreate, request: Request):
        actor = require(request)
        token, iid = secrets.token_urlsafe(32), identifier('invitation')
        expires = time.time() + body.days * 86400
        with domain.store.connect() as con:
            con.execute('INSERT INTO invitations VALUES (?,?,?,?,NULL,0)', (iid, digest(token), body.label, expires))
            audit(con, actor, 'invitation_created', iid)
        return {'id': iid, 'invitation': token, 'expires': expires}

    @app.delete('/api/admin/invitations/{invitation_id}')
    def revoke(invitation_id: str, request: Request):
        actor = require(request)
        with domain.store.connect() as con:
            if con.execute('UPDATE invitations SET revoked=1 WHERE id=?', (invitation_id,)).rowcount != 1:
                raise HTTPException(404, '邀请码不存在')
            audit(con, actor, 'invitation_revoked', invitation_id)
        return {'revoked': True}

    @app.patch('/api/admin/users/{user_id}')
    def account(user_id: str, body: AccountStatus, request: Request):
        actor = require(request)
        if auth.is_admin(user_id):
            raise HTTPException(409, '不能停用工作区管理员')
        with domain.store.connect() as con:
            if con.execute('UPDATE users SET disabled=? WHERE id=?', (int(body.disabled), user_id)).rowcount != 1:
                raise HTTPException(404, '账号不存在')
            if body.disabled:
                con.execute('DELETE FROM sessions WHERE user_id=?', (user_id,))
                con.execute('UPDATE api_tokens SET revoked=1 WHERE user_id=?', (user_id,))
            audit(con, actor, 'account_disabled' if body.disabled else 'account_enabled', user_id)
        return {'disabled': body.disabled}
