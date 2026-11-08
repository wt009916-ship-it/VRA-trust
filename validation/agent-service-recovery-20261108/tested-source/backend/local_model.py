"""Explicit loopback-only llama.cpp adapter; no shell, downloads or cloud fallback."""
import json
import os
import re
import threading
import time

import httpx
from pydantic import Field

from . import core
from .model_recovery import ModelServiceUnavailable, TRANSIENT_STATUS, TRANSIENT_TRANSPORT
from .schema import Contract


class LocalModelSettings(Contract):
    enabled: bool = False
    port: int = Field(default=18773, ge=1024, le=65535, strict=True)
    model: str = Field(default='vra-qwen3-4b', pattern=r'^[a-zA-Z0-9_.:-]{1,80}$')


class LocalModelGateway:
    def __init__(self, store):
        self.path = store.root / 'private' / 'local-model.json'
        self.lock = threading.Lock()

    def settings(self):
        return LocalModelSettings.model_validate(core.read_json(self.path) if self.path.exists() else {})

    @staticmethod
    def token():
        value = os.environ.get('VRA_LOCAL_MODEL_TOKEN', '')
        return value if re.fullmatch(r'[A-Za-z0-9._~-]{24,256}', value) else None

    def public(self):
        config = self.settings()
        return {'provider': 'local_model', 'model': config.model, 'port': config.port,
                'enabled': config.enabled, 'key_configured': bool(self.token()),
                'endpoint': f'http://127.0.0.1:{config.port}/v1/chat/completions',
                'key_storage': 'environment', 'connection_verified': False,
                'data_scope': '仅向本机模型发送提问、项目摘要与工具结果；不自动发送原始文件。',
                'identity_notice': '模型名称由管理员声明；名称及连通性不证明模型文件来源或工程能力。'}

    def save(self, body):
        with self.lock:
            core.write_json(self.path, body.model_dump())
        return self.public()

    def complete(self, messages, tools, *, transport=None):
        config = self.settings()
        token = self.token()
        if not config.enabled or not token:
            raise core.ValidationError('本地模型尚未启用或缺少 VRA_LOCAL_MODEL_TOKEN；未调用其他服务')
        payload = {'model': config.model, 'messages': messages, 'tools': tools,
                   'tool_choice': 'auto', 'max_tokens': 1400, 'temperature': 0,
                   'chat_template_kwargs': {'enable_thinking': False}, 'stream': False}
        try:
            raw = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode('utf-8')
            if len(raw) > 192 * 1024:
                raise core.ValidationError('本地模型请求超出预算；请缩小任务，不会截断证据')
            started = time.monotonic()
            with httpx.Client(timeout=httpx.Timeout(120, connect=5), follow_redirects=False,
                              trust_env=False, transport=transport) as client:
                with client.stream('POST', f'http://127.0.0.1:{config.port}/v1/chat/completions',
                                   headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'},
                                   content=raw) as response:
                    if response.status_code in TRANSIENT_STATUS:
                        raise ModelServiceUnavailable('http_' + str(response.status_code), response.headers.get('Retry-After'))
                    if response.status_code != 200:
                        raise core.ValidationError('本地模型请求失败，HTTP ' + str(response.status_code) + '；未生成工程结果')
                    data = bytearray()
                    for chunk in response.iter_bytes():
                        if time.monotonic() - started > 120 or len(data) + len(chunk) > 1024 * 1024:
                            raise core.ValidationError('本地模型响应超出时间或大小预算')
                        data.extend(chunk)
            obj = json.loads(data)
            if obj['model'] != config.model:
                raise core.ValidationError('本地模型响应名称与配置不一致')
            choices = obj['choices']
            if not isinstance(choices, list) or len(choices) != 1 or choices[0]['finish_reason'] not in {'stop', 'tool_calls'}:
                raise core.ValidationError('本地模型输出未完整结束；拒绝执行截断的工具调用')
            message = choices[0]['message']
            if not isinstance(message, dict):
                raise ValueError('Invalid message')
            return {k: message[k] for k in ('role', 'content', 'tool_calls') if k in message}
        except ModelServiceUnavailable:
            raise
        except TRANSIENT_TRANSPORT as exc:
            raise ModelServiceUnavailable(type(exc).__name__) from None
        except (httpx.HTTPError, ValueError, KeyError, TypeError, IndexError):
            # Do not expose endpoint error bodies, credentials, prompts or raw responses.
            raise core.ValidationError('本地模型不可用或响应不完整；请检查本机服务与配置，未生成工程结果') from None
