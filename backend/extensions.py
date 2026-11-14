"""Project-scoped trust and Agent endpoints, protected by the main API boundary."""
import json
import zipfile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi import HTTPException, Request, Query
from .agent import Agent, Chat, TOOLS
from . import agent_outputs
from .gateway import Gateway, ProviderSettings
from .local_model import LocalModelSettings
from .trust import FactorUpdate, FactorReview, Trust
from .robustness import Robustness, Search, Actions
from .spatial import Spatial, Reconstruction
from .thermal import Thermal, Assembly, ThermalCompare, compare as compare_thermal, render_html as thermal_html
from .cad import Cad, Inspection, CurrentStates
from .cad_union import IfcUnions, UnionRequest, union_report
from .lifecycle import Lifecycle, Inventory, Comparison as LifecycleComparison, compare as lifecycle_compare, report as lifecycle_report
from .standards import Standards, StandardInput, Preview as StandardPreview, Review as StandardReview, Query as StandardQuery
from .engineering import Engineering, BeamInput, report as engineering_report
from .material_cost import Costs, Estimate, Comparison as CostComparison, compare as cost_compare, report as cost_report
from .construction import Schedules, ScheduleInput, report as schedule_report
from .operations import Operations, AnalysisInput, report as operations_report
from .drawings import Drawings, DrawingInput, DrawingReview
from .drawing_scale import DrawingScales, ScaleInput, LengthInput

def register_extensions(app, domain, auth):
    trust, gateway = (Trust(domain), Gateway(domain.store))
    agent = Agent(domain, gateway)
    app.state.agent, app.state.gateway = (agent, gateway)
    robustness, spatial = (Robustness(domain), Spatial(domain))
    app.state.robustness = robustness
    domain.robustness = robustness
    thermal = Thermal(domain)
    from .thermal_bridge_routes import register as register_thermal_bridge
    register_thermal_bridge(app, domain)
    from .ideal_loads import register_diagnostics
    register_diagnostics(app, domain)
    from .timestep_studies import register as register_timestep_studies
    register_timestep_studies(app,domain)
    from .end_use_records import register as register_end_use
    register_end_use(app,domain)
    from .utility_records import register as register_utility
    register_utility(app,domain)
    from .retrofit_models import register as register_retrofit_models
    register_retrofit_models(app,domain)
    cad = Cad(domain)
    from .ifc_beam_handoff import register as register_ifc_beam_handoff
    register_ifc_beam_handoff(app, cad)
    from .material_takeoff import register as register_material_takeoff
    register_material_takeoff(app, cad)
    lifecycle = Lifecycle(domain)
    standards = Standards(domain)
    from .standard_ocr import register as register_standard_ocr
    register_standard_ocr(app, domain)
    engineering = Engineering(domain)
    costs = Costs(domain)
    schedules = Schedules(domain)
    operations = Operations(domain)
    from .maintenance import register as register_maintenance
    register_maintenance(app, domain)
    drawings = Drawings(domain)
    drawing_scales = DrawingScales(drawings)
    from .drawing_associations import register as register_drawing_associations
    register_drawing_associations(app, drawings)
    from .design_conditions import register as register_design_conditions
    register_design_conditions(app, domain)

    @app.post('/api/projects/{project_id}/drawings', status_code=201)
    def drawing_create(project_id: str, body: DrawingInput):
        return drawings.save(project_id,body)

    @app.get('/api/projects/{project_id}/drawings')
    def drawing_list(project_id: str):
        return [{k:r[k] for k in ('drawing_id','source','created_at','revision')}|{'page':r['input']['page']} for r in domain.store.list('drawing',project_id)]

    @app.get('/api/projects/{project_id}/drawings/{drawing_id}')
    def drawing_get(project_id: str, drawing_id: str):
        return drawings.view(project_id,drawing_id)

    @app.get('/api/projects/{project_id}/drawings/{drawing_id}/preview.png')
    def drawing_preview(project_id: str, drawing_id: str):
        return FileResponse(drawings.preview(project_id,drawing_id),media_type='image/png',headers={'X-Content-Type-Options':'nosniff'})

    @app.post('/api/projects/{project_id}/drawings/{drawing_id}/review')
    def drawing_review(project_id: str, drawing_id: str, body: DrawingReview, request: Request):
        return drawings.review(project_id,drawing_id,body,request.state.user['id'])

    @app.get('/api/projects/{project_id}/drawings/{drawing_id}/history')
    def drawing_history(project_id: str, drawing_id: str):
        return drawings.history(project_id,drawing_id)

    @app.get('/api/projects/{project_id}/drawings/{drawing_id}/derivatives/{name}')
    def drawing_derivative(project_id: str,drawing_id: str,name: str):
        return FileResponse(drawings.derivative(project_id,drawing_id,name),media_type='image/png',headers={'X-Content-Type-Options':'nosniff'})

    @app.post('/api/projects/{project_id}/drawings/{drawing_id}/scales',status_code=201)
    def drawing_scale_create(project_id: str,drawing_id: str,body: ScaleInput,request: Request):
        return drawing_scales.save(project_id,drawing_id,body,request.state.user['id'])

    @app.get('/api/projects/{project_id}/drawings/{drawing_id}/scales')
    def drawing_scale_list(project_id: str,drawing_id: str):
        drawings.view(project_id,drawing_id)
        return [drawing_scales.view(project_id,drawing_id,r['scale_id']) for r in domain.store.list('scale',project_id) if r['drawing_id']==drawing_id]

    @app.get('/api/projects/{project_id}/drawings/{drawing_id}/scales/{scale_id}')
    def drawing_scale_get(project_id: str,drawing_id: str,scale_id: str):
        return drawing_scales.view(project_id,drawing_id,scale_id)

    @app.post('/api/projects/{project_id}/drawings/{drawing_id}/scales/{scale_id}/measure')
    def drawing_measure(project_id: str,drawing_id: str,scale_id: str,body: LengthInput):
        return drawing_scales.measure(project_id,drawing_id,scale_id,body)

    @app.get('/api/projects/{project_id}/operation-inputs')
    def operations_inputs(project_id: str):
        return [{k:r[k] for k in ('file_id','name','size','hash')} for r in domain.store.list('file',project_id) if r['name'].lower().endswith('.csv')]

    @app.get('/api/projects/{project_id}/operation-inputs/{file_id}')
    def operations_preview(project_id: str, file_id: str):
        return operations.preview(project_id,file_id)

    @app.post('/api/projects/{project_id}/operations', status_code=201)
    def operations_create(project_id: str, body: AnalysisInput):
        return operations.save(project_id,body)

    @app.get('/api/projects/{project_id}/operations')
    def operations_list(project_id: str):
        return [operations.view(project_id,r['operation_id']) for r in domain.store.list('operation',project_id)]

    @app.get('/api/projects/{project_id}/operations/{operation_id}')
    def operations_get(project_id: str, operation_id: str):
        return operations.view(project_id,operation_id)

    @app.get('/api/projects/{project_id}/operations/{operation_id}/report.html', response_class=HTMLResponse)
    def operations_html(project_id: str, operation_id: str):
        return operations_report(operations.view(project_id,operation_id))

    @app.post('/api/projects/{project_id}/schedule-validation')
    def schedule_validation(project_id: str, body: ScheduleInput):
        return body.model_dump()

    @app.post('/api/projects/{project_id}/schedules', status_code=201)
    def schedule_create(project_id: str, body: ScheduleInput):
        return schedules.save(project_id,body)

    @app.get('/api/projects/{project_id}/schedules')
    def schedule_list(project_id: str):
        return [schedules.view(project_id,r['schedule_id']) for r in domain.store.list('schedule',project_id)]

    @app.get('/api/projects/{project_id}/schedules/{schedule_id}')
    def schedule_get(project_id: str, schedule_id: str):
        return schedules.view(project_id,schedule_id)

    @app.get('/api/projects/{project_id}/schedules/{schedule_id}/report.html', response_class=HTMLResponse)
    def schedule_html(project_id: str, schedule_id: str):
        return schedule_report(schedules.view(project_id,schedule_id))

    @app.post('/api/projects/{project_id}/material-cost-validation')
    def cost_validation(project_id: str, body: Estimate):
        return body.model_dump(mode='json')

    @app.post('/api/projects/{project_id}/material-costs', status_code=201)
    def cost_create(project_id: str, body: Estimate):
        return costs.save(project_id,body)

    @app.get('/api/projects/{project_id}/material-costs')
    def cost_list(project_id: str):
        return [costs.view(project_id,r['cost_id']) for r in domain.store.list('cost',project_id)]

    @app.get('/api/projects/{project_id}/material-costs/{cost_id}')
    def cost_get(project_id: str, cost_id: str):
        return costs.view(project_id,cost_id)

    @app.get('/api/projects/{project_id}/material-costs/{cost_id}/report.html', response_class=HTMLResponse)
    def cost_html(project_id: str, cost_id: str):
        return cost_report(costs.view(project_id,cost_id))

    @app.post('/api/projects/{project_id}/material-cost-comparisons')
    def cost_comparison(project_id: str, body: CostComparison):
        return cost_compare(costs,project_id,body)

    @app.post('/api/projects/{project_id}/beam-analyses', status_code=201)
    def beam_create(project_id: str, body: BeamInput):
        return engineering.save(project_id, body)

    @app.get('/api/projects/{project_id}/beam-analyses')
    def beam_list(project_id: str):
        return [engineering.view(project_id,r['engineering_id']) for r in domain.store.list('engineering',project_id)]

    @app.get('/api/projects/{project_id}/beam-analyses/{engineering_id}')
    def beam_get(project_id: str, engineering_id: str):
        return engineering.view(project_id,engineering_id)

    @app.get('/api/projects/{project_id}/beam-analyses/{engineering_id}/report.html', response_class=HTMLResponse)
    def beam_html(project_id: str, engineering_id: str):
        return engineering_report(engineering.view(project_id,engineering_id))

    @app.post('/api/projects/{project_id}/standards-preview')
    def standards_preview(project_id: str, body: StandardPreview):
        return standards.preview(project_id, body)

    @app.post('/api/projects/{project_id}/standards', status_code=201)
    def standards_create(project_id: str, body: StandardInput):
        return standards.save(project_id, body)

    @app.get('/api/projects/{project_id}/standards')
    def standards_list(project_id: str):
        return standards.catalog(project_id)

    @app.get('/api/projects/{project_id}/standards/{standard_id}')
    def standards_get(project_id: str, standard_id: str):
        return standards.view(project_id, standard_id)

    @app.get('/api/projects/{project_id}/standards/{standard_id}/source.pdf')
    def standards_source(project_id: str, standard_id: str):
        record = standards.view(project_id, standard_id)
        source, path = domain.file_record(project_id, record['input']['file_id'])
        return FileResponse(path, media_type='application/pdf', filename=source['name'],
            content_disposition_type='inline', headers={'X-Source-SHA256':source['hash']})

    @app.post('/api/projects/{project_id}/standards/{standard_id}/review')
    def standards_review(project_id: str, standard_id: str, body: StandardReview, request: Request):
        return standards.review(project_id, standard_id, body, request.state.user['id'])

    @app.post('/api/projects/{project_id}/standard-queries', status_code=201)
    def standards_query(project_id: str, body: StandardQuery):
        return standards.query(project_id, body)

    @app.get('/api/projects/{project_id}/standard-queries/{normquery_id}')
    def standards_query_get(project_id: str, normquery_id: str):
        return standards.query_view(project_id, normquery_id)

    @app.post('/api/projects/{project_id}/lifecycle-validation')
    def lifecycle_validation(project_id: str, body: Inventory):
        return body.model_dump()

    @app.post('/api/projects/{project_id}/lifecycle-comparisons')
    def lifecycle_comparison(project_id: str, body: LifecycleComparison):
        return lifecycle_compare(lifecycle, project_id, body)

    @app.post('/api/projects/{project_id}/lifecycle', status_code=201)
    def lifecycle_create(project_id: str, body: Inventory):
        return lifecycle.save(project_id, body)

    @app.get('/api/projects/{project_id}/lifecycle')
    def lifecycle_history(project_id: str):
        return [lifecycle.view(project_id, r['lifecycle_id']) for r in domain.store.list('lifecycle', project_id)]

    @app.get('/api/projects/{project_id}/lifecycle/{lifecycle_id}')
    def lifecycle_record(project_id: str, lifecycle_id: str):
        return lifecycle.view(project_id, lifecycle_id)

    @app.get('/api/projects/{project_id}/lifecycle/{lifecycle_id}/report.html', response_class=HTMLResponse)
    def lifecycle_html(project_id: str, lifecycle_id: str):
        return lifecycle_report(lifecycle.view(project_id, lifecycle_id))

    @app.get('/api/projects/{project_id}/dwg-capability')
    def dwg_capability(project_id: str):
        from . import dwg_runtime
        return {'available':dwg_runtime.current() is not None,'coverage':'partial_not_lossless',
                'platform':'windows','max_bytes':10*1024**2}

    @app.get('/api/projects/{project_id}/cad-inspections/{cad_id}/converted.dxf')
    def dwg_download(project_id: str, cad_id: str):
        from .dwg import download
        return FileResponse(download(cad,project_id,cad_id),media_type='application/dxf',
                            filename='converted-partial.dxf',headers={'X-Content-Type-Options':'nosniff'})

    @app.post('/api/projects/{project_id}/cad-current-states')
    def cad_current_states(project_id: str, body: CurrentStates):
        return cad.current_states(project_id, body)

    @app.post('/api/projects/{project_id}/cad-inspections', status_code=201)
    def inspect_cad(project_id: str, body: Inspection):
        return cad.inspect(project_id, body)

    @app.get('/api/projects/{project_id}/cad-inspections')
    def cad_history(project_id: str):
        return [cad.view(project_id, r['cad_id']) for r in domain.store.list('cad', project_id)]

    @app.get('/api/projects/{project_id}/cad-inspection-page')
    def cad_page(project_id: str, limit: int = Query(default=20, ge=1, le=20),
                 before: int | None = Query(default=None, ge=0, le=2**53-1),
                 snapshot: int | None = Query(default=None, ge=0, le=2**53-1)):
        from .cad_history import page
        return page(cad, project_id, limit=limit, before=before, snapshot=snapshot)

    @app.get('/api/projects/{project_id}/cad-inspections/{cad_id}')
    def cad_record(project_id: str, cad_id: str):
        return cad.view(project_id, cad_id)

    unions = IfcUnions(cad)

    @app.post('/api/projects/{project_id}/ifc-unions', status_code=201)
    def ifc_union_create(project_id: str, body: UnionRequest):
        return unions.create(project_id, body)

    @app.get('/api/projects/{project_id}/ifc-unions')
    def ifc_union_history(project_id: str):
        return [unions.view(project_id, row['union_id']) for row in domain.store.list('union', project_id)]

    @app.get('/api/projects/{project_id}/ifc-unions/{union_id}')
    def ifc_union_record(project_id: str, union_id: str):
        return unions.view(project_id, union_id)

    @app.get('/api/projects/{project_id}/ifc-unions/{union_id}/report.html', response_class=HTMLResponse)
    def ifc_union_html(project_id: str, union_id: str):
        return union_report(unions.view(project_id, union_id))

    @app.post('/api/projects/{project_id}/thermal', status_code=201)
    def thermal_create(project_id: str, body: Assembly):
        return thermal.save(project_id, body)

    @app.get('/api/projects/{project_id}/thermal')
    def thermal_list(project_id: str):
        return [thermal.view(project_id, r['thermal_id']) for r in domain.store.list('thermal', project_id)]

    @app.post('/api/projects/{project_id}/thermal-comparisons')
    def thermal_comparison(project_id: str, body: ThermalCompare):
        return compare_thermal(thermal, project_id, body)

    @app.get('/api/projects/{project_id}/thermal/{thermal_id}')
    def thermal_record(project_id: str, thermal_id: str):
        return thermal.view(project_id, thermal_id)

    @app.get('/api/projects/{project_id}/thermal/{thermal_id}/report.html', response_class=HTMLResponse)
    def thermal_report(project_id: str, thermal_id: str):
        return thermal_html(thermal.view(project_id, thermal_id))

    def developer(request):
        if not auth.is_admin(request.state.user['id']):
            raise HTTPException(403, '只有工作区管理员可以配置 Provider')

    @app.get('/api/developer/provider')
    def settings(request: Request):
        developer(request)
        return gateway.public()

    @app.put('/api/developer/provider')
    def configure(body: ProviderSettings, request: Request):
        developer(request)
        return gateway.save(body)

    @app.post('/api/developer/provider/test')
    def test_provider(request: Request):
        developer(request)
        answer = gateway.complete([{'role': 'user', 'content': '请调用 evidence_validate 工具检查资料。'}], agent.tools())
        calls = answer.get('tool_calls') or []
        # Connectivity check must not execute model-selected mutating tools.
        return {'connected': True, 'tool_calling_observed': any(c.get('function', {}).get('name') == 'evidence_validate' for c in calls),
                'model': gateway.public()['model'], 'tools_executed': 0}

    @app.get('/api/agent/status')
    def agent_status():
        config = gateway.public()
        local = agent.local_model.public()
        return {'provider_ready': config['enabled'] and config['key_configured'], 'model': config['model'],
                'local_model_ready': local['enabled'] and local['key_configured'], 'local_model': local['model'],
                'readiness_notice': '配置就绪不等于服务连通或能力验收通过', 'tools': agent.tools(),
                'output_catalog': agent_outputs.public_catalog(),
                'tool_catalog_scope':'default_read_only', 'installed_tool_names':sorted(TOOLS)}

    @app.get('/api/developer/local-model')
    def local_model_settings(request: Request):
        developer(request)
        return agent.local_model.public()

    @app.put('/api/developer/local-model')
    def configure_local_model(body: LocalModelSettings, request: Request):
        developer(request)
        return agent.local_model.save(body)

    @app.post('/api/developer/local-model/test')
    def test_local_model(request: Request):
        developer(request)
        from .agent import ProviderMessage
        answer = ProviderMessage.model_validate(agent.local_model.complete(
            [{'role': 'user', 'content': '请调用 evidence_validate 工具检查资料。'}], agent.tools()))
        return {'connected': True, 'tool_calling_observed': any(c.function.name == 'evidence_validate' for c in answer.tool_calls or []),
                'model': agent.local_model.public()['model'], 'tools_executed': 0, 'engineering_capability_verified': False}

    @app.post('/api/projects/{project_id}/agent/chat', status_code=202)
    def chat(project_id: str, body: Chat):
        return agent.start(project_id, body)

    @app.get('/api/projects/{project_id}/agent-tasks')
    def agent_history(project_id: str):
        return [{k: task.get(k) for k in ('agent_id', 'question', 'mode', 'objective', 'status', 'created_at', 'answer', 'previous_agent_id')}
                for task in (agent.view(project_id, row['agent_id']) for row in domain.store.list('agent', project_id)[:20])]

    @app.get('/api/projects/{project_id}/agent/{agent_id}')
    def agent_task(project_id: str, agent_id: str):
        task = domain.store.get('agent', agent_id)
        if task['project_id'] != project_id:
            raise HTTPException(404)
        return agent.view(project_id, agent_id)

    @app.get('/api/projects/{project_id}/carbon-factors')
    def factor(project_id: str):
        return trust.factor(project_id)

    @app.put('/api/projects/{project_id}/carbon-factors')
    def update_factor(project_id: str, body: FactorUpdate):
        return trust.update_factor(project_id, body)

    @app.get('/api/projects/{project_id}/carbon-factor-assurance')
    def factor_assurance(project_id: str):
        current = trust.factor(project_id)
        return trust.source_assurance(project_id, current['profile']) if current else {'status': 'NOT_REGISTERED'}

    @app.post('/api/projects/{project_id}/carbon-factor-reviews', status_code=201)
    def review_factor(project_id: str, body: FactorReview, request: Request):
        user = request.state.user
        return trust.review_factor(project_id, body, {'user_id': user['id'], 'display_name': user['display_name']})

    @app.post('/api/runs/{run_id}/recalculate-carbon')
    def recalculate(run_id: str):
        return trust.recalculate(run_id)

    @app.get('/api/projects/{project_id}/claims')
    def project_claims(project_id: str):
        return domain.project_claims(project_id)

    @app.post('/api/projects/{project_id}/searches', status_code=202)
    def search(project_id: str, body: Search):
        return robustness.start(project_id, body)

    @app.get('/api/projects/{project_id}/searches')
    def searches(project_id: str):
        return [robustness.view(project_id, s['search_id']) for s in domain.store.list('search', project_id)]

    @app.get('/api/projects/{project_id}/searches/{search_id}')
    def search_result(project_id: str, search_id: str):
        return robustness.view(project_id, search_id)

    @app.get('/api/projects/{project_id}/searches/{search_id}/artifacts')
    def search_artifacts(project_id: str, search_id: str):
        study = robustness.view(project_id, search_id)
        if study['status'] == 'running':
            raise HTTPException(409, '搜索仍在执行，完成后再导出')
        root = domain.store.root / 'searches' / search_id
        export = domain.store.root / 'exports' / (search_id + '.zip')
        export.parent.mkdir(exist_ok=True)
        with zipfile.ZipFile(export, 'w', zipfile.ZIP_DEFLATED) as archive:
            for path in root.rglob('*'):
                if path.is_file():
                    archive.write(path, path.relative_to(root).as_posix())
            archive.writestr('SEARCH_CERTIFICATE.json', json.dumps(study, ensure_ascii=False, indent=2))
        return FileResponse(export, filename=export.name, media_type='application/zip')

    @app.post('/api/projects/{project_id}/searches/{search_id}/actions')
    def actions(project_id: str, search_id: str, body: Actions):
        return robustness.actions(project_id, search_id, body)

    @app.get('/api/projects/{project_id}/search-materials')
    def materials(project_id: str):
        jobs = domain.store.jobs(project_id)
        latest = {}
        for job in jobs:
            latest.setdefault(job['scheme_id'], job['run_id'])
        ids = list(latest.values())
        return {'run_ids': ids, 'materials': robustness.materials(ids)}

    @app.get('/api/projects/{project_id}/geometry')
    def geometry(project_id: str):
        return spatial.get(project_id)

    @app.put('/api/projects/{project_id}/geometry')
    def save_geometry(project_id: str, body: Reconstruction):
        return spatial.save(project_id, body)
