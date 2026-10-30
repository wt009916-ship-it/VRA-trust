"""One labelled HTTP503 followed by an actual local Qwen response, via the production Gateway."""
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
import time

import httpx


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():
        parser.error('output must be a new file')
    events=[]
    class Proxy(BaseHTTPRequestHandler):
        def do_POST(self):
            raw=self.rfile.read(int(self.headers['Content-Length']))
            number=len(events)
            event={'attempt':number+1,'injected':number==0,'actual_model_forwarded':number>0}
            events.append(event)
            if number==0:
                status,payload=503,b'{"error":"controlled acceptance fault"}'
            else:
                response=httpx.post('http://127.0.0.1:8790/v1/chat/completions',content=raw,
                    headers={'Content-Type':'application/json'},timeout=150)
                status,payload=response.status_code,response.content
            event['http_status']=status
            self.send_response(status)
            self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        def log_message(self,*a):
            pass
    server=ThreadingHTTPServer(('127.0.0.1',8792),Proxy)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    report={}
    try:
        with httpx.Client(base_url='http://127.0.0.1:8770',timeout=180) as client:
            auth=client.post('/api/auth/login',json={'username':'qwen_repair','password':'Qwen-repair-acceptance-2026!'})
            auth.raise_for_status();client.headers['X-CSRF-Token']=auth.json()['csrf_token']
            pid=client.get('/api/projects').json()[0]['project_id'];base='/api/projects/'+pid
            config={'enabled':True,'model':'qwen3-benchmark','endpoint':'http://127.0.0.1:8792/v1/chat/completions',
                    'request_timeout_s':120,'max_output_tokens':1000,'local_qwen_no_thinking':True}
            try:
                client.put('/api/developer/provider',json=config).raise_for_status()
                started=time.monotonic()
                response=client.post(base+'/agent/chat',json={'message':'核对天气来源与数据质量，不提交仿真。请用简短中文说明。',
                                                           'mode':'provider','task':'weather','allow_compute':False})
                response.raise_for_status();task=response.json()
                while task['status']=='running' and time.monotonic()-started<220:
                    time.sleep(.3)
                    task=client.get(base+'/agent/'+task['agent_id']).json()
                jobs=client.get(base+'/runs').json()
                report={'scope':'Controlled first HTTP503; later model responses are real Qwen',
                        'proxy':events,'task':task,'seconds':time.monotonic()-started,'engine_jobs_created':len(jobs)}
                args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
                assert task['status']=='succeeded' and task['explanation_status']=='available'
                event=next(e for e in task['events'] if e['tool']=='llm.request')
                assert event['request_info']['attempts'][0]['code']=='HTTP_503'
                assert event['request_info']['attempts'][1]['status']=='succeeded'
                assert not jobs
                print('TRANSIENT503_REAL_QWEN_RECOVERED',round(report['seconds'],3),'PROXY_REQUESTS',len(events),'ENGINE_JOBS',len(jobs))
            finally:
                config['endpoint']='http://127.0.0.1:8791/v1/chat/completions'
                client.put('/api/developer/provider',json=config).raise_for_status()
    finally:
        server.shutdown();server.server_close()


if __name__=='__main__':
    main()
