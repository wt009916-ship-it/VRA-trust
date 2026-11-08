from pathlib import Path
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from threading import Thread
import json,sqlite3,hashlib
O=Path('C:/Users/18483/AppData/Local/Temp/vra-scenario-source-20261108');info=json.loads((O/'ready.json').read_text());root=(Path(info['runtime'])/'api').resolve()
with sqlite3.connect(root/'vra.sqlite3') as db:row=db.execute("SELECT body FROM records WHERE kind='file' AND id=? ORDER BY revision DESC LIMIT 1",(info['file_id'],)).fetchone()
target=(root/json.loads(row[0])['path']).resolve();assert target.is_relative_to(root)
raw=target.read_bytes();assert hashlib.sha256(raw).hexdigest()==info['source_hash'];events=[]
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_POST(self):
        size=int(self.headers.get('Content-Length','0'));assert 0<=size<=1048576
        body=self.rfile.read(size)
        if self.path=='/invalidate':target.write_bytes(b'Damaged isolated acceptance copy during preflight')
        elif self.path=='/restore':target.write_bytes(raw)
        elif self.path=='/record':
            record=json.loads(body);assert record['calculation']['project_id']==info['project_id']
            (O/'browser-calculated.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
        else:self.send_error(404);return
        events.append(self.path);self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(b'{"ok":true}')
server=ThreadingHTTPServer(('127.0.0.1',18780),Handler);Thread(target=server.serve_forever,daemon=True).start()
print('Isolated fault-control ready on 127.0.0.1:18780',flush=True)
try:assert input().strip()=='stop'
finally:
    server.shutdown();server.server_close();target.write_bytes(raw)
    (O/'fault-control-receipt.json').write_text(json.dumps({'events':events,'stopped':True,'isolated_copy_restored':hashlib.sha256(target.read_bytes()).hexdigest()==info['source_hash']},indent=2));print('Fault-control stopped and isolated copy restored.',flush=True)
