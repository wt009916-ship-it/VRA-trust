"""Single-process admission control before body parsing and password work."""
import time
import threading
from starlette.responses import JSONResponse


class Admission:
    def __init__(self, app, concurrency=32, burst=240, rate=120):
        self.app, self.maximum, self.burst, self.rate = app, concurrency, burst, rate
        self.active, self.tokens, self.updated = 0, float(burst), time.monotonic()
        self.lock = threading.Lock()

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or not scope['path'].startswith('/api/'):
            return await self.app(scope, receive, send)
        with self.lock:
            now = time.monotonic()
            self.tokens = min(self.burst, self.tokens+(now-self.updated)*self.rate)
            self.updated = now
            allowed = self.active < self.maximum and self.tokens >= 1
            if allowed:
                self.active += 1
                self.tokens -= 1
        if not allowed:
            return await JSONResponse({'detail': '请求过于密集，请稍后重试'}, status_code=429,
                headers={'Retry-After': '1', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})(scope, receive, send)
        try:
            await self.app(scope, receive, send)
        finally:
            with self.lock:
                self.active -= 1
