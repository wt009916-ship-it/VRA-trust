"""Isolated benchmark-only bridge to production Agent.call; never loaded by the product.

All calls are authenticated/project-scoped by production middleware. Compute is always
disabled. A loopback proxy preserves actual local-model requests/responses without keys.
"""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import itertools
import json
import os
from pathlib import Path
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    os.environ['VRA_DATA_DIR'] = str(args.output/'private-runtime')
    os.environ['VRA_API_KEY'] = 'local-benchmark-no-secret'
    from backend.api import create_app
    import httpx
    import uvicorn
    app = create_app(start_worker=False)

    @app.post('/api/projects/{project_id}/benchmark/tool')
    def tool(project_id: str, body: dict):
        return app.state.agent.call(project_id, body['name'], body.get('arguments', {}), False)

    # create_app ends with the frontend catch-all mount. Place this test-only route
    # before that mount; production authentication middleware still wraps it.
    app.router.routes.insert(0, app.router.routes.pop())

    counter = itertools.count(1+max((int(p.stem.split('-')[1]) for p in args.output.glob('llm-*.json')),default=-1))

    class Proxy(BaseHTTPRequestHandler):
        def do_POST(self):
            raw = self.rfile.read(int(self.headers['Content-Length']))
            data = json.loads(raw)
            n = next(counter)
            record = {'number': n, 'request': data, 'started': time.time()}
            try:
                response = httpx.post('http://127.0.0.1:8790/v1/chat/completions', json=data, timeout=180)
                record.update(http_status=response.status_code, response=response.json(), seconds=time.time()-record['started'])
                payload = response.content
                self.send_response(response.status_code)
            except Exception as exc:
                record['error'] = f'{type(exc).__name__}: {exc}'
                payload = json.dumps({'error':record['error']}).encode()
                self.send_response(502)
            (args.output/f'llm-{n:03}.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf8')
            self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(payload)))
            self.end_headers()
            try:
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *_):
            pass

    proxy = ThreadingHTTPServer(('127.0.0.1',8791),Proxy)
    threading.Thread(target=proxy.serve_forever,daemon=True).start()
    try:
        uvicorn.run(app, host='127.0.0.1',port=8770,log_level='warning')
    finally:
        proxy.shutdown()


if __name__ == '__main__':
    main()
