"""One server-side provider adapter; secrets never appear in returned settings."""
import base64
import ctypes
import os
import threading
from urllib.parse import urlsplit

import httpx
from pydantic import Field, SecretStr, model_validator

from . import core
from .schema import Contract


class ProviderSettings(Contract):
    enabled: bool
    model: str = Field(default='deepseek-flash', pattern=r'^[a-zA-Z0-9_./:-]{1,100}$')
    endpoint: str = 'https://api.deepseek.com/chat/completions'
    vision_model: str | None = Field(default=None, pattern=r'^[a-zA-Z0-9_./:-]{1,100}$')
    api_key: SecretStr | None = None
    clear_key: bool = False

    @model_validator(mode='after')
    def endpoint_contract(self):
        url = urlsplit(self.endpoint)
        local = url.hostname in {'localhost', '127.0.0.1', '::1'}
        if (url.scheme != 'https' and not (url.scheme == 'http' and local)) or not url.hostname:
            raise ValueError('外部服务须使用 HTTPS；本机服务允许 HTTP')
        if url.username or url.password or url.query or url.fragment or not url.path.endswith('/chat/completions'):
            raise ValueError('填写不含凭据/查询参数的完整 /chat/completions 地址')
        return self


def protect(value, decrypt=False):
    """Windows CurrentUser DPAPI, UI-forbidden. Linux uses injected environment secrets."""
    if os.name != 'nt':
        raise core.ValidationError('此主机使用环境变量 DEEPSEEK_API_KEY 注入密钥；不保存明文密钥')
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]
    raw = base64.b64decode(value) if decrypt else value.encode()
    buf = ctypes.create_string_buffer(raw)
    source = Blob(len(raw), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    fn = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    fn.restype = wintypes.BOOL
    fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    if not fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise core.ValidationError('操作系统密钥保护失败')
    try:
        result = ctypes.string_at(target.data, target.size)
        return result.decode() if decrypt else base64.b64encode(result).decode()
    finally:
        local_free = ctypes.WinDLL('kernel32').LocalFree
        local_free.argtypes = [ctypes.c_void_p]
        local_free.restype = ctypes.c_void_p
        local_free(target.data)


class Gateway:
    endpoint = 'https://api.deepseek.com/chat/completions'

    def __init__(self, store):
        self.path = store.root / 'private' / 'provider.json'
        self.lock = threading.Lock()

    def settings(self):
        return core.read_json(self.path) if self.path.exists() else {'enabled': False, 'model': 'deepseek-flash'}

    def public(self):
        settings = self.settings()
        endpoint = settings.get('endpoint', self.endpoint)
        return {'provider': 'OpenAI-compatible', 'model': settings['model'], 'enabled': settings['enabled'],
                'vision_model': settings.get('vision_model'),
                'key_configured': bool(settings.get('sealed_key') or self.environment_key(settings)),
                'endpoint': endpoint, 'key_storage': 'Windows DPAPI' if os.name == 'nt' else 'environment',
                'data_scope': '聊天发送提问、项目摘要与工具结果；仅在显式勾选视觉识别时发送选定图页。'}

    def environment_key(self, settings):
        return os.environ.get('VRA_API_KEY') or (os.environ.get('DEEPSEEK_API_KEY')
            if settings.get('endpoint', self.endpoint) == self.endpoint else None)

    def save(self, body):
        with self.lock:
            config = self.settings()
            if body.endpoint != config.get('endpoint', self.endpoint):
                if config.get('sealed_key') and not body.clear_key and not body.api_key:
                    raise core.ValidationError('更换服务地址时须同时提供新 Key 或清除旧 Key，避免把旧凭据发送到新服务')
            if body.clear_key:
                config.pop('sealed_key', None)
            elif body.api_key and body.api_key.get_secret_value():
                value = body.api_key.get_secret_value().strip()
                if not 10 <= len(value) <= 500 or any(c.isspace() for c in value):
                    raise core.ValidationError('密钥格式无效')
                config['sealed_key'] = protect(value)
            config.update(enabled=body.enabled, model=body.model, endpoint=body.endpoint, vision_model=body.vision_model)
            core.write_json(self.path, config)
        return self.public()

    def complete(self, messages, tools, *, transport=None, vision=False):
        settings = self.settings()
        if not settings['enabled']:
            raise core.ValidationError('AI Provider 尚未启用，请在开发者设置中配置')
        if vision and not settings.get('vision_model'):
            raise core.ValidationError('请先在开发者设置中配置支持图片的视觉模型')
        key = protect(settings['sealed_key'], True) if settings.get('sealed_key') else self.environment_key(settings)
        if not key:
            raise core.ValidationError('尚未配置 API Key')
        try:
            with httpx.Client(timeout=60, follow_redirects=False, transport=transport, trust_env=False) as client:
                endpoint = settings.get('endpoint', self.endpoint)
                payload = {'model': settings['vision_model'] if vision else settings['model'],
                           'messages': messages, 'max_tokens': 6000 if vision else 1400}
                if endpoint == self.endpoint:
                    payload['thinking'] = {'type': 'disabled'}
                if tools:
                    payload.update(tools=tools, tool_choice='auto')
                with client.stream('POST', endpoint, headers={'Authorization': 'Bearer ' + key}, json=payload) as response:
                    if response.status_code != 200:
                        raise core.ValidationError('Provider 请求失败，HTTP ' + str(response.status_code) + '；请检查配置、余额和模型权限')
                    raw = bytearray()
                    for chunk in response.iter_bytes():
                        raw.extend(chunk)
                        if len(raw) > 1024 * 1024:
                            raise core.ValidationError('Provider response too large')
                    import json
                    data = json.loads(raw)
            message = data['choices'][0]['message']
            # Never store/display the provider's hidden reasoning_content.
            return {k: message[k] for k in ('role', 'content', 'tool_calls') if k in message}
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            if isinstance(exc, core.ValidationError):
                raise
            raise core.ValidationError('Provider 网络或响应格式错误；未生成工程结果') from None
