"""Project-scoped trust and Agent endpoints, protected by the main API boundary."""
import json
import zipfile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi import HTTPException, Request
from .agent import Agent, Chat
from .gateway import Gateway, ProviderSettings
from .trust import FactorUpdate, FactorReview, Trust
from .robustness import Robustness, Search, Actions
from .spatial import Spatial, Reconstruction
from .thermal import Thermal, Assembly, ThermalCompare, compare as compare_thermal, render_html as thermal_html
from .cad import Cad, Inspection
from .lifecycle import Lifecycle, Inventory, Comparison as LifecycleComparison, compare as lifecycle_compare, report as lifecycle_report

def register_extensions(app, domain, auth):
    trust, gateway = (Trust(domain), Gateway(domain.store))
    agent = Agent(domain, gateway)
    app.state.agent, app.state.gateway = (agent, gateway)
    robustness, spatial = (Robustness(domain), Spatial(domain))
    app.state.robustness = robustness
    domain.robustness = robustness
    thermal = Thermal(domain)
    cad = Cad(domain)
    lifecycle = Lifecycle(domain)

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

    @app.post('/api/projects/{project_id}/cad-inspections', status_code=201)
    def inspect_cad(project_id: str, body: Inspection):
        return cad.inspect(project_id, body)

    @app.get('/api/projects/{project_id}/cad-inspections')
    def cad_history(project_id: str):
        return [cad.view(project_id, r['cad_id']) for r in domain.store.list('cad', project_id)]

    @app.get('/api/projects/{project_id}/cad-inspections/{cad_id}')
    def cad_record(project_id: str, cad_id: str):
        return cad.view(project_id, cad_id)

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
        return {'provider_ready': config['enabled'] and config['key_configured'], 'model': config['model'], 'tools': agent.tools()}

    @app.post('/api/projects/{project_id}/agent/chat', status_code=202)
    def chat(project_id: str, body: Chat):
        return agent.start(project_id, body)

    @app.get('/api/projects/{project_id}/agent-tasks')
    def agent_history(project_id: str):
        return [{k: task.get(k) for k in ('agent_id', 'question', 'mode', 'objective', 'status', 'created_at', 'answer', 'previous_agent_id')}
                for task in domain.store.list('agent', project_id)[:20]]

    @app.get('/api/projects/{project_id}/agent/{agent_id}')
    def agent_task(project_id: str, agent_id: str):
        task = domain.store.get('agent', agent_id)
        if task['project_id'] != project_id:
            raise HTTPException(404)
        return task

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
