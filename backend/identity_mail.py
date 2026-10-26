"""Verified email binding and one-use recovery, with an encrypted durable outbox."""
import json
import secrets
import smtplib
import ssl
import threading
import time
import uuid
from email.message import EmailMessage

from email_validator import EmailNotValidError, validate_email
from fastapi import HTTPException

from .auth import digest, password_hash, validate_password
from .identity_security import seal, unseal


def email_address(value):
    try:
        return validate_email(value, check_deliverability=False).normalized.lower()
    except EmailNotValidError:
        raise HTTPException(422, '请填写有效的邮箱地址') from None


class AccountMail:
    def __init__(self, identity, operations):
        self.identity, self.store, self.operations = identity, identity.store, operations
        self.stop = threading.Event()
        self.worker = None
        with self.store.connect() as con:
            con.executescript('''
                CREATE TABLE IF NOT EXISTS account_emails (
                    user_id TEXT PRIMARY KEY, address TEXT NOT NULL, verified INTEGER NOT NULL DEFAULT 0);
                CREATE UNIQUE INDEX IF NOT EXISTS verified_account_email ON account_emails(address) WHERE verified=1;
                CREATE TABLE IF NOT EXISTS email_tokens (
                    token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL, purpose TEXT NOT NULL,
                    address TEXT NOT NULL, password_version TEXT NOT NULL, expires REAL NOT NULL, used_at REAL);
                CREATE TABLE IF NOT EXISTS identity_outbox (
                    id TEXT PRIMARY KEY, payload TEXT NOT NULL, state TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0, retry_at REAL NOT NULL, error TEXT);
                UPDATE identity_outbox SET state='queued' WHERE state='sending';
            ''')

    def status(self, uid):
        with self.store.connect() as con:
            row = con.execute('SELECT address,verified FROM account_emails WHERE user_id=?', (uid,)).fetchone()
        return {'address': row['address'] if row else None, 'verified': bool(row and row['verified']),
                'delivery_configured': self.identity.config.read()[0].smtp_enabled}

    def queue(self, con, to, subject, text):
        payload = seal(json.dumps({'to': to, 'subject': subject, 'text': text}, ensure_ascii=False))
        con.execute("INSERT INTO identity_outbox VALUES (?,?, 'queued',0,?,NULL)",
                    ('mail_'+uuid.uuid4().hex, payload, time.time()))

    def issue(self, con, uid, purpose, address, password_version, public_url):
        token = secrets.token_urlsafe(32)
        con.execute('UPDATE email_tokens SET used_at=? WHERE user_id=? AND purpose=? AND used_at IS NULL', (time.time(), uid, purpose))
        con.execute('INSERT INTO email_tokens VALUES (?,?,?,?,?,?,NULL)',
                    (digest(token), uid, purpose, address, password_version, time.time()+1800))
        route = 'verify-email' if purpose == 'verify' else 'reset-password'
        link = public_url+'/#'+route+'/'+token
        subject = '稀土智暖：验证恢复邮箱' if purpose == 'verify' else '稀土智暖：重置登录密码'
        text = ('你正在绑定账号恢复邮箱。' if purpose == 'verify' else '你请求了重置账号登录密码。')
        self.queue(con, address, subject, text+'\n请在30分钟内打开以下链接；链接只能使用一次。\n'+link+'\n如非本人操作，请忽略此邮件。')

    def bind(self, uid, password, factor_code, address):
        config, _ = self.identity.config.read()
        if not config.smtp_enabled:
            raise HTTPException(503, '工作区尚未配置邮件服务，不能验证恢复邮箱')
        row = self.identity.mfa.password(uid, password)
        self.identity.mfa.check(uid, factor_code)
        address = email_address(address)
        with self.store.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            current = con.execute('SELECT password_hash FROM users WHERE id=? AND disabled=0', (uid,)).fetchone()
            if not current or current['password_hash'] != row['password_hash']:
                raise HTTPException(409, '账号状态已改变，请重新验证')
            self.issue(con, uid, 'verify', address, row['password_hash'], config.public_url)
            self.identity.mfa.audit(con, uid, 'recovery_email_requested')
        return {'message': '验证邮件已进入发送队列，请在邮箱中确认；原恢复邮箱在确认前仍有效'}

    def verify(self, token):
        with self.store.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            row = con.execute('SELECT t.*,u.password_hash,u.disabled FROM email_tokens t JOIN users u ON u.id=t.user_id WHERE token_hash=? AND purpose=\'verify\'', (digest(token),)).fetchone()
            if not self.valid(row):
                raise HTTPException(400, '验证链接无效、过期或已使用')
            occupied = con.execute('SELECT user_id FROM account_emails WHERE address=? AND verified=1 AND user_id<>?', (row['address'], row['user_id'])).fetchone()
            if occupied:
                raise HTTPException(409, '此邮箱无法绑定，请联系管理员')
            old = con.execute('SELECT address FROM account_emails WHERE user_id=? AND verified=1', (row['user_id'],)).fetchone()
            con.execute('INSERT INTO account_emails VALUES (?,?,1) ON CONFLICT(user_id) DO UPDATE SET address=excluded.address,verified=1', (row['user_id'], row['address']))
            con.execute('UPDATE email_tokens SET used_at=? WHERE user_id=? AND used_at IS NULL', (time.time(), row['user_id']))
            if old and old['address'] != row['address']:
                self.queue(con, old['address'], '稀土智暖：恢复邮箱已变更', '你的账号恢复邮箱已完成变更。如非本人操作，请立即联系工作区管理员。')
            self.identity.mfa.audit(con, row['user_id'], 'recovery_email_verified')
        return {'message': '恢复邮箱已验证，可返回登录或账号设置'}

    @staticmethod
    def valid(row):
        return bool(row and not row['disabled'] and row['used_at'] is None and row['expires'] > time.time()
                    and row['password_version'] == row['password_hash'])

    def request_reset(self, address):
        config, _ = self.identity.config.read()
        if not config.smtp_enabled:
            raise HTTPException(503, '工作区尚未配置邮件找回，请联系管理员')
        address = email_address(address)
        with self.store.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            row = con.execute('SELECT u.* FROM account_emails e JOIN users u ON u.id=e.user_id WHERE e.address=? AND e.verified=1 AND u.disabled=0', (address,)).fetchone()
            if row:
                recent = con.execute("SELECT 1 FROM email_tokens WHERE user_id=? AND purpose='reset' AND expires>?", (row['id'], time.time()+1740)).fetchone()
                if not recent:
                    self.issue(con, row['id'], 'reset', address, row['password_hash'], config.public_url)
        return {'message': '如该邮箱已绑定可用账号，你将收到重置邮件。请稍后查看收件箱及垃圾邮件'}

    def reset(self, token, new_password, factor_code):
        with self.store.connect() as con:
            row = con.execute("SELECT t.*,u.password_hash,u.salt,u.username,u.disabled FROM email_tokens t JOIN users u ON u.id=t.user_id WHERE token_hash=? AND purpose='reset'", (digest(token),)).fetchone()
        if not self.valid(row):
            raise HTTPException(400, '重置链接无效、过期或已使用')
        validate_password(new_password, row['username'])
        if password_hash(new_password, row['salt']) == row['password_hash']:
            raise HTTPException(422, '新密码须与当前密码不同')
        salt = secrets.token_hex(16)
        hashed = password_hash(new_password, salt)
        with self.store.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            current = con.execute('SELECT t.*,u.password_hash,u.disabled FROM email_tokens t JOIN users u ON u.id=t.user_id WHERE token_hash=?', (digest(token),)).fetchone()
            email = con.execute('SELECT 1 FROM account_emails WHERE user_id=? AND address=? AND verified=1', (row['user_id'], row['address'])).fetchone()
            if not self.valid(current) or not email:
                raise HTTPException(400, '重置链接无效、过期或已使用')
            if self.identity.mfa.enabled(row['user_id']) and not self.identity.mfa.factor(con, row['user_id'], factor_code):
                raise HTTPException(401, '账号已启用双重验证，请提供有效认证器验证码或恢复码')
            con.execute('UPDATE users SET salt=?,password_hash=? WHERE id=?', (salt, hashed, row['user_id']))
            con.execute('UPDATE email_tokens SET used_at=? WHERE user_id=? AND used_at IS NULL', (time.time(), row['user_id']))
            self.identity.mfa.revoke(con, row['user_id'])
            self.identity.mfa.audit(con, row['user_id'], 'password_reset_by_verified_email')
            self.queue(con, row['address'], '稀土智暖：密码已重置', '你的账号密码已重置，旧登录会话与项目令牌均已撤销。如非本人操作，请立即联系管理员。')
        return {'message': '密码已重置，请使用新密码重新登录。双重验证设置保持不变'}

    def deliver_pending(self):
        if not self.operations.enter():
            return False
        try:
            config, _ = self.identity.config.read()
            if not config.smtp_enabled:
                return False
            with self.store.connect() as con:
                con.execute('BEGIN IMMEDIATE')
                row = con.execute("SELECT * FROM identity_outbox WHERE state='queued' AND retry_at<=? ORDER BY retry_at LIMIT 1", (time.time(),)).fetchone()
                if not row:
                    return False
                con.execute("UPDATE identity_outbox SET state='sending',attempts=attempts+1 WHERE id=?", (row['id'],))
            try:
                data = json.loads(unseal(row['payload']))
                message = EmailMessage()
                message['From'], message['To'], message['Subject'] = config.smtp_from, data['to'], data['subject']
                message['Message-ID'] = '<'+row['id']+'@vra-trust.local>'
                message.set_content(data['text'])
                context = ssl.create_default_context()
                client = smtplib.SMTP_SSL(config.smtp_host, config.smtp_port, timeout=5, context=context) if config.smtp_tls == 'tls' else smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=5)
                with client as smtp:
                    smtp.ehlo()
                    if config.smtp_tls == 'starttls':
                        smtp.starttls(context=context)
                        smtp.ehlo()
                    if config.smtp_username:
                        smtp.login(config.smtp_username, self.identity.config.secret('smtp_password'))
                    smtp.send_message(message)
                state, error = 'sent', None
            except Exception as exc:
                state = 'failed' if row['attempts'] >= 4 else 'queued'
                error = type(exc).__name__  # No email addresses, reset links or SMTP credentials in diagnostics.
            with self.store.connect() as con:
                con.execute('UPDATE identity_outbox SET state=?,error=?,retry_at=? WHERE id=?',
                            (state, error, time.time()+min(300, 5*2**row['attempts']), row['id']))
            return True
        finally:
            self.operations.leave()

    def start(self):
        def work():
            while not self.stop.wait(1):
                try:
                    self.deliver_pending()
                except Exception:
                    continue
        self.worker = threading.Thread(target=work, name='identity-mail', daemon=True)
        self.worker.start()

    def close(self):
        self.stop.set()
        if self.worker:
            self.worker.join(timeout=7)
