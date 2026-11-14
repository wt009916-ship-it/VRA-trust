"""Loopback-only task API and built frontend. No third-party Python dependencies."""
from __future__ import annotations
import argparse, concurrent.futures, html, io, json, mimetypes, threading, uuid, zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from . import core

RUNS=core.ROOT/'runs'
POOL=concurrent.futures.ThreadPoolExecutor(max_workers=1)
LOCK=threading.Lock();ACTIVE=None
def run_dir(run_id):
    if not isinstance(run_id,str) or not __import__('re').fullmatch(r'[a-zA-Z0-9_-]{8,90}',run_id):raise core.ValidationError('Invalid run_id')
    p=RUNS/run_id
    if not p.is_dir():raise FileNotFoundError('run_id not found')
    return p
def public_result(run_id):
    rd=run_dir(run_id)
    if not (rd/'manifest.json').is_file():return core.read_json(rd/'task.json')
    try:
        result,manifest,plan=core.read_validated(rd)
        return {**result,'invalidation':plan,'evidence_url':'/api/runs/'+run_id+'/evidence','engine_calls_executed':manifest['engine_calls_executed']}
    except Exception as e:return {'run_id':run_id,'status':'stale','metrics':None,'carbon':None,'error':{'code':'EVIDENCE_INVALID','message':str(e)}}
def worker(run_id,case_id,scheme_id,profile_id):
    global ACTIVE
    rd=RUNS/run_id
    try:
        core.write_json(rd/'task.json',{'run_id':run_id,'case_id':case_id,'scheme_id':scheme_id,'status':'running'})
        result=core.run_simulation(case_id,scheme_id,profile_id,rd)
        core.write_json(rd/'task.json',{'run_id':run_id,'case_id':case_id,'scheme_id':scheme_id,'status':result['status']})
    except Exception as e:core.write_json(rd/'task.json',{'run_id':run_id,'status':'failed','error':{'message':str(e)}})
    finally:
        with LOCK:ACTIVE=None
def submit(case_id,scheme_id,profile_id):
    global ACTIVE
    case=core.load_case(case_id);core.get_scheme(case,scheme_id);profile=core.get_profile(profile_id)
    if profile.get('region') not in ('*',case['region']):raise core.ValidationError('因子地区不匹配')
    core.engine_path()
    with LOCK:
        if ACTIVE:raise RuntimeError('BUSY')
        rid='run_'+uuid.uuid4().hex;ACTIVE=rid
        (RUNS/rid).mkdir(parents=True)
        core.write_json(RUNS/rid/'task.json',{'run_id':rid,'case_id':case_id,'scheme_id':scheme_id,'status':'queued'})
        POOL.submit(worker,rid,case_id,scheme_id,profile_id)
    return {'run_id':rid,'status':'queued'}
def report_html(data):
    esc=lambda x:html.escape(str(x if x is not None else '未提供'))
    row=lambda label,values:'<tr><th>'+esc(label)+'</th>'+''.join('<td>'+esc(v)+'</td>' for v in values)+'</tr>'
    rs=data['results'];lines=[]
    for label,fn in [('方案',lambda r:r['scheme_name']),('run_id',lambda r:r['run_id']),('年场地能耗 kWh',lambda r:round(r['metrics']['annual_energy_kwh'],3)),('总建筑面积 m²',lambda r:r['metrics']['area_m2']),('EUI kWh/(m²·a)',lambda r:round(r['metrics']['eui_kwh_m2a'],3)),('节能率 %',lambda r:round(r['saving_rate_pct'],3) if r['saving_rate_pct'] is not None else None),('运行碳 kgCO₂',lambda r:r['carbon']['operating_carbon_kg']),('碳计算性质',lambda r:r['carbon']['status']),('因子版本',lambda r:r['carbon']['profile_id']),('Warning条数（待工程复核）',lambda r:r['warnings_count'])]:lines.append(row(label,[fn(r) for r in rs]))
    provenance=''.join('<h3>'+esc(r['scheme_id'])+'：SQL指标来源与限制</h3><pre>'+esc(json.dumps({'locators':r['metrics']['locators'],'carbon_rows':r['carbon']['rows'],'comfort_hours':r['metrics']['comfort_hours'],'limitations':r['limitations']},ensure_ascii=False,indent=2))+'</pre>' for r in rs)
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>稀土智暖可复算方案报告</title><style>body{font:14px/1.6 system-ui;max-width:1080px;margin:30px auto;color:#17332e}table{width:100%;border-collapse:collapse}td,th{border:1px solid #ccc;padding:8px;text-align:left}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.5 monospace}@media print{button{display:none}body{margin:0}tr{break-inside:avoid}}</style><button onclick="print()">打印或保存PDF</button><h1>稀土智暖 · 方案计算与核验报告</h1><p>生成时间：'+esc(core.now())+'</p><p>工程参考算例，不是企业实测。碳数值若标 scenario，为明确假设下的情景。造价与全生命周期缺项不补零，未形成可交易碳信用。</p><table>'+''.join(lines)+'</table><p>'+esc(data['recommendation'])+'</p><p>'+esc(data['ccer_note'])+'</p>'+provenance+'</html>'

class Handler(BaseHTTPRequestHandler):
    def log_message(self,fmt,*args):pass
    def respond(self,status,data,kind='application/json; charset=utf-8',filename=None):
        body=json.dumps(data,ensure_ascii=False,allow_nan=False).encode('utf-8') if kind.startswith('application/json') else data
        self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(body)));self.send_header('X-Content-Type-Options','nosniff');self.send_header('Cache-Control','no-store')
        if filename:self.send_header('Content-Disposition','attachment; filename="'+filename+'"')
        self.end_headers();self.wfile.write(body)
    def check_origin(self):
        host=self.headers.get('Host','')
        if host not in {'127.0.0.1:'+str(self.server.server_port),'localhost:'+str(self.server.server_port)}:raise core.ValidationError('Invalid Host')
        origin=self.headers.get('Origin')
        if origin and origin not in {'http://127.0.0.1:'+str(self.server.server_port),'http://localhost:'+str(self.server.server_port)}:raise core.ValidationError('Cross-origin request denied')
    def do_GET(self):
        try:
            self.check_origin();parsed=urlparse(self.path);path=parsed.path;parts=path.strip('/').split('/')
            if path=='/api/health':
                try:engine=str(core.engine_path());error=None
                except core.ValidationError as e:engine=None;error=str(e)
                return self.respond(200,{'status':'ok','engine_available':bool(engine),'engine_error':error,'version':'0.2.0','active_run':ACTIVE})
            if path=='/api/cases':return self.respond(200,{'cases':[core.load_case(k) for k in core.read_json(core.ROOT/'cases/registry.json')],'carbon_profiles':core.profiles()})
            if path=='/api/runs':
                rows=[]
                for p in sorted(RUNS.glob('run_*'),key=lambda p:p.name):
                    if p.is_dir():rows.append(public_result(p.name))
                return self.respond(200,{'runs':rows})
            if len(parts)>=3 and parts[:2]==['api','runs']:
                rid=parts[2];rd=run_dir(rid)
                if len(parts)==3:return self.respond(200,public_result(rid))
                if len(parts)==4 and parts[3]=='evidence':
                    # Permit failed evidence for diagnosis; never include host config or arbitrary paths.
                    buf=io.BytesIO()
                    with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as z:
                        for f in rd.rglob('*'):
                            if f.is_file() and not f.is_symlink():z.write(f,f.relative_to(rd))
                    return self.respond(200,buf.getvalue(),'application/zip',rid+'.zip')
            if path in {'/api/compare','/api/report'}:
                ids=parse_qs(parsed.query).get('runs',[''])[0].split(',')
                if len(ids)>20:raise core.ValidationError('Too many runs')
                data=core.compare_runs([run_dir(i) for i in ids])
                if path=='/api/report':return self.respond(200,report_html(data).encode(),'text/html; charset=utf-8')
                return self.respond(200,data)
            if path.startswith('/api/'):return self.respond(404,{'error':'Not found'})
            dist=core.ROOT/'frontend/dist';rel='index.html' if path=='/' else path.lstrip('/')
            f=core.relative_file(dist,rel)
            return self.respond(200,f.read_bytes(),mimetypes.guess_type(f.name)[0] or 'application/octet-stream')
        except FileNotFoundError as e:self.respond(404,{'error':str(e)})
        except (ValueError,KeyError,TypeError) as e:self.respond(400,{'error':str(e)})
        except Exception as e:self.respond(500,{'error':type(e).__name__+': '+str(e)})
    def do_POST(self):
        try:
            self.check_origin()
            if self.headers.get('Content-Type','').split(';')[0]!='application/json':raise core.ValidationError('JSON body required')
            n=int(self.headers.get('Content-Length','0'))
            if n<=0 or n>262144:raise core.ValidationError('Request body must be 1..262144 bytes')
            def reject(x):raise core.ValidationError('Non-finite JSON')
            body=json.loads(self.rfile.read(n),parse_constant=reject)
            if not isinstance(body,dict):raise core.ValidationError('Object body required')
            path=urlparse(self.path).path
            if path=='/api/runs':return self.respond(202,submit(body['case_id'],body['scheme_id'],body.get('profile_id','none')))
            if path=='/api/recalculate':
                rid='run_'+uuid.uuid4().hex
                data=core.recalculate_carbon(run_dir(body['run_id']),RUNS/rid,body['profile_id'])
                return self.respond(201,data)
            if path=='/api/cost':
                r=public_result(body['run_id'])
                if r['status']!='succeeded':raise core.ValidationError('Valid run required')
                return self.respond(200,core.cost_scenario(r['metrics']['energy_by_carrier_kwh'],body['tariffs'],body['investment'],body['horizon'],body['discount']))
            if path=='/api/carbon-value':return self.respond(200,core.carbon_value_scenario(body['quantity_t'],body['price'],body['development_cost'],body['monitoring_cost'],body['eligibility_evidence']))
            if path=='/api/evidence-gaps':return self.respond(200,core.evidence_gaps(body['items']))
            return self.respond(404,{'error':'Not found'})
        except RuntimeError as e:self.respond(409,{'error':str(e)})
        except FileNotFoundError as e:self.respond(404,{'error':str(e)})
        except (ValueError,KeyError,TypeError) as e:self.respond(400,{'error':str(e)})
        except Exception as e:self.respond(500,{'error':type(e).__name__+': '+str(e)})

def main(port=8765):
    RUNS.mkdir(exist_ok=True)
    for p in RUNS.glob('run_*/task.json'):
        if not (p.parent/'manifest.json').is_file():
            task=core.read_json(p)
            if task.get('status') in {'queued','running'}:core.write_json(p,{**task,'status':'failed','error':{'message':'服务已重启，原任务未完成，请新建任务。'}})
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    print('稀土智暖本地服务：http://127.0.0.1:'+str(port),flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close();POOL.shutdown(wait=True,cancel_futures=True)
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--port',type=int,default=8765);main(ap.parse_args().port)
