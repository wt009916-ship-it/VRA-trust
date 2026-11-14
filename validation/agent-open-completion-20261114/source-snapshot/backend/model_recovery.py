"""Typed inference transport failures; never retries tools or parses error bodies."""
import math
import re
import time
from email.utils import parsedate_to_datetime

import httpx

from . import core


TRANSIENT_STATUS = {429, 502, 503, 504}
TRANSIENT_TRANSPORT = (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.WriteTimeout,
                       httpx.ConnectError, httpx.ReadError, httpx.WriteError,
                       httpx.RemoteProtocolError)


class ModelServiceUnavailable(core.ValidationError):
    def __init__(self, code, retry_after=None):
        super().__init__('模型服务暂时不可用；未接受本次响应或执行其中的工具')
        self.code = code
        self.retry_after = retry_after


def retry_delay(value, *, now=None):
    """Return seconds, or infinity when a server hint cannot be safely honored."""
    if value is None:
        return 0.0
    if len(value) > 128:
        return math.inf
    value = value.strip()
    if re.fullmatch(r'[0-9]{1,10}', value):
        return float(value)
    try:
        date = parsedate_to_datetime(value)
        if date.tzinfo is None:
            return math.inf
        return max(0.0, date.timestamp() - (time.time() if now is None else now))
    except (ValueError, TypeError, OverflowError):
        return math.inf


def decision(error, attempts, turn, events, reserve):
    delay = max(float(2 ** attempts), retry_delay(error.retry_after))
    reason = ('retry_limit' if attempts >= 2 else
              'response_budget' if turn >= 4 else
              'event_budget' if events + 1 + reserve > 15 else
              'server_delay_exceeds_budget' if delay > 5 else 'transient_inference_only')
    return {'code': error.code, 'retry_allowed': reason == 'transient_inference_only',
            'reason': reason, 'delay_seconds': delay if delay <= 5 else None,
            'tools_replayed': False}


def identity(gateway):
    public = gateway.public()
    return {key: public.get(key) for key in ('provider', 'model', 'endpoint', 'enabled')}
