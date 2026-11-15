"""Source-bound annual end-use ledgers; never rewrite a physical run."""
import copy
import html
import json
from pathlib import Path
import sqlite3
import threading
from fastapi import Query, Request
from fastapi.responses import HTMLResponse
from pydantic import Field
from . import core,end_use,hourly_thermal
from .domain import identifier
from .schema import Contract
from .task_capacity import CapacityError


def version():return core.hash_json({p.name:core.sha(p) for p in (Path(__file__),Path(end_use.__file__),Path(core.__file__),Path(hourly_thermal.__file__))})


class LedgerInput(Contract):
    name:str=Field(min_length=2,max_length=160)
    purpose:str=Field(min_length=15,max_length=2000)
    run_id:str=Field(pattern=r'^run_[a-f0-9]{32}$')


class Ledgers:
    def __init__(self,domain):self.domain=domain;self.store=domain.store;self.lock=threading.Lock()

    def source(self,pid,rid):
        job=self.store.job(rid)
        if job['project_id']!=pid:raise core.ValidationError('Run belongs to another project')
        if self.domain.view(rid)['status']!='succeeded':raise core.ValidationError('Current successful source run required')
        rd=self.store.root/'runs'/rid;_,manifest,_=core.read_validated(rd,check_current=False)
        return {'run_id':rid,'scheme_id':job['scheme_id'],'model_sha256':manifest['fingerprints']['model'],'weather_sha256':manifest['fingerprints']['weather'],'engine_sha256':job['engine_hash'],'idd_sha256':job['idd_hash'],'code_sha256':job['code_hash'],'sql_sha256':manifest['artifact_hashes']['output/eplusout.sql'],'mtd_sha256':manifest['artifact_hashes'].get('output/eplusout.mtd')},rd

    def create(self,pid,body,actor):
        self.store.get('project',pid)
        if not self.lock.acquire(blocking=False):raise CapacityError('能耗分项正在处理，请稍后重试')
        try:
            source,rd=self.source(pid,body.run_id)
            summary=end_use.inspect(rd/'output/eplusout.sql',rd/'input/model.idf',rd/'output/eplusout.mtd' if source['mtd_sha256'] else None)
            if self.source(pid,body.run_id)[0]!=source:raise core.ValidationError('Source changed during ledger creation')
            record={'enduse_id':identifier('enduse'),'project_id':pid,'created_at':core.now(),'actor_user_id':actor,'input':body.model_dump(),'source_run':source,'implementation_hash':version(),'status':'calculated_model_end_uses','summary':summary}
            record['hash']=core.hash_json(record);saved=self.store.put('enduse',record);return self.view(pid,saved['enduse_id'])
        except (sqlite3.Error,UnicodeError) as exc:raise core.ValidationError('End-use data unavailable: '+str(exc)) from None
        finally:self.lock.release()

    def history(self,pid,before=None):
        # Names only: no historical numeric summary is trusted without detail revalidation.
        with self.store.connect() as con:
            rows=con.execute("SELECT rowid,id,json_extract(body,'$.input.name') AS name, json_extract(body,'$.created_at') AS created_at FROM records WHERE kind='enduse' AND project_id=? AND (? IS NULL OR rowid<?) ORDER BY rowid DESC LIMIT 21",(pid,before,before)).fetchall()
        return {'records':[{'enduse_id':r['id'],'name':r['name'],'created_at':r['created_at']} for r in rows[:20]],'next_before':rows[19]['rowid'] if len(rows)>20 else None,'limit':20,'detail_status':'not_checked'}

    def view(self,pid,ident):
        record=copy.deepcopy(self.store.get('enduse',ident))
        if record['project_id']!=pid:raise core.ValidationError('Ledger belongs to another project')
        reasons=[]
        if core.hash_json({k:v for k,v in record.items() if k not in ('hash','revision')})!=record['hash']:reasons.append('Ledger integrity changed')
        if record['implementation_hash']!=version():reasons.append('Ledger implementation changed')
        try:
            if self.source(pid,record['source_run']['run_id'])[0]!=record['source_run']:reasons.append('Source binding changed')
        except (core.ValidationError,KeyError,OSError,ValueError):reasons.append('Source run no longer current')
        record['stale_reasons']=reasons
        if reasons:record.update(status='stale',summary=None)
        return record


def report(record):
    esc=lambda x:html.escape(str(x));s=record.get('summary');body='<p>当前来源失效或无法核验，全部数值已撤下。</p>'
    if s:
        columns=list(s['carrier_totals']);rows=[]
        for r in s['rows']:
            cells=[]
            for c in columns:
                v=r['carriers'][c];native=v['hourly_meter_kwh'];cells.append('<td>'+esc(format(v['tabulated']['kwh'],'.6g'))+'<br>逐时：'+('—' if native is None else esc(format(native,'.8g')) )+'</td>')
            rows.append('<tr><th>'+esc(r['label'])+'</th>'+''.join(cells)+'</tr>')
        body='<p>范围：'+esc(s['hours'])+'小时；表格值为原生舍入值，逐时值仅在完整计量核对后显示。单位kWh；各载体性质不同。</p><p>理想系统：'+esc('、'.join(s['model']['ideal_systems']) or '模型未声明理想系统')+'</p><table><thead><tr><th>用途</th>'+''.join('<th>'+esc(c)+'</th>' for c in columns)+'</tr></thead><tbody>'+''.join(rows)+'</tbody></table><ul>'+''.join('<li>'+esc(x)+'</li>' for x in s['limitations'])+'</ul>'
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>设备与用途能耗账</title><style>body{max-width:1100px;margin:32px auto;padding:20px;font:15px/1.7 system-ui}table{border-collapse:collapse;width:100%}td,th{border:1px solid #bbb;padding:8px}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style><h1>'+esc(record['input']['name'])+'</h1><p>'+esc(record['input']['purpose'])+'</p>'+body+'<details><summary>计量来源、舍入误差与完整回执</summary><pre>'+esc(json.dumps(record,ensure_ascii=False,indent=2))+'</pre></details></html>'


def register(app,domain):
    service=Ledgers(domain);app.state.end_use_ledgers=service
    @app.post('/api/projects/{project_id}/end-use-ledgers',status_code=201)
    def create(project_id:str,body:LedgerInput,request:Request):return service.create(project_id,body,request.state.user['id'])
    @app.get('/api/projects/{project_id}/end-use-ledgers')
    def history(project_id:str,before:int|None=Query(default=None,ge=1,le=2**53-1)):return service.history(project_id,before)
    @app.get('/api/projects/{project_id}/end-use-ledgers/{enduse_id}')
    def view(project_id:str,enduse_id:str):return service.view(project_id,enduse_id)
    @app.get('/api/projects/{project_id}/end-use-ledgers/{enduse_id}/report.html',response_class=HTMLResponse)
    def html_report(project_id:str,enduse_id:str):return report(service.view(project_id,enduse_id))
