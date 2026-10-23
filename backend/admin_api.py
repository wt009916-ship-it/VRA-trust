"""Session-only administrator console; no passwords, source data or keys in summaries."""
import secrets
import time

from fastapi import HTTPException, Request
from pydantic import Field

from .auth import digest
from .domain import identifier
from .schema import Contract


class InvitationCreate(Contract):
    label: str = Field(min_length=1, max_length=80)
    days: int = Field(default=7, ge=1, le=30)


class AccountStatus(Contract):
    disabled: bool


def register_admin(app, domain, auth):
    def require(request):
        user = request.state.user
        if user.get('api_project') or not auth.is_admin(user['id']):
            raise HTTPException(403, '此页面仅允许工作区管理员访问')
        return user['id']

    def audit(con, actor, action, target):
        con.execute('INSERT INTO admin_audit(actor,action,target,timestamp) VALUES (?,?,?,?)',
                    (actor, action, target, time.time()))

    @app.get('/api/admin/overview')
    def overview(request: Request):
        require(request)
        with domain.store.connect() as con:
            return {
                'database': {'engine': 'SQLite', 'persistent': True,
                             'journal_mode': con.execute('PRAGMA journal_mode').fetchone()[0],
                             'schema_version': con.execute('PRAGMA user_version').fetchone()[0]},
                'registration_mode': auth.registration_mode(),
                'users': [dict(r) for r in con.execute('SELECT id,username,display_name,disabled FROM users ORDER BY rowid')],
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
