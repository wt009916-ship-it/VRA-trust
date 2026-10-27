"""Building workbench, public tool contracts and developer diagnostics."""
import json
from typing import Literal
from fastapi import HTTPException, Request
from fastapi.responses import Response
from pydantic import Field
from . import core, model_export
from .api_tokens import TokenCreate
from .model_schema import ImportOptions, ModelDraft, PublishModel
from .modeling import Modeling
from .schema import Contract, RunCreate

class ModelRun(Contract):
    scheme_id: Literal['baseline', 'R1', 'R2'] = 'baseline'
    factor_profile_id: str = 'none'

class ModelRevision(Contract):
    revision: int = Field(ge=1)

class EquipmentImport(Contract):
    file_id: str

def register_product(app, domain, auth):
    modeling = Modeling(domain, app.state.gateway)
    domain.modeling = app.state.modeling = modeling

    @app.get('/api/projects/{project_id}/model/equipment-template.csv')
    def equipment_template(project_id: str):
        from .equipment_inputs import COLUMNS
        return Response(','.join(COLUMNS) + '\r\n', media_type='text/csv', headers={'Content-Disposition': 'attachment; filename="pthp-nameplates-W-m3s.csv"'})

    @app.post('/api/projects/{project_id}/model/equipment-import')
    def equipment_import(project_id: str, body: EquipmentImport):
        from .equipment_inputs import read_csv
        record, path = domain.file_record(project_id, body.file_id)
        return read_csv(record, path)

    @app.get('/api/projects/{project_id}/model')
    def model(project_id: str):
        return modeling.get(project_id)

    @app.put('/api/projects/{project_id}/model')
    def save_model(project_id: str, body: ModelDraft, request: Request):
        return modeling.save(project_id, body, request.state.user['display_name'])

    @app.get('/api/projects/{project_id}/model/history')
    def model_history(project_id: str):
        return modeling.history(project_id)

    @app.get('/api/projects/{project_id}/model/validate')
    def validate_model(project_id: str):
        return modeling.validate(project_id)

    @app.post('/api/projects/{project_id}/model/sync-area')
    def sync_area(project_id: str, body: ModelRevision):
        return modeling.sync_area(project_id, body.revision)

    @app.post('/api/projects/{project_id}/model/publish')
    def publish_model(project_id: str, body: PublishModel):
        return modeling.publish(project_id, body)

    @app.get('/api/projects/{project_id}/model/export.ifc')
    def export_ifc(project_id: str):
        model = modeling.get(project_id)
        if not model:
            raise core.ValidationError('尚无模型')
        return Response(model_export.ifc(model), media_type='application/x-step', headers={'Content-Disposition': f'''attachment; filename="building-v{model['revision']}.ifc"'''})

    @app.get('/api/projects/{project_id}/model/geometry.hbjson')
    def export_hbjson(project_id: str):
        from .honeybee_bridge import geometry_model
        model = modeling.get(project_id)
        if not model:
            raise core.ValidationError('尚无模型')
        hb = geometry_model(model, model_export.geometry(model))
        return Response(json.dumps(hb.to_dict(), ensure_ascii=False), media_type='application/json', headers={'Content-Disposition': f'''attachment; filename="geometry-v{model['revision']}.hbjson"'''})

    @app.get('/api/projects/{project_id}/files/{file_id}/plan-preview')
    def plan_preview(project_id: str, file_id: str, page: int=1):
        from .document_reader import preview
        from pathlib import Path
        record, path = domain.file_record(project_id, file_id)
        if Path(record['name']).suffix.lower() not in {'.pdf', '.png', '.jpg', '.jpeg'} or not 1 <= page <= 500:
            raise core.ValidationError('仅支持有效 PDF/图片图页')
        return Response(preview(path, page), media_type='image/png', headers={'Cache-Control': 'no-store'})

    @app.get('/api/projects/{project_id}/model/export.idf')
    def export_idf(project_id: str):
        model = modeling.get(project_id)
        if not model or not modeling.validate(project_id)['can_publish']:
            raise core.ValidationError('模型未通过发布检查')
        text, _ = model_export.idf(model)
        return Response(text, media_type='text/plain', headers={'Content-Disposition': f'''attachment; filename="building-v{model['revision']}.idf"'''})

    @app.get('/api/projects/{project_id}/files/{file_id}/ifc-storeys')
    def ifc_storeys(project_id: str, file_id: str):
        import ifcopenshell
        from .model_import import storey_inventory
        _, path = domain.file_record(project_id, file_id)
        if path.suffix.lower() != '.ifc':
            raise core.ValidationError('请先选择 IFC 文件')
        return storey_inventory(ifcopenshell.open(str(path)))

    @app.post('/api/projects/{project_id}/imports', status_code=201)
    def import_source(project_id: str, body: ImportOptions, request: Request):
        return modeling.start_import(project_id, body, request.state.user['display_name'])

    @app.get('/api/projects/{project_id}/imports')
    def imports(project_id: str):
        return domain.store.list('import', project_id)

    @app.get('/api/projects/{project_id}/imports/{import_id}/report.json')
    def import_report(project_id: str, import_id: str):
        record = domain.store.get('import', import_id)
        if record['project_id'] != project_id:
            raise HTTPException(404)
        try:
            domain.file_record(project_id, record['options']['file_id'])
            source_check = {'valid': True}
        except (core.ValidationError, KeyError, OSError) as exc:
            source_check = {'valid': False, 'error': str(exc)}
        report = {'report_version': 1, 'import': record, 'current_source_check': source_check, 'scope': '导入诊断，不构成建筑性能或完整工程模型验收'}
        return Response(json.dumps(report, ensure_ascii=False, indent=2), media_type='application/json', headers={'Content-Disposition': f'attachment; filename="{import_id}-diagnostics.json"'})

    @app.post('/api/projects/{project_id}/imports/{import_id}/review')
    def import_review(project_id: str, import_id: str, body: ModelDraft, request: Request):
        return modeling.resume(project_id, import_id, body, request.state.user['display_name'])

    @app.post('/api/projects/{project_id}/model-runs', status_code=202)
    def model_run(project_id: str, body: ModelRun):
        return domain.submit(RunCreate(project_id=project_id, **body.model_dump()))

    @app.post('/api/projects/{project_id}/runs/{run_id}/cancel')
    def cancel_run(project_id: str, run_id: str):
        job = domain.store.job(run_id)
        if job['project_id'] != project_id:
            raise HTTPException(404)
        with domain.store.connect() as con:
            result = con.execute("UPDATE jobs SET state='failed',error='Cancelled before execution' WHERE id=? AND state='queued'", (run_id,))
            if result.rowcount != 1:
                raise core.ValidationError('仅可取消尚未开始的任务；已执行任务保留其计算记录')
        return {'run_id': run_id, 'cancelled': True}

    @app.get('/api/projects/{project_id}/tokens')
    def tokens(project_id: str, request: Request):
        return app.state.tokens.list(project_id, request.state.user['id'])

    @app.post('/api/projects/{project_id}/tokens', status_code=201)
    def create_token(project_id: str, body: TokenCreate, request: Request):
        return app.state.tokens.create(project_id, request.state.user['id'], body)

    @app.delete('/api/projects/{project_id}/tokens/{token_id}')
    def revoke_token(project_id: str, token_id: str, request: Request):
        return app.state.tokens.revoke(project_id, request.state.user['id'], token_id)
