"""One server-side provider adapter; secrets never appear in returned settings."""
import base64
import ctypes
import os
import threading
import json
import time
from urllib.parse import urlsplit

import httpx
from pydantic import Field, SecretStr, StrictInt, model_validator

from . import core
from .schema import Contract


class ProviderSettings(Contract):
    enabled: bool
    model: str = Field(default='deepseek-flash', pattern=r'^[a-zA-Z0-9_./:-]{1,100}$')
    endpoint: str = 'https://api.deepseek.com/chat/completions'
    vision_model: str | None = Field(default=None, pattern=r'^[a-zA-Z0-9_./:-]{1,100}$')
    api_key: SecretStr | None = None
    clear_key: bool = False
    request_timeout_s: StrictInt = Field(default=120, ge=10, le=180)
    max_output_tokens: StrictInt = Field(default=1000, ge=128, le=6000)
    local_qwen_no_thinking: bool = True

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
                'request_timeout_s': settings.get('request_timeout_s', 120),
                'max_output_tokens': settings.get('max_output_tokens', 1000),
                'local_qwen_no_thinking': settings.get('local_qwen_no_thinking', True),
                'key_configured': bool(settings.get('sealed_key') or self.environment_key(settings)),
                'endpoint': endpoint, 'key_storage': 'Windows DPAPI' if os.name == 'nt' else 'environment',
                'data_scope': '聊天发送提问、项目摘要与工具结果；仅在本次任务勾选允许AI读取资料摘录后发送有页码的有限文字；视觉识别另需明确勾选发送选定图页。'}

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
            config.update(enabled=body.enabled, model=body.model, endpoint=body.endpoint, vision_model=body.vision_model,
                          request_timeout_s=body.request_timeout_s, max_output_tokens=body.max_output_tokens,
                          local_qwen_no_thinking=body.local_qwen_no_thinking)
            core.write_json(self.path, config)
        return self.public()

    def complete(self, messages, tools, *, transport=None, vision=False, timeout_s=None):
        settings = self.settings()
        if not settings['enabled']:
            raise core.ValidationError('AI Provider 尚未启用，请在开发者设置中配置')
        if vision and not settings.get('vision_model'):
            raise core.ValidationError('请先在开发者设置中配置支持图片的视觉模型')
        key = protect(settings['sealed_key'], True) if settings.get('sealed_key') else self.environment_key(settings)
        if not key:
            raise core.ValidationError('尚未配置 API Key')
        endpoint = settings.get('endpoint', self.endpoint)
        model = settings['vision_model'] if vision else settings['model']
        payload = {'model': model, 'messages': messages,
                   'max_tokens': 6000 if vision else settings.get('max_output_tokens', 1000)}
        if endpoint == self.endpoint or (urlsplit(endpoint).hostname=='tokenhub.tencentmaas.com' and 'deepseek' in model.lower()):
            payload['thinking'] = {'type': 'disabled'}
        if (not vision and settings.get('local_qwen_no_thinking', True) and 'qwen' in model.lower()
                and urlsplit(endpoint).hostname in {'localhost', '127.0.0.1', '::1'}):
            payload['chat_template_kwargs'] = {'enable_thinking': False}
            payload['temperature'] = 0.
        if tools:
            payload.update(tools=tools, tool_choice='auto')
        budget = min(settings.get('request_timeout_s', 120), timeout_s if timeout_s is not None else 180)
        deadline = time.monotonic()+budget
        attempts = []
        for attempt in range(2):
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                raise ProviderError('TIME_BUDGET', attempts)
            start, received = time.monotonic(), False
            try:
                timeout = httpx.Timeout(remaining, connect=min(10., remaining), write=min(30., remaining), pool=min(10., remaining))
                with httpx.Client(timeout=timeout, follow_redirects=False, transport=transport, trust_env=False) as client:
                    with client.stream('POST', endpoint, headers={'Authorization': 'Bearer '+key}, json=payload) as response:
                        if response.status_code != 200:
                            code = 'HTTP_'+str(response.status_code)
                            attempts.append({'attempt': attempt+1, 'status': 'failed', 'code': code,
                                             'duration_ms': round((time.monotonic()-start)*1000)})
                            if response.status_code in {502, 503, 504} and attempt == 0 and deadline-time.monotonic() > 2:
                                continue
                            raise ProviderError(code, attempts)
                        raw = bytearray()
                        for chunk in response.iter_bytes():
                            received = received or bool(chunk)
                            raw.extend(chunk)
                            if len(raw) > 1024*1024:
                                raise ProviderError('RESPONSE_TOO_LARGE', attempts)
                            if time.monotonic() > deadline:
                                raise ProviderError('TIME_BUDGET', attempts)
                        data = json.loads(raw)
                message = data['choices'][0]['message']
                if not isinstance(message, dict) or message.get('role','assistant')!='assistant':
                    raise ValueError('Message must be an assistant object')
                calls=message.get('tool_calls') or []
                if not isinstance(calls,list) or len(calls)>4:
                    raise ValueError('Tool calls must be a bounded list')
                ids=[]
                for call in calls:
                    if not isinstance(call,dict) or not isinstance(call.get('id'),str) or not 1<=len(call['id'])<=200:
                        raise ValueError('Invalid tool call ID')
                    fn=call.get('function')
                    if not isinstance(fn,dict) or not isinstance(fn.get('name'),str) or not isinstance(fn.get('arguments'),str):
                        raise ValueError('Invalid function call')
                    ids.append(call['id'])
                if len(set(ids))!=len(ids):raise ValueError('Duplicate tool call IDs')
                usage=data.get('usage') if isinstance(data.get('usage'),dict) else {}
                attempts.append({'attempt': attempt+1, 'status': 'succeeded',
                                 'duration_ms': round((time.monotonic()-start)*1000)})
                # Never retain a provider's hidden reasoning_content.
                answer = {k: message[k] for k in ('role', 'content', 'tool_calls') if k in message}
                answer['_request'] = {'attempts': attempts, 'finish_reason': data['choices'][0].get('finish_reason'),
                                      'usage':{k:v for k,v in usage.items() if k in {'prompt_tokens','completion_tokens','total_tokens','prompt_cache_hit_tokens','prompt_cache_miss_tokens'} and isinstance(v,int) and not isinstance(v,bool) and v>=0},
                                      'timeout_s': budget, 'local_no_thinking': 'chat_template_kwargs' in payload}
                return answer
            except ProviderError as exc:
                if not attempts or attempts[-1]['attempt'] != attempt+1:
                    attempts.append({'attempt': attempt+1, 'status': 'failed', 'code': exc.code,
                                     'duration_ms': round((time.monotonic()-start)*1000)})
                raise
            except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
                code = ('READ_TIMEOUT' if isinstance(exc, httpx.ReadTimeout) else
                        'CONNECT_TIMEOUT' if isinstance(exc, httpx.ConnectTimeout) else
                        'NETWORK_ERROR' if isinstance(exc, httpx.HTTPError) else 'INVALID_RESPONSE')
                attempts.append({'attempt': attempt+1, 'status': 'failed', 'code': code,
                                 'duration_ms': round((time.monotonic()-start)*1000)})
                if (isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout))
                        and not received and attempt == 0 and deadline-time.monotonic() > 2):
                    continue
                raise ProviderError(code, attempts) from None
        raise ProviderError('RETRY_BUDGET', attempts)


class ProviderError(core.ValidationError):
    def __init__(self, code, attempts):
        self.code, self.attempts = code, attempts
        action={'HTTP_401':'；请在后台重新核对开放平台API Key和接口地址','HTTP_402':'；请在服务商平台核对余额','HTTP_429':'；服务商限流，请稍后重试'}.get(code,'')
        super().__init__('Provider '+code.replace('HTTP_', 'HTTP ')+action+'；AI说明未完成，已核验工具结果仍保留')
