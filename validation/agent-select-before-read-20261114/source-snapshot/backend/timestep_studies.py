"""Project-owned immutable timestep studies; revalidate source runs on every read."""
import copy
import hashlib
import html
import json
from pathlib import Path
import sqlite3
import threading
from typing import Annotated
from fastapi import Query,Request,Response
from fastapi.responses import HTMLResponse
from pydantic import Field,StrictBool,StrictFloat,model_validator
from . import core,timestep_check as check
from .domain import identifier
from .schema import Contract
from .task_capacity import CapacityError


def version():return core.hash_json({p.name:core.sha(p) for p in (Path(__file__),Path(check.__file__),Path(check.hourly.__file__),Path(check.ideal.__file__))})


class Thresholds(Contract):
    temperature_absolute_K:StrictFloat=Field(ge=0,le=20)
    load_absolute_W:StrictFloat=Field(ge=0,le=1e12)
    load_relative_pct:StrictFloat=Field(ge=0,le=100)
    near_zero_W:StrictFloat=Field(gt=0,le=1e12)


class StudyInput(Contract):
    name:str=Field(min_length=2,max_length=160)
    purpose:str=Field(min_length=15,max_length=2000)
    run_ids:list[Annotated[str,Field(pattern=r'^run_[a-f0-9]{32}$')]]=Field(min_length=2,max_length=3)
    include_ideal:StrictBool
    thresholds:Thresholds

    @model_validator(mode='after')
    def unique(self):
        if len(self.run_ids)!=len(set(self.run_ids)):raise ValueError('Distinct run IDs required')
        return self


class Studies:
    def __init__(self,domain):self.domain=domain;self.store=domain.store;self.lock=threading.Lock()

    def run_source(self,pid,rid):
        job=self.store.job(rid)
        if job['project_id']!=pid:raise core.ValidationError('Run belongs to another project')
        view=self.domain.view(rid)
        if view['status']!='succeeded':raise core.ValidationError('All source runs must be current and successful')
        rd=self.store.root/'runs'/rid
        _,manifest,_=core.read_validated(rd,check_current=False)
        return {'run_id':rid,'scheme_id':job['scheme_id'],'model_sha256':manifest['fingerprints']['model'],'weather_sha256':manifest['fingerprints']['weather'],
                'engine_sha256':job['engine_hash'],'idd_sha256':job['idd_hash'],'code_sha256':job['code_hash'],'sql_sha256':manifest['artifact_hashes']['output/eplusout.sql']},rd

    def create(self,pid,body,actor):
        self.store.get('project',pid)
        if not self.lock.acquire(blocking=False):raise CapacityError('时间步检查正在处理，请稍后再试')
        try:
            snapshots=[];sources=[]
            for rid in body.run_ids:
                snapshot,rd=self.run_source(pid,rid);snapshots.append(snapshot)
                sources.append(check.source(rd/'output/eplusout.sql',rd/'input/model.idf',body.include_ideal))
            for key in ('weather_sha256','engine_sha256','idd_sha256','code_sha256'):
                if len({s[key] for s in snapshots})!=1:raise core.ValidationError('Comparison context differs: '+key)
            summary=check.compare(sources,body.thresholds.model_dump())
            for snapshot in snapshots:
                if self.run_source(pid,snapshot['run_id'])[0]!=snapshot:raise core.ValidationError('Run changed during study')
            rec={'timestep_id':identifier('timestep'),'project_id':pid,'created_at':core.now(),'actor_user_id':actor,'input':body.model_dump(),'source_runs':snapshots,'implementation_hash':version(),'status':'assessed_model_sensitivity','summary':summary}
            rec['hash']=core.hash_json(rec);saved=self.store.put('timestep',rec);return self.view(pid,saved['timestep_id'])
        except (check.hourly.HourlyEvidenceError,sqlite3.Error,UnicodeError) as exc:raise core.ValidationError('Time-step inspection unavailable: '+str(exc)) from None
        finally:self.lock.release()

    def view(self,pid,ident):
        rec=copy.deepcopy(self.store.get('timestep',ident))
        if rec['project_id']!=pid:raise core.ValidationError('Study belongs to another project')
        reasons=[]
        if core.hash_json({k:v for k,v in rec.items() if k not in ('hash','revision')})!=rec['hash']:reasons.append('Study integrity mismatch')
        if rec['implementation_hash']!=version():reasons.append('Study implementation changed')
        for s in rec['source_runs']:
            try:
                if self.run_source(pid,s['run_id'])[0]!=s:reasons.append('Source run binding changed')
            except (core.ValidationError,KeyError,OSError,ValueError):reasons.append('Source run no longer current')
        rec['stale_reasons']=reasons
        if reasons:rec.update(status='stale',summary=None)
        return rec


def report(record):
    esc=lambda x:html.escape(str(x));summary=record.get('summary');rows=[]
    for pair in (summary or {}).get('pairs',[]):
        for r in pair['results']:
            rows.append('<tr>'+''.join('<td>'+esc(v)+'</td>' for v in (str(pair['coarse_steps_per_hour'])+' → '+str(pair['fine_steps_per_hour']),r['scope']+' / '+r['entity'],r['metric'],r['maximum_absolute_difference'],r['difference_unit'],r['hours_exceeding_threshold'],r['energy_difference_kWh'] if r['energy_difference_kWh'] is not None else '—'))+'</tr>')
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>时间步敏感性检查</title><style>body{max-width:1100px;margin:32px auto;font:15px/1.7 system-ui;padding:20px}table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccc;padding:8px;overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style><h1>'+esc(record['input']['name'])+'</h1><p>状态：'+esc(record['status'])+'；判定：'+esc((summary or {}).get('verdict','当前无有效判断'))+'</p><p>声明用途：'+esc(record['input']['purpose'])+'</p><p>两个结果接近不等于一般收敛、真实精度或规范合规。阈值由用户声明。</p><pre>'+esc(json.dumps(record['input']['thresholds'],ensure_ascii=False,indent=2))+'</pre><table><thead><tr><th>步/小时</th><th>范围</th><th>指标</th><th>最大差</th><th>单位</th><th>超限小时</th><th>积分差kWh</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table><details><summary>完整来源、时刻及限制</summary><pre>'+esc(json.dumps(record,ensure_ascii=False,indent=2))+'</pre></details></html>'


def register(app,domain):
    service=Studies(domain);app.state.timestep_studies=service
    @app.get('/api/projects/{project_id}/files/{file_id}/timestep.idf')
    def download(project_id:str,file_id:str,steps:int=Query(ge=1,le=60),expected_source_hash:str=Query(pattern=r'^[a-f0-9]{64}$')):
        rec,path=domain.file_record(project_id,file_id)
        if rec['hash']!=expected_source_hash or path.suffix.lower()!='.idf' or rec['size']>2*1024**2:raise core.ValidationError('Current IDF source of at most 2 MiB required')
        raw=path.read_bytes();result,receipt=check.derivative(raw,steps)
        if hashlib.sha256(raw).hexdigest()!=rec['hash'] or core.sha(path)!=rec['hash']:raise core.ValidationError('Model changed during download')
        return Response(result,media_type='application/octet-stream',headers={'Content-Disposition':f'attachment; filename="timestep-{steps}-{rec["hash"][:12]}.idf"','X-VRA-Source-SHA256':rec['hash'],'X-VRA-Derivative-SHA256':receipt['derivative_sha256'],'X-VRA-Physical-Fields-SHA256':receipt['physical_fields_sha256'],'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})
    @app.post('/api/projects/{project_id}/timestep-studies',status_code=201)
    def create(project_id:str,body:StudyInput,request:Request):return service.create(project_id,body,request.state.user['id'])
    @app.get('/api/projects/{project_id}/timestep-studies')
    def history(project_id:str):return [service.view(project_id,r['timestep_id']) for r in domain.store.list('timestep',project_id)]
    @app.get('/api/projects/{project_id}/timestep-studies/{timestep_id}')
    def view(project_id:str,timestep_id:str):return service.view(project_id,timestep_id)
    @app.get('/api/projects/{project_id}/timestep-studies/{timestep_id}/report.html',response_class=HTMLResponse)
    def html_report(project_id:str,timestep_id:str):return report(service.view(project_id,timestep_id))