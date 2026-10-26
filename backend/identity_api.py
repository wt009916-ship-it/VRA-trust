"""Account-owned MFA/recovery/SSO routes and administrator connection settings."""
import logging
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import Field, SecretStr
from .auth import PasswordConfirm, digest
from .identity_mail import AccountMail, email_address
from .identity_security import IdentityConfig, MFA
from .identity_sso import SSO
from .schema import Contract

class FactorCode(Contract):
    code: SecretStr = Field(min_length=1, max_length=40)

class MFAComplete(FactorCode):
    challenge: SecretStr = Field(min_length=32, max_length=256)

class FactorManage(PasswordConfirm):
    pass

class EmailBinding(PasswordConfirm):
    address: str = Field(min_length=3, max_length=254)

class EmailRequest(Contract):
    address: str = Field(min_length=3, max_length=254)

class EmailToken(Contract):
    token: SecretStr = Field(min_length=32, max_length=256)

class EmailReset(EmailToken):
    new_password: SecretStr = Field(min_length=15, max_length=128)
    factor_code: SecretStr | None = Field(default=None, max_length=40)

class Unlink(PasswordConfirm):
    issuer: str = Field(max_length=2048)

class RedactIdentityQuery(logging.Filter):

    def filter(self, record):
        if isinstance(record.args, tuple) and len(record.args) >= 3 and str(record.args[2]).startswith('/api/auth/sso/callback'):
            args = list(record.args)
            args[2] = '/api/auth/sso/callback'
            record.args = tuple(args)
        return True

class Identity:

    def __init__(self, auth, operations):
        self.auth, self.store = (auth, auth.store)
        self.config = IdentityConfig(self.store)
        self.mfa = MFA(auth)
        self.mail = AccountMail(self, operations)
        self.sso = SSO(self)
        auth.identity = self

    def login(self, body):
        row = self.auth.verify_credentials(body)
        if self.mfa.enabled(row['id']):
            return self.mfa.challenge(row, body.remember_device)
        return self.auth.new_session(row['id'], body.remember_device, expected_password_hash=row['password_hash'])

    def confirm(self, request, body):
        user = request.state.user
        self.auth.throttle('identity:' + user['username'], request.client.host if request.client else 'unknown')
        self.mfa.password(user['id'], body.current_password.get_secret_value())
        self.mfa.check(user['id'], body.factor_code.get_secret_value() if body.factor_code else None)
        return user

def register_identity(app, auth, session_response):
    identity = app.state.identity
    pending_cookie = 'vra_mfa_pending'
    secure = __import__('os').environ.get('VRA_COOKIE_SECURE', 'false').lower() == 'true'
    logger = logging.getLogger('uvicorn.access')
    if not any((isinstance(f, RedactIdentityQuery) for f in logger.filters)):
        logger.addFilter(RedactIdentityQuery())

    def factor(body):
        return body.factor_code.get_secret_value() if body.factor_code else None

    def fresh(request, *, otp=True):
        user = request.state.user
        assurance = user.get('assurance', 'pwd') if otp and identity.mfa.enabled(user['id']) else 'pwd'
        return session_response(auth.new_session(user['id'], user['remember_device'], assurance=assurance), request.cookies.get(auth.cookie))

    @app.get('/api/auth/security')
    def status(request: Request):
        uid = request.state.user['id']
        return {'mfa': identity.mfa.status(uid), 'email': identity.mail.status(uid), 'sso': identity.sso.status(uid)}

    @app.post('/api/auth/mfa/enroll')
    def enroll(body: PasswordConfirm, request: Request):
        user = identity.confirm(request, body)
        return identity.mfa.enroll(user['id'], request.cookies[auth.cookie], body.current_password.get_secret_value())

    @app.post('/api/auth/mfa/enable')
    def enable(body: FactorCode, request: Request):
        user = request.state.user
        auth.throttle('mfa-enroll:' + user['username'], request.client.host if request.client else 'unknown')
        codes = identity.mfa.enable(user['id'], request.cookies[auth.cookie], body.code.get_secret_value())
        response = session_response(auth.new_session(user['id'], user['remember_device'], assurance='pwd+otp'))
        import json
        data = json.loads(response.body)
        data['recovery_codes'] = codes
        updated = JSONResponse(data)
        updated.headers['set-cookie'] = response.headers['set-cookie']
        return updated

    @app.post('/api/auth/mfa/verify')
    def verify(body: MFAComplete, request: Request):
        auth.throttle('mfa:' + digest(body.challenge.get_secret_value())[:20], request.client.host if request.client else 'unknown')
        response = session_response(identity.mfa.complete(body.challenge.get_secret_value(), body.code.get_secret_value()), request.cookies.get(auth.cookie))
        response.delete_cookie(pending_cookie)
        return response

    @app.get('/api/auth/mfa/pending')
    def pending(request: Request):
        token = request.cookies.get(pending_cookie)
        if not token:
            raise HTTPException(400, '没有待验证的企业登录')
        return {'mfa_required': True, 'challenge': token}

    @app.post('/api/auth/mfa/disable')
    def disable(body: FactorManage, request: Request):
        user = request.state.user
        auth.throttle('identity:' + user['username'], request.client.host if request.client else 'unknown')
        identity.mfa.manage(user['id'], body.current_password.get_secret_value(), factor(body), disable=True)
        return fresh(request, otp=False)

    @app.post('/api/auth/mfa/recovery-codes')
    def regenerate(body: FactorManage, request: Request):
        user = request.state.user
        auth.throttle('identity:' + user['username'], request.client.host if request.client else 'unknown')
        codes = identity.mfa.manage(user['id'], body.current_password.get_secret_value(), factor(body))
        response = fresh(request)
        import json
        data = json.loads(response.body)
        data['recovery_codes'] = codes
        updated = JSONResponse(data)
        updated.headers['set-cookie'] = response.headers['set-cookie']
        return updated

    @app.post('/api/auth/email/bind')
    def bind_email(body: EmailBinding, request: Request):
        user = request.state.user
        auth.throttle('email-bind:' + user['username'], request.client.host if request.client else 'unknown')
        return identity.mail.bind(user['id'], body.current_password.get_secret_value(), factor(body), body.address)

    @app.post('/api/auth/email/verify')
    def verify_email(body: EmailToken, request: Request):
        auth.throttle('email-token:' + digest(body.token.get_secret_value())[:20], request.client.host if request.client else 'unknown')
        return identity.mail.verify(body.token.get_secret_value())

    @app.post('/api/auth/recovery/request')
    def request_reset(body: EmailRequest, request: Request):
        address = email_address(body.address)
        auth.throttle('recover:' + digest(address), request.client.host if request.client else 'unknown')
        return identity.mail.request_reset(address)

    @app.post('/api/auth/recovery/inspect')
    def inspect_reset(body: EmailToken, request: Request):
        import time
        auth.throttle('inspect:' + digest(body.token.get_secret_value())[:20], request.client.host if request.client else 'unknown')
        with identity.store.connect() as con:
            row = con.execute("SELECT t.*,u.username,u.password_hash,u.disabled FROM email_tokens t JOIN users u ON u.id=t.user_id WHERE token_hash=? AND purpose='reset'", (digest(body.token.get_secret_value()),)).fetchone()
        if not identity.mail.valid(row) or row['expires'] < time.time():
            raise HTTPException(400, '重置链接无效、过期或已使用')
        return {'username': row['username'], 'mfa_required': identity.mfa.enabled(row['user_id'])}

    @app.post('/api/auth/recovery/complete')
    def reset(body: EmailReset, request: Request):
        auth.throttle('recover-token:' + digest(body.token.get_secret_value())[:20], request.client.host if request.client else 'unknown')
        return identity.mail.reset(body.token.get_secret_value(), body.new_password.get_secret_value(), factor(body))

    def browser_cookie(response, value):
        response.set_cookie(identity.sso.cookie, value, max_age=300, httponly=True, secure=secure, samesite='lax', path='/api/auth/sso')
        return response

    @app.get('/api/auth/sso/start')
    async def sso_start(request: Request):
        address = request.client.host if request.client else 'unknown'
        auth.throttle('sso-start:' + address, address, user_limit=40)
        url, browser = await identity.sso.start()
        return browser_cookie(RedirectResponse(url, status_code=303), browser)

    @app.post('/api/auth/sso/link')
    async def sso_link(body: PasswordConfirm, request: Request):
        user = identity.confirm(request, body)
        url, browser = await identity.sso.start(uid=user['id'], session_hash=digest(request.cookies[auth.cookie]), remember=user['remember_device'])
        return browser_cookie(JSONResponse({'authorization_url': url}), browser)

    @app.post('/api/auth/sso/unlink')
    def sso_unlink(body: Unlink, request: Request):
        user = identity.confirm(request, body)
        with identity.store.connect() as con:
            con.execute('DELETE FROM oidc_links WHERE user_id=? AND issuer=?', (user['id'], body.issuer))
            identity.mfa.revoke(con, user['id'])
            identity.mfa.audit(con, user['id'], 'oidc_subject_unlinked')
        assurance = 'pwd+otp' if identity.mfa.enabled(user['id']) else 'pwd'
        return session_response(auth.new_session(user['id'], user['remember_device'], assurance=assurance))

    @app.get('/api/auth/sso/callback')
    async def sso_callback(request: Request, state: str='', code: str='', error: str=''):
        try:
            if error or not state or (not code) or (len(state) > 256) or (len(code) > 4096):
                raise HTTPException(400, '企业登录未完成')
            result = await identity.sso.complete(state, code, request.cookies.get(identity.sso.cookie, ''))
            if isinstance(result, tuple):
                session = session_response(result, request.cookies.get(auth.cookie))
                response = RedirectResponse('/', status_code=303)
                response.headers['set-cookie'] = session.headers['set-cookie']
            elif result.get('mfa_required'):
                response = RedirectResponse('/#sso-mfa', status_code=303)
                response.set_cookie(pending_cookie, result['challenge'], max_age=300, httponly=True, secure=secure, samesite='strict')
            else:
                response = RedirectResponse('/#sso-linked', status_code=303)
        except HTTPException:
            response = RedirectResponse('/#sso-failed', status_code=303)
        response.delete_cookie(identity.sso.cookie, path='/api/auth/sso')
        return response

def factor_value(body):
    return body.factor_code.get_secret_value() if body.factor_code else None
