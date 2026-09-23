"""One server-side provider adapter; secrets never appear in returned settings."""
import base64
import ctypes
import os
import threading

import httpx
from pydantic import Field, SecretStr

from . import core
from .schema import Contract


class ProviderSettings(Contract):
    enabled: bool
    model: str = Field(default='deepseek-flash', pattern=r'^[a-zA-Z0-9_.:-]{1,80}$')
    api_key: SecretStr | None = None
    clear_key: bool = False


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
        return {'provider': 'DeepSeek', 'model': settings['model'], 'enabled': settings['enabled'],
                'key_configured': bool(settings.get('sealed_key') or os.environ.get('DEEPSEEK_API_KEY')),
                'endpoint': self.endpoint, 'key_storage': 'Windows DPAPI' if os.name == 'nt' else 'environment',
                'data_scope': '发送提问、项目摘要与工具结果；不自动发送原始文件。'}

    def save(self, body):
        with self.lock:
            config = self.settings()
            if body.clear_key:
                config.pop('sealed_key', None)
            elif body.api_key and body.api_key.get_secret_value():
                value = body.api_key.get_secret_value().strip()
                if not 10 <= len(value) <= 500 or any(c.isspace() for c in value):
                    raise core.ValidationError('密钥格式无效')
                config['sealed_key'] = protect(value)
            config.update(enabled=body.enabled, model=body.model)
            core.write_json(self.path, config)
        return self.public()

    def complete(self, messages, tools, *, transport=None):
        settings = self.settings()
        if not settings['enabled']:
            raise core.ValidationError('AI Provider 尚未启用，请在开发者设置中配置')
        key = protect(settings['sealed_key'], True) if settings.get('sealed_key') else os.environ.get('DEEPSEEK_API_KEY')
        if not key:
            raise core.ValidationError('尚未配置 API Key')
        try:
            with httpx.Client(timeout=60, follow_redirects=False, transport=transport, trust_env=False) as client:
                payload = {'model': settings['model'], 'messages': messages, 'max_tokens': 1400,
                           'thinking': {'type': 'disabled'}, 'tools': tools, 'tool_choice': 'auto'}
                with client.stream('POST', self.endpoint, headers={'Authorization': 'Bearer ' + key}, json=payload) as response:
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
