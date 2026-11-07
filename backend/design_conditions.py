"""Project-owned, append-only design climate sources and explicit field checks."""
import html
import json
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import Field, HttpUrl, StrictInt, model_validator
from fastapi.responses import HTMLResponse

from . import core, design_condition_parser as parser
from .domain import identifier
from .schema import Contract


def version():
    return core.hash_json({'service':core.sha(Path(__file__)), 'parser':core.sha(Path(parser.__file__))})


class SourceInput(Contract):
    file_id: str = Field(pattern=r'^file_[a-f0-9]{32}$')
    encoding: Literal['utf-8-sig','cp1252'] = 'utf-8-sig'
    declared_format: Literal['IDF 9.0'] = 'IDF 9.0'
    title: str = Field(min_length=2,max_length=200)
    publisher: str = Field(min_length=2,max_length=200)
    edition: str = Field(min_length=1,max_length=100)
    source_url: HttpUrl
    acquired_on: date
    permission: str = Field(min_length=5,max_length=1000)
    scope: str = Field(min_length=5,max_length=2000)

    @model_validator(mode='after')
    def valid_source(self):
        if self.acquired_on>date.today():
            raise ValueError('Future acquisition date cannot be claimed')
        if self.source_url.username or self.source_url.password:
            raise ValueError('Source URL must not contain credentials')
        return self


class Review(Contract):
    expected_revision: StrictInt = Field(ge=1)
    state: Literal['confirmed','pending','rejected']
    basis: str = Field(min_length=10,max_length=2000)


class Pair(Contract):
    model_day: str = Field(min_length=1,max_length=200)
    source_day: str = Field(min_length=1,max_length=200)


class CheckInput(Contract):
    source_id: str = Field(pattern=r'^designsource_[a-f0-9]{32}$')
    source_revision: StrictInt = Field(ge=1)
    model_evidence_id: str = Field(pattern=r'^evidence_[a-f0-9]{32}$')
    model_revision: StrictInt = Field(ge=1)
    pairs: list[Pair] = Field(min_length=1,max_length=64)


class DesignConditions:
    def __init__(self,domain):
        self.domain,self.store=domain,domain.store

    def owned(self,kind,pid,ident):
        obj=self.store.get(kind,ident)
        if obj['project_id']!=pid:
            raise KeyError(ident)
        return obj

    def save_source(self,pid,body,user):
        self.store.get('project',pid)
        f,path=self.domain.file_record(pid,body.file_id)
        if path.suffix.lower()!='.ddy':
            raise core.ValidationError('Design source requires a preserved DDY file')
        if path.stat().st_size>parser.MAX_BYTES:
            raise core.ValidationError('DDY exceeds 2 MiB inspection budget')
        parsed=parser.parse(path.read_bytes(),body.encoding)
        obj={'designsource_id':identifier('designsource'),'project_id':pid,
            'input':body.model_dump(mode='json'),'file_snapshot':f,'catalog':parsed,'version':version(),
            'created_at':core.now(),'review':{'state':'pending','basis':None,'user_id':user}}
        with self.store.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            self.budget(con,'designsource',pid,32)
            current,_=self.domain.file_record(pid,body.file_id)
            if current!=f:
                raise core.ValidationError('Source changed during inspection')
            return self.store.put_in(con,'designsource',obj)

    @staticmethod
    def budget(con,kind,pid,limit):
        n=con.execute('SELECT COUNT(DISTINCT id) FROM records WHERE kind=? AND project_id=?',(kind,pid)).fetchone()[0]
        if n>=limit:
            raise core.ValidationError('Design-source/check project record budget exceeded')

    def source(self,pid,ident):
        obj=self.owned('designsource',pid,ident)
        reasons=[]
        if obj['version']!=version():
            reasons.append('verifier_version_changed')
        try:
            f,_=self.domain.file_record(pid,obj['input']['file_id'])
            if f!=obj['file_snapshot']:
                reasons.append('source_file_revision_changed')
        except (OSError,ValueError,KeyError):
            reasons.append('source_file_unavailable')
        return {**obj,'source_status':'stale' if reasons else 'intact','stale_reasons':reasons,
                'catalog':None if reasons else obj['catalog'],'authority_status':'declared_not_independently_verified'}

    def catalog(self,pid):
        rows=[]
        for obj in self.store.list('designsource',pid):
            current=self.source(pid,obj['designsource_id'])
            days=[d['name'] for d in (current['catalog'] or {}).get('days',[])]
            rows.append({k:v for k,v in {**current,'day_names':days}.items() if k!='catalog'})
        return rows

    def review(self,pid,ident,body,user):
        current=self.source(pid,ident)
        if current['source_status']!='intact':
            raise core.ValidationError('Source changed; register and inspect a new source')
        obj=self.owned('designsource',pid,ident)
        obj.update(review={'state':body.state,'basis':body.basis,'user_id':user,'at':core.now()})
        return self.store.put('designsource',obj,body.expected_revision)

    def model(self,pid,eid):
        ev=self.owned('evidence',pid,eid)
        if ev['type']!='idf' or ev['review_state']!='confirmed' or not ev['source_file']:
            raise core.ValidationError('Select a confirmed model evidence record')
        f,path=self.domain.file_record(pid,ev['source_file'])
        if path.suffix.lower()!='.idf' or ev['hash']!=f['hash']:
            raise core.ValidationError('Model evidence/file mismatch')
        if path.stat().st_size>32*1024**2:
            raise core.ValidationError('Model exceeds inspection budget')
        parsed=parser.parse(path.read_bytes(),model=True)
        return {'evidence':ev,'file':f,'catalog':parsed}

    def check(self,pid,body,user):
        project=self.store.get('project',pid)
        source=self.source(pid,body.source_id)
        model=self.model(pid,body.model_evidence_id)
        if source['source_status']!='intact' or source['review']['state']!='confirmed':
            raise core.ValidationError('Select an intact, reviewed design source')
        if source['revision']!=body.source_revision or model['evidence']['revision']!=body.model_revision:
            raise core.ValidationError('Selected source/model revision changed; refresh')
        result=parser.compare(model['catalog'],source['catalog'],[p.model_dump() for p in body.pairs])
        obj={'designcheck_id':identifier('designcheck'),'project_id':pid,'project_revision':project['revision'],
             'created_at':core.now(),'user_id':user,'input':body.model_dump(),'version':version(),
             'source_snapshot':self.owned('designsource',pid,body.source_id),'model_snapshot':model,
             'result':result,'status':'current'}
        with self.store.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            self.budget(con,'designcheck',pid,128)
            if self.store.get('project',pid)['revision']!=project['revision']:
                raise core.ValidationError('Project changed during design check')
            if self.owned('designsource',pid,body.source_id)!=obj['source_snapshot']:
                raise core.ValidationError('Design source changed during check')
            if self.model(pid,body.model_evidence_id)!=model:
                raise core.ValidationError('Model changed during design check')
            current=self.source(pid,body.source_id)
            if current['source_status']!='intact':
                raise core.ValidationError('Design source changed during check')
            return self.store.put_in(con,'designcheck',obj)

    def view(self,pid,ident):
        obj=self.owned('designcheck',pid,ident)
        reasons=[]
        if obj['version']!=version():
            reasons.append('verifier_version_changed')
        if self.store.get('project',pid)['revision']!=obj['project_revision']:
            reasons.append('project_revision_changed')
        try:
            current=self.source(pid,obj['input']['source_id'])
            if (current['source_status']!='intact' or current['revision']!=obj['source_snapshot']['revision']
                    or current['review']['state']!='confirmed'):
                reasons.append('design_source_changed_or_withdrawn')
        except (KeyError,ValueError,OSError):
            reasons.append('design_source_unavailable')
        try:
            if self.model(pid,obj['input']['model_evidence_id'])!=obj['model_snapshot']:
                reasons.append('model_changed')
        except (KeyError,ValueError,OSError):
            reasons.append('model_unavailable_or_unconfirmed')
        return {**obj,'status':'stale' if reasons else 'current','stale_reasons':reasons,
                'result':None if reasons else obj['result']}


def report(record):
    result=record['result']
    rows=''
    if result:
        for row in result['rows']:
            rows+='<h2>'+html.escape(row['model_day'])+' → '+html.escape(row['source_day'])+'</h2><p>'+html.escape(row['status'])+'</p>'
            rows+='<table><tr><th>字段</th><th>单位</th><th>模型</th><th>来源</th><th>一致</th></tr>'
            for f in row['fields']:
                rows+='<tr>'+''.join('<td>'+html.escape(str(f[k]))+'</td>' for k in ('field','unit','model','source','equal'))+'</tr>'
            rows+='</table>'
    else:
        rows='<p>来源已变更，当前核对结果不可用。</p>'
    return ('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>设计气象来源核对</title>'
        '<style>body{font:15px/1.7 system-ui;max-width:1000px;margin:32px auto;padding:20px}table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:8px}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style>'
        '<h1>设计气象来源核对</h1><p>声明字段一致不等于来源权威、规范适用或工程设计认证。报告是生成时快照，后续使用须重新核验。</p>'+rows+
        '<details><summary>输入、原件哈希及版本</summary><pre>'+html.escape(json.dumps(record,ensure_ascii=False,indent=2))+'</pre></details></html>')


def register(app,domain):
    from fastapi import Request
    service=DesignConditions(domain)

    @app.post('/api/projects/{project_id}/design-sources',status_code=201)
    def source_create(project_id:str,body:SourceInput,request:Request):
        return service.save_source(project_id,body,request.state.user['id'])

    @app.get('/api/projects/{project_id}/design-sources')
    def source_list(project_id:str):
        return service.catalog(project_id)

    @app.get('/api/projects/{project_id}/design-sources/{source_id}')
    def source_get(project_id:str,source_id:str):
        return service.source(project_id,source_id)

    @app.post('/api/projects/{project_id}/design-sources/{source_id}/review')
    def source_review(project_id:str,source_id:str,body:Review,request:Request):
        return service.review(project_id,source_id,body,request.state.user['id'])

    @app.get('/api/projects/{project_id}/design-models/{evidence_id}')
    def model_get(project_id:str,evidence_id:str):
        return service.model(project_id,evidence_id)

    @app.post('/api/projects/{project_id}/design-checks',status_code=201)
    def check_create(project_id:str,body:CheckInput,request:Request):
        return service.check(project_id,body,request.state.user['id'])

    @app.get('/api/projects/{project_id}/design-checks')
    def check_list(project_id:str):
        rows=[]
        for r in domain.store.list('designcheck',project_id):
            current=service.view(project_id,r['designcheck_id'])
            rows.append({k:current[k] for k in ('designcheck_id','created_at','status','stale_reasons','input')})
        return rows

    @app.get('/api/projects/{project_id}/design-checks/{check_id}')
    def check_get(project_id:str,check_id:str):
        return service.view(project_id,check_id)

    @app.get('/api/projects/{project_id}/design-checks/{check_id}/report.html',response_class=HTMLResponse)
    def check_report(project_id:str,check_id:str):
        return report(service.view(project_id,check_id))
