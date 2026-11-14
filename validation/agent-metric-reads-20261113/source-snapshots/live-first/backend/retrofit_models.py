"""Reviewed material scenarios generate immutable IDF derivatives, never originals."""
import hashlib
import html
import json
from pathlib import Path
import threading
from typing import Annotated, Literal
from pydantic import Field, StrictBool, StrictFloat, model_validator
from fastapi.responses import FileResponse, HTMLResponse

from . import core, idf_retrofit
from .domain import identifier
from .runtime_lock import runtime_operation
from .schema import Contract, Evidence, EvidenceCreate, ComparisonRequest
from .thermal import Thermal

_capacity=threading.BoundedSemaphore(1)


class Properties(Contract):
    density_kg_m3: StrictFloat = Field(gt=0,le=30000)
    specific_heat_j_kg_k: StrictFloat = Field(ge=100,le=100000)
    roughness: Literal['VeryRough','Rough','MediumRough','MediumSmooth','Smooth','VerySmooth']
    thermal_absorptance: StrictFloat = Field(gt=0,le=.99999)
    solar_absorptance: StrictFloat = Field(ge=0,le=1)
    visible_absorptance: StrictFloat = Field(ge=0,le=1)
    property_source: str = Field(min_length=10,max_length=2000)


class Assignment(Contract):
    thermal_id: str = Field(pattern=r'^thermal_[a-f0-9]{32}$')
    surface_names: list[Annotated[str,Field(min_length=1,max_length=2000)]] = Field(min_length=1,max_length=1000)
    layer_order: Literal['outside_to_inside','inside_to_outside']
    properties: list[Properties] = Field(min_length=1,max_length=10)


class ModelPlan(Contract):
    name: str = Field(min_length=1,max_length=160)
    source_evidence_id: str = Field(pattern=r'^evidence_[a-f0-9]{32}$')
    scheme_id: Literal['R1','R2']
    assignments: list[Assignment] = Field(min_length=1,max_length=20)
    responsible_person: str = Field(min_length=1,max_length=100)
    basis: str = Field(min_length=10,max_length=2000)

    @model_validator(mode='after')
    def unique_surfaces(self):
        names=[n.casefold() for a in self.assignments for n in a.surface_names]
        if len(names)>1000 or len(names)!=len(set(names)):
            raise ValueError('Select at most 1000 distinct surfaces, each assigned once')
        return self


class Generate(ModelPlan):
    expected_preview_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    acknowledge_scope: StrictBool

    @model_validator(mode='after')
    def acknowledged(self):
        if not self.acknowledge_scope:raise ValueError('Explicit confirmation of mapping and scenario limits is required')
        return self


def version():
    return core.hash_json({'service':core.sha(Path(__file__)),'writer':core.sha(Path(idf_retrofit.__file__))})


class Retrofits:
    def __init__(self,domain):
        self.domain,self.store=domain,domain.store
        self.thermal=Thermal(domain)

    def source(self,pid,eid):
        evidence=self.store.get('evidence',eid)
        if (evidence['project_id']!=pid or evidence['type']!='idf' or evidence['scheme_id']!='baseline'
            or evidence['review_state']!='confirmed' or evidence['status'] in {'MISSING','AI_INFERRED'}):
            raise core.ValidationError('Select a current confirmed baseline IDF from this project')
        file,path=self.domain.file_record(pid,evidence['source_file'])
        if path.suffix.lower()!='.idf' or evidence['hash']!=file['hash']:
            raise core.ValidationError('Baseline IDF evidence/file mismatch')
        if any(r['derived_file']['file_id']==file['file_id'] for r in self.store.list('retrofit',pid)):
            raise core.ValidationError('Chained model derivations are not supported; use the original baseline')
        if file['size']>idf_retrofit.MAX_BYTES:raise core.ValidationError('Baseline IDF exceeds 2 MiB')
        raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=file['hash']:raise core.ValidationError('Baseline changed during reading')
        return evidence,file,raw

    def catalog(self,pid,eid):
        evidence,file,raw=self.source(pid,eid)
        model=idf_retrofit.inspect(raw)
        return {'source_evidence':evidence,'source_file':file,'surfaces':model['catalog'],
                'limitations':limits(),'builder_version':version()}

    def prepare(self,pid,body):
        project=self.store.get('project',pid)
        evidence,file,raw=self.source(pid,body.source_evidence_id)
        thermal=[self.thermal.view(pid,a.thermal_id) for a in body.assignments]
        if any(r['status']!='calculated' for r in thermal):
            raise core.ValidationError('Thermal inputs must be current and complete; no guessed properties')
        bindings=[{'thermal_id':r['thermal_id'],'hash':r['hash'],'source_status':r['source_status']} for r in thermal]
        dependencies={'project_revision':project['revision'],'source_evidence':evidence,'source_file':file,
                      'thermal_bindings':bindings,'builder_version':version()}
        request=body.model_dump()
        namespace=core.hash_json({'project_id':pid,'input':request,'dependencies':dependencies})[:20]
        data,changes=idf_retrofit.derive(raw,body.assignments,thermal,namespace)
        preview={'project_id':pid,'input':request,'dependencies':dependencies,'changes':changes,
                 'limitations':limits(),'source_nature':'USER_DECLARED_RETROFIT_SCENARIO',
                 'simulation_executed':False,'annual_saving_rate_pct':None}
        preview['preview_hash']=core.hash_json(preview)
        return preview,data

    @runtime_operation
    def generate(self,pid,body):
        if not _capacity.acquire(False):raise core.ValidationError('Model generation busy; retry later')
        try:
            plan=ModelPlan.model_validate(body.model_dump(exclude={'expected_preview_hash','acknowledge_scope'}))
            preview,data=self.prepare(pid,plan)
            if preview['preview_hash']!=body.expected_preview_hash:
                raise core.ValidationError('Preview or sources changed; inspect a fresh preview before generation')
            for previous in self.store.list('retrofit',pid):
                if previous['preview_hash']==preview['preview_hash']:
                    current=self.view(pid,previous['retrofit_id'])
                    if current['status']!='generated':raise core.ValidationError('Existing identical derivation is no longer current')
                    return current
            if len(self.store.list('retrofit',pid))>=20:raise core.ValidationError('Project model derivation limit is 20')
            with self.domain.storage.import_batch(pid,[(body.scheme_id+'-material-scenario.idf',data)]) as (con,files):
                # Revalidate under the same serialized DB write transaction as
                # the file, pending evidence and derivation record insertion.
                check,_=self.prepare(pid,plan)
                if check['preview_hash']!=preview['preview_hash']:
                    raise core.ValidationError('Sources changed during model generation')
                rows=con.execute("SELECT body FROM records r WHERE kind='evidence' AND project_id=? AND revision=(SELECT MAX(revision) FROM records x WHERE x.kind=r.kind AND x.id=r.id)",(pid,)).fetchall()
                if any((e:=json.loads(row[0]))['type']=='idf' and e['scheme_id']==body.scheme_id and e['review_state']!='rejected' for row in rows):
                    raise core.ValidationError('Target scheme already has model evidence; explicitly reject the superseded model first')
                file=files[0]
                draft=EvidenceCreate(type='idf',name=body.name,source_file=file['file_id'],source_locator='Derived IDF; exact reference edits in model derivation record',
                    authority='User-declared material retrofit scenario',permission=preview['dependencies']['source_evidence']['permission'],
                    uncertainty='Not measured construction; thermal films are not material layers; generated model requires review and native simulation',
                    acquisition_method='Explicit surface mapping and immutable IDF derivation',responsible_person=body.responsible_person,
                    status='ASSUMED',scheme_id=body.scheme_id)
                ev=Evidence(**draft.model_dump(),evidence_id=identifier('evidence'),project_id=pid,revision=1,timestamp=core.now(),hash=file['hash']).model_dump(mode='json')
                ev=self.store.put_in(con,'evidence',ev)
                obj={'retrofit_id':identifier('retrofit'),'project_id':pid,'created_at':core.now(),
                     'preview_hash':preview['preview_hash'],'input':plan.model_dump(),'dependencies':preview['dependencies'],
                     'changes':preview['changes'],'derived_file':file,'derived_evidence_id':ev['evidence_id'],
                     'limitations':limits(),'source_nature':'USER_DECLARED_RETROFIT_SCENARIO'}
                obj['hash']=core.hash_json(obj);self.store.put_in(con,'retrofit',obj)
            return self.view(pid,obj['retrofit_id'])
        finally:_capacity.release()

    def record(self,pid,rid):
        obj=self.store.get('retrofit',rid)
        if obj['project_id']!=pid:raise core.ValidationError('Cross-project model derivation rejected')
        if core.hash_json({k:v for k,v in obj.items() if k not in {'hash','revision'}})!=obj['hash']:
            raise core.ValidationError('Model derivation integrity failed')
        return obj

    def view(self,pid,rid):
        obj=self.record(pid,rid);reasons=[];deps=obj['dependencies']
        if version()!=deps['builder_version']:reasons.append('builder_changed')
        if self.store.get('project',pid)['revision']!=deps['project_revision']:reasons.append('project_changed')
        try:
            evidence,file,_=self.source(pid,deps['source_evidence']['evidence_id'])
            if (evidence['revision'],evidence['hash'],file['hash'])!=(deps['source_evidence']['revision'],deps['source_evidence']['hash'],deps['source_file']['hash']):
                reasons.append('baseline_binding_changed')
        except (OSError,ValueError,KeyError):reasons.append('baseline_unavailable')
        for old in deps['thermal_bindings']:
            try:
                current=self.thermal.view(pid,old['thermal_id'])
                if current['status']!='calculated' or current['hash']!=old['hash']:reasons.append('thermal_source_changed')
            except (OSError,ValueError,KeyError):reasons.append('thermal_source_unavailable')
        try:
            file,_=self.domain.file_record(pid,obj['derived_file']['file_id'])
            if file['hash']!=obj['derived_file']['hash']:reasons.append('derived_file_changed')
            ev=self.store.get('evidence',obj['derived_evidence_id'])
            if (ev['project_id'],ev['type'],ev['source_file'],ev['scheme_id'],ev['hash'])!=(pid,'idf',file['file_id'],obj['input']['scheme_id'],file['hash']):
                reasons.append('derived_evidence_changed')
        except (OSError,ValueError,KeyError):reasons.append('derived_file_unavailable');ev=None
        status='stale' if reasons else 'rejected' if ev and ev['review_state']=='rejected' else 'generated'
        return {**obj,'status':status,'stale_reasons':sorted(set(reasons)),
                'changes':obj['changes'] if status=='generated' else None,'evidence_review':ev,
                'simulation_executed':False,'annual_saving_rate_pct':None}

    def require_file_current(self,pid,fid):
        for row in self.store.list('retrofit',pid):
            if row['derived_file']['file_id']==fid and self.view(pid,row['retrofit_id'])['status']!='generated':
                raise core.ValidationError('Derived model sources are stale or rejected; create a new reviewed derivation')

    def download(self,pid,rid):
        record=self.view(pid,rid)
        if record['status']!='generated':raise core.ValidationError('Derived model is not current')
        return self.domain.file_record(pid,record['derived_file']['file_id'])[1]

    def compare(self,pid,rid,body):
        record=self.view(pid,rid)
        if record['status']!='generated':raise core.ValidationError('Model derivation is not current')
        if len(body.run_ids)!=2:raise core.ValidationError('Select exactly one baseline and one derived-model run')
        jobs=[self.store.job(r) for r in body.run_ids]
        expected={'baseline':record['dependencies']['source_file']['file_id'],record['input']['scheme_id']:record['derived_file']['file_id']}
        if (len({j['scheme_id'] for j in jobs})!=2 or any(j['project_id']!=pid or j['scheme_id'] not in expected
            or j['evidence_snapshot']['idf']['source_file']!=expected[j['scheme_id']] for j in jobs)):
            raise core.ValidationError('Runs must use exactly the bound baseline and derived IDF files')
        return {'retrofit_id':rid,'source_hash':record['hash'],'comparison':self.domain.compare(body.run_ids),
                'thermal_u_is_not_annual_saving_rate':True,'limitations':limits()}


def limits():
    return ['仅明确选择的室外围护表面和普通材料构造；窗、地接触、可动保温、特殊材性与动态构造控制未自动改模。',
            '密度、比热、吸收率及层序为用户明确声明；不自动证明结构、耐火、含湿或耐久功能等效。',
            '仅写入材料厚度及修正后导热系数；Rsi/Rse不作为材料层，EnergyPlus自行计算表面对流和辐射。',
            '生成IDF不等于引擎运行成功；薄层、高导热等参数仍可能被原生引擎拒绝。',
            '全年节能率只能来自相同天气、引擎、项目和有效基准的实际运行比较；不能用U下降比例替代。']


def report(record):
    esc=lambda x:html.escape(str(x))
    changes=record['changes']
    rows='' if changes is None else ''.join('<tr><td>'+esc(r['surface_name'])+'</td><td>'+esc(r['old_construction'])+'</td><td>'+esc(r['new_construction'])+'</td></tr>' for r in changes['changes'])
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>材料方案派生模型</title><style>body{font-family:system-ui;max-width:1000px;margin:32px auto;padding:20px}td,th{border:1px solid #bbb;padding:8px}table{border-collapse:collapse}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style><h1>'+esc(record['input']['name'])+'</h1><p>状态：'+esc(record['status'])+'；用户声明改造情景，未经工程适用性认证。</p>'+('<p>来源失效，变更结果已撤下。</p>' if changes is None else '<table><tr><th>表面</th><th>原构造</th><th>派生构造</th></tr>'+rows+'</table>')+'<ul>'+''.join('<li>'+esc(t)+'</li>' for t in record['limitations'])+'</ul><p>原模型SHA256：'+esc(record['dependencies']['source_file']['hash'])+'</p><p>派生模型SHA256：'+esc(record['derived_file']['hash'])+'</p><details><summary>声明材性、层序、来源与复核信息</summary><pre>'+esc(json.dumps({'input':record['input'],'dependencies':record['dependencies'],'evidence_review':record['evidence_review']},ensure_ascii=False,indent=2))+'</pre></details></html>'


def register(app,domain):
    service=Retrofits(domain)
    @app.get('/api/projects/{project_id}/retrofit-models')
    def sources(project_id: str):
        return [{'evidence_id':e['evidence_id'],'name':e['name'],'review_state':e['review_state'],'hash':e['hash']} for e in domain.store.list('evidence',project_id) if e['type']=='idf' and e['scheme_id']=='baseline' and e['review_state']=='confirmed']
    @app.get('/api/projects/{project_id}/retrofit-models/{evidence_id}')
    def catalog(project_id: str,evidence_id: str):return service.catalog(project_id,evidence_id)
    @app.post('/api/projects/{project_id}/retrofit-previews')
    def preview(project_id: str,body: ModelPlan):return service.prepare(project_id,body)[0]
    @app.post('/api/projects/{project_id}/retrofits',status_code=201)
    def create(project_id: str,body: Generate):return service.generate(project_id,body)
    @app.get('/api/projects/{project_id}/retrofits')
    def listing(project_id: str):return [service.view(project_id,r['retrofit_id']) for r in domain.store.list('retrofit',project_id)]
    @app.get('/api/projects/{project_id}/retrofits/{retrofit_id}')
    def get(project_id: str,retrofit_id: str):return service.view(project_id,retrofit_id)
    @app.get('/api/projects/{project_id}/retrofits/{retrofit_id}/model.idf')
    def download(project_id: str,retrofit_id: str):return FileResponse(service.download(project_id,retrofit_id),media_type='text/plain',filename='derived-material-scenario.idf')
    @app.get('/api/projects/{project_id}/retrofits/{retrofit_id}/report.html')
    def html_report(project_id: str,retrofit_id: str):return HTMLResponse(report(service.view(project_id,retrofit_id)))
    @app.post('/api/projects/{project_id}/retrofits/{retrofit_id}/comparison')
    def compare(project_id: str,retrofit_id: str,body: ComparisonRequest):return service.compare(project_id,retrofit_id,body)
