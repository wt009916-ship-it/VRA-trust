"""Immutable model-layer takeoffs, bound to current source and geometry rules."""
import html
import json
from pathlib import Path

from fastapi.responses import HTMLResponse
from pydantic import Field, StrictInt

from . import core, parser_runtime
from .cad import parser_version
from .domain import identifier
from .schema import Contract


class LayerRequest(Contract):
    cad_id: str = Field(pattern=r'^cad_[a-f0-9]{32}$')
    product_id: StrictInt = Field(gt=0,le=2147483647)


def calculator_version():
    return core.hash_json({name:core.sha(Path(__file__).with_name(name)) for name in
                          ['material_takeoff.py','ifc_layer_quantities.py','ifc_geometry.py','ifc_details.py']})


class LayerTakeoffs:
    def __init__(self,cad):
        self.cad,self.domain,self.store=cad,cad.domain,cad.store

    def create(self,pid,body):
        source=self.cad.view(pid,body.cad_id)
        if source['status']!='parsed' or source['result']['format']!='IFC':
            raise core.ValidationError('A current IFC inspection is required')
        if body.product_id not in {r['id'] for r in source['result']['objects']}:
            raise core.ValidationError('Product is not in the selected IFC inspection')
        if not self.cad.capacity.acquire(False):
            raise core.ValidationError('File parsers busy; retry later')
        try:
            _,path=self.domain.file_record(pid,source['source']['file_id'])
            before,calc=parser_version(),calculator_version()
            with parser_runtime.run('cad',path,options={'operation':'ifc_layers','product_id':body.product_id}) as scope:
                output=scope['work']/'result.json'
                if not output.exists() or output.stat().st_size>8*1024**2:
                    raise core.ValidationError('Layer takeoff output unavailable')
                result=core.read_json(output)
                if 'error' in result:raise core.ValidationError('Layer takeoff rejected; original preserved')
                result['resource_limits']=scope['resource_limits']
            current=self.cad.view(pid,body.cad_id)
            if current['status']!='parsed' or current['hash']!=source['hash'] or before!=parser_version() or calc!=calculator_version():
                raise core.ValidationError('Layer takeoff source changed during calculation')
            obj={'takeoff_id':identifier('takeoff'),'project_id':pid,'cad_id':body.cad_id,
                 'product_id':body.product_id,'inspection_hash':source['hash'],'parser_hash':before,
                 'calculator_hash':calc,'source':source['source'],'result':result,'created_at':core.now()}
            obj['hash']=core.hash_json(obj);self.store.put('takeoff',obj)
            return self.view(pid,obj['takeoff_id'])
        finally:
            self.cad.capacity.release()

    def view(self,pid,ident):
        obj=self.store.get('takeoff',ident)
        if obj['project_id']!=pid:raise core.ValidationError('Cross-project takeoff rejected')
        if core.hash_json({k:v for k,v in obj.items() if k not in {'hash','revision'}})!=obj['hash']:
            raise core.ValidationError('Layer takeoff integrity failed')
        stale=obj['calculator_hash']!=calculator_version()
        try:
            current=self.cad.view(pid,obj['cad_id'])
            stale|=current['status']!='parsed' or current['hash']!=obj['inspection_hash'] or obj['parser_hash']!=parser_version()
        except (OSError,ValueError,KeyError):stale=True
        return {**obj,'status':'stale' if stale else obj['result']['status'],'result':None if stale else obj['result'],
                'assessment':'MODEL_LAYER_ENVELOPE_NOT_PURCHASE_QUANTITY'}


def report(record):
    esc=lambda x:html.escape(str(x))
    rows=(record.get('result') or {}).get('layers',[])
    table=''.join('<tr>'+''.join('<td>'+esc(v)+'</td>' for v in [r['layer_id'],r['material_name'],
            r['thickness_m'],r['envelope_volume_m3']])+'</tr>' for r in rows)
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>构件分层计量</title><body><h1>模型材料层包络体积</h1><p>当前状态：'+esc(record['status'])+'</p><p>已扣除模型洞口；不是采购材料净量。空腔、龙骨等层的实体比例及计量规则需另有依据。</p><table><tr><th>层编号</th><th>材料声明</th><th>厚度 m</th><th>包络体积 m³</th></tr>'+table+'</table><h2>来源与计算回执</h2><pre style="white-space:pre-wrap;overflow-wrap:anywhere">'+esc(json.dumps(record,ensure_ascii=False,indent=2))+'</pre></body></html>'


def register(app,cad):
    service=LayerTakeoffs(cad);app.state.layer_takeoffs=service
    from .material_scenarios import register as register_scenarios
    register_scenarios(app, service)
    from .material_collection_service import register as register_collections
    register_collections(app, cad)

    @app.post('/api/projects/{project_id}/ifc-layer-takeoffs',status_code=201)
    def create(project_id:str,body:LayerRequest):return service.create(project_id,body)

    @app.get('/api/projects/{project_id}/ifc-layer-takeoffs/{takeoff_id}')
    def current(project_id:str,takeoff_id:str):return service.view(project_id,takeoff_id)

    @app.get('/api/projects/{project_id}/ifc-layer-takeoffs/{takeoff_id}/report.html',response_class=HTMLResponse)
    def html_report(project_id:str,takeoff_id:str):return report(service.view(project_id,takeoff_id))
