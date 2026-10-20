"""Building workbench, public tool contracts and developer diagnostics."""
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

def register_product(app, domain, auth):
    modeling = Modeling(domain, app.state.gateway)
    domain.modeling = app.state.modeling = modeling

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

    @app.get('/api/projects/{project_id}/model/export.idf')
    def export_idf(project_id: str):
        model = modeling.get(project_id)
        if not model or not modeling.validate(project_id)['can_publish']:
            raise core.ValidationError('模型未通过发布检查')
        text, _ = model_export.idf(model)
        return Response(text, media_type='text/plain', headers={'Content-Disposition': f'''attachment; filename="building-v{model['revision']}.idf"'''})

    @app.post('/api/projects/{project_id}/imports', status_code=201)
    def import_source(project_id: str, body: ImportOptions, request: Request):
        return modeling.start_import(project_id, body, request.state.user['display_name'])

    @app.get('/api/projects/{project_id}/imports')
    def imports(project_id: str):
        return domain.store.list('import', project_id)

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
