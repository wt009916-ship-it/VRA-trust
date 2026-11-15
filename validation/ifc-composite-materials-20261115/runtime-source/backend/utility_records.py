"""Source-bound utility comparisons with preserved originals and current-state reports."""
import copy,csv,html,io,json,threading
from pathlib import Path
from fastapi import Query,Request
from fastapi.responses import HTMLResponse,Response
from . import core,utility_comparison as calc,end_use,end_use_records,hourly_thermal,calculation_provenance as provenance
from .domain import identifier
from .task_capacity import CapacityError


def version():return core.hash_json({Path(m.__file__).name:core.sha(Path(m.__file__)) for m in (calc,end_use,end_use_records,hourly_thermal,core,provenance)}|{'service':core.sha(Path(__file__))})


class Comparisons:
    def __init__(self,domain):self.domain=domain;self.store=domain.store;self.sources=end_use_records.Ledgers(domain);self.lock=threading.Lock()
    def bill(self,pid,eid,nature=None):
        ev=self.store.get('evidence',eid)
        if ev['project_id']!=pid or ev['type']!='bill' or ev['review_state']!='confirmed' or not ev['source_file'] or ev['status'] in ('MISSING','AI_INFERRED'):raise core.ValidationError('Confirmed project bill evidence with an original file is required')
        if nature=='measured' and ev['status'] not in ('MEASURED','DOCUMENTED'):raise core.ValidationError('Assumed/imported bill cannot be labelled measured')
        file,path=self.domain.file_record(pid,ev['source_file']);return ev,file,path
    def catalog(self,pid,rid):
        source,rd=self.sources.source(pid,rid);data=calc.native_meter(rd)
        if self.sources.source(pid,rid)[0]!=source:raise core.ValidationError('Run changed while reading utility meters')
        return {'source_run':source,**{k:v for k,v in data.items() if k not in ('series','selected_meter')}}
    def create(self,pid,body,actor):
        if not self.lock.acquire(blocking=False):raise CapacityError('账单比较正在核验，请稍后重试')
        try:
            project=self.store.get('project',pid);ev,file,path=self.bill(pid,body.bill_evidence_id,body.bill_nature);source,rd=self.sources.source(pid,body.run_id)
            native=calc.native_meter(rd,body.meter);bills=calc.parse_bill(path,native['selected_meter']['resource'],body.period_kind);result=calc.compare(bills,native,body)
            obj={'utility_id':identifier('utility'),'project_id':pid,'project_revision':project['revision'],'input':body.model_dump(),'actor_user_id':actor,'created_at':core.now(),'calculator_version':version(),'source_run':source,'file_snapshot':file,'evidence_snapshot':[ev],'result':result};obj['hash']=core.hash_json(obj)
            def check():
                if self.sources.source(pid,body.run_id)[0]!=source:raise core.ValidationError('Run changed during utility comparison')
                if self.bill(pid,body.bill_evidence_id,body.bill_nature)[:2]!=(ev,file):raise core.ValidationError('Bill changed during utility comparison')
            saved=provenance.persist(self.domain,'utility',obj,pre_insert_check=check);return self.view(pid,saved['utility_id'])
        finally:self.lock.release()
    def view(self,pid,uid):
        obj=copy.deepcopy(self.store.get('utility',uid))
        if obj['project_id']!=pid:raise core.ValidationError('Comparison belongs to another project')
        validity=provenance.validity(self.domain,obj,version());reasons=validity['stale_reasons']
        if core.hash_json({k:v for k,v in obj.items() if k not in ('hash','revision')})!=obj['hash']:reasons.append('comparison_integrity_changed')
        try:
            if self.sources.source(pid,obj['source_run']['run_id'])[0]!=obj['source_run']:reasons.append('native_source_changed')
            self.bill(pid,obj['input']['bill_evidence_id'],obj['input']['bill_nature'])
        except (core.ValidationError,OSError,KeyError,ValueError):reasons.append('current_bill_or_native_source_unavailable')
        obj.update(validity,status='stale' if reasons else obj['result']['status'])
        if reasons:obj['result']=None
        return obj
    def history(self,pid,before=None):
        with self.store.connect() as con:rows=con.execute("SELECT rowid,id,json_extract(body,'$.input.name') AS name FROM records WHERE kind='utility' AND project_id=? AND (? IS NULL OR rowid<?) ORDER BY rowid DESC LIMIT 21",(pid,before,before)).fetchall()
        return {'records':[{'utility_id':r['id'],'name':r['name']} for r in rows[:20]],'next_before':rows[19]['rowid'] if len(rows)>20 else None,'detail_status':'not_checked'}


def report(record):
    esc=lambda x:html.escape('—' if x is None else str(x));r=record.get('result');content='<p>当前来源无法核验，全部比较数值已撤下。</p>'
    if r:
        rows=''.join('<tr>'+''.join('<td>'+esc(v)+'</td>' for v in (x['source_line'],x['original']['start'],x['original']['end'],x['bill_kwh'],x['native_kwh'],x['difference_kwh']))+'</tr>' for x in r['rows'])
        s=r['statistics'];context='<p>账单性质：'+esc(record['input']['bill_nature'])+'；配对：'+esc(record['input']['alignment'])+'；原生年份：'+esc(r['native']['year'])+'；气象年份：'+esc(r['native']['weather_years'])+'。本地标准时，开始含、结束不含。</p><p>'+esc('；'.join(r['context_reasons']))+'</p>';content=context+'<p>MBE%：'+esc(s['mbe_percent'])+'；CV(RMSE)%：'+esc(s['cvrmse_percent'])+'；RMSE kWh：'+esc(s['rmse_kwh'])+'</p><p>声明阈值内：'+esc(r['within_declared_tolerances'])+'。此判定不是实楼校准或合规认证。</p><table><tr><th>原行</th><th>账期开始（含）</th><th>账期结束（不含）</th><th>账单kWh</th><th>模拟kWh</th><th>模拟−账单kWh</th></tr>'+rows+'</table><ul>'+''.join('<li>'+esc(x)+'</li>' for x in r['limitations'])+'</ul>'
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>账单与模拟比较</title><style>body{font:15px/1.7 system-ui;margin:32px auto;max-width:1200px;padding:20px}td,th{border:1px solid #bbb;padding:6px}table{border-collapse:collapse}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style><h1>'+esc(record['input']['name'])+'</h1><p>'+esc(record['input']['purpose'])+'</p>'+content+'<details><summary>时间映射、边界和完整来源回执</summary><pre>'+esc(json.dumps(record,ensure_ascii=False,indent=2))+'</pre></details></html>'


def export_csv(record):
    if not record.get('result'):raise core.ValidationError('Current source unavailable; comparison CSV withheld')
    stream=io.StringIO(newline='');writer=csv.writer(stream,lineterminator='\n');writer.writerow(['source_line','start_inclusive','end_exclusive','native_start','native_end','bill_kwh','native_kwh','difference_kwh'])
    for r in record['result']['rows']:writer.writerow([r['source_line'],r['original']['start'],r['original']['end'],r['mapped_start'],r['mapped_end'],r['bill_kwh'],r['native_kwh'],r['difference_kwh']])
    return stream.getvalue()


def register(app,domain):
    service=Comparisons(domain);app.state.utility_comparisons=service
    @app.get('/api/projects/{project_id}/utility-meters/{run_id}')
    def catalog(project_id:str,run_id:str):return service.catalog(project_id,run_id)
    @app.post('/api/projects/{project_id}/utility-comparisons',status_code=201)
    def create(project_id:str,body:calc.ComparisonInput,request:Request):return service.create(project_id,body,request.state.user['id'])
    @app.get('/api/projects/{project_id}/utility-comparisons')
    def history(project_id:str,before:int|None=Query(default=None,ge=1,le=2**53-1)):return service.history(project_id,before)
    @app.get('/api/projects/{project_id}/utility-comparisons/{utility_id}')
    def view(project_id:str,utility_id:str):return service.view(project_id,utility_id)
    @app.get('/api/projects/{project_id}/utility-comparisons/{utility_id}/report.html',response_class=HTMLResponse)
    def html_report(project_id:str,utility_id:str):return report(service.view(project_id,utility_id))
    @app.get('/api/projects/{project_id}/utility-comparisons/{utility_id}/comparison.csv')
    def download(project_id:str,utility_id:str):return Response(export_csv(service.view(project_id,utility_id)),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':'attachment; filename="utility-comparison.csv"'})
