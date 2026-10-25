"""Authenticated local project API. Run exactly one uvicorn worker."""
import io
import json
import os
import hmac
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.openapi.utils import get_openapi
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from . import core
from .domain import Domain
from .auth import Auth, Credentials, Registration, PasswordChange
from .api_tokens import Tokens
from .reports import report_html, report_pdf
from .schema import BuildingUpdate, ComparisonRequest, Evidence, EvidenceCreate, EvidenceReview, EvidenceMetadata, Project, ProjectCreate, RunCreate, RunView
from .store import Store

class BodyTooLarge(Exception):
    pass

class BodyLimit:

    def __init__(self, app, limit):
        self.app, self.limit = (app, limit)

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        size = 0

        async def limited_receive():
            nonlocal size
            message = await receive()
            size += len(message.get('body', b''))
            if size > self.limit:
                raise BodyTooLarge()
            return message
        try:
            await self.app(scope, limited_receive, send)
        except BodyTooLarge:
            await JSONResponse({'detail': 'Upload/request size limit exceeded'}, status_code=413)(scope, receive, send)

def create_app(data_dir=None, *, start_worker=True):
    root = Path(data_dir or os.environ.get('VRA_DATA_DIR', core.ROOT / 'runtime')).resolve()
    if (root / '.restore-incomplete').exists():
        raise core.ValidationError('恢复尚未校验通过，拒绝启动此目录')
    domain = Domain(Store(root))
    auth = Auth(domain.store)

    @asynccontextmanager
    async def lifespan(app):
        if start_worker:
            app.state.agent.recover()
            app.state.robustness.recover()
            app.state.decisions.recover()
            app.state.modeling.recover()
            domain.start_worker()
        yield
        domain.stop.set()
        if domain.worker:
            domain.worker.join(timeout=5)
    app = FastAPI(title='VRA-Trust Evidence API', version='1.0.0', lifespan=lifespan)
    from .runtime_backup import Operations
    app.state.operations = Operations()
    app.state.domain = domain
    app.state.auth = auth
    app.state.tokens = Tokens(auth)
    public_api = {'/api/health', '/api/auth/status', '/api/auth/login', '/api/auth/register'}
    maximum = int(os.environ.get('VRA_MAX_UPLOAD_MB', '64')) * 1024 * 1024
    app.add_middleware(BodyLimit, limit=maximum + 65536)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['localhost', '127.0.0.1', '[::1]', 'testserver'])

    @app.middleware('http')
    async def local_boundary(request: Request, call_next):
        origin = request.headers.get('origin')
        if origin and origin != str(request.base_url).rstrip('/'):
            return JSONResponse({'detail': 'Cross-origin request rejected'}, status_code=403)
        if request.headers.get('sec-fetch-site') == 'cross-site':
            return JSONResponse({'detail': 'Cross-site request rejected'}, status_code=403)
        path = request.url.path
        if path.startswith('/api/') and path not in public_api:
            authorization = request.headers.get('authorization', '')
            bearer = authorization.startswith('Bearer ')
            user = app.state.tokens.authenticate(authorization[7:]) if bearer else auth.session(request.cookies.get(auth.cookie))
            if not user:
                return JSONResponse({'detail': '请先登录'}, status_code=401)
            if bearer and (not app.state.tokens.permits(user, request.method, path)):
                return JSONResponse({'detail': 'API Token 的项目或权限范围不足'}, status_code=403)
            request.state.user = user
            if not bearer and request.method not in {'GET', 'HEAD', 'OPTIONS'} and (not hmac.compare_digest(request.headers.get('x-csrf-token', ''), user['csrf'])):
                return JSONResponse({'detail': '会话校验失败，请刷新后重试'}, status_code=403)
            parts = path.strip('/').split('/')
            try:
                if len(parts) >= 3 and parts[1] == 'projects':
                    auth.require_project(parts[2], user['id'])
                if len(parts) >= 3 and parts[1] == 'runs':
                    auth.require_run(parts[2], user['id'])
            except (HTTPException, core.ValidationError):
                return JSONResponse({'detail': '记录不存在或无访问权限'}, status_code=404)
        declared = request.headers.get('content-length')
        if declared and (not declared.isdigit() or int(declared) > maximum + 65536):
            return JSONResponse({'detail': f'请求超过大小限制；单文件上限 {maximum // 1024 // 1024} MB，请拆分资料'}, status_code=413)
        tracked = path.startswith('/api/') and path != '/api/health'
        if tracked and (not app.state.operations.enter()):
            return JSONResponse({'detail': '正在创建完整备份，请稍后重试'}, status_code=503, headers={'Retry-After': '5'})
        try:
            response = await call_next(request)
        finally:
            if tracked:
                app.state.operations.leave()
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'"
        return response

    @app.exception_handler(core.ValidationError)
    async def validation_error(request, exc):
        return JSONResponse({'detail': str(exc)}, status_code=409)

    @app.exception_handler(KeyError)
    async def not_found(request, exc):
        return JSONResponse({'detail': 'Record not found'}, status_code=404)

    @app.exception_handler(RequestValidationError)
    async def schema_error(request, exc):
        return JSONResponse({'detail': [{'loc': e['loc'], 'msg': e['msg'], 'type': e['type']} for e in exc.errors()]}, status_code=422)

    @app.get('/api/health')
    def health():
        try:
            core.engine_path()
            available = True
        except core.ValidationError:
            available = False
        return {'status': 'ok', 'maintenance': app.state.operations.maintenance, 'engine_available': available, 'worker_alive': bool(domain.worker and domain.worker.is_alive()), 'upload_policy': {'max_file_bytes': maximum, 'max_file_mb': maximum // 1024 // 1024}, 'demo_mode': os.environ.get('DEMO_MODE', 'false').lower() == 'true', 'deployment': 'local_authenticated', 'capabilities': {'project_intake': True, 'evidence_gate': True, 'real_energyplus': available, 'llm_tools': all((app.state.gateway.public()[k] for k in ('enabled', 'key_configured'))), 'agent_tools_installed': True, 'claim_dag': True, 'selective_recomputation': True, 'drawing_ai': bool(app.state.gateway.public().get('vision_model') and app.state.gateway.public()['enabled'] and app.state.gateway.public()['key_configured']), 'local_dxf_pdf_ifc': True, 'model_to_idf': True, 'ifc_export': True, 'persistent_model_workflow': True, 'mcp_adapter': True, 'weather_analysis': True, 'nasa_daily_connector': True, 'epw_quality_gate': True, 'manual_geometry': True, 'robustness': True}}

    @app.get('/api/auth/status')
    def auth_status():
        return {'setup_required': auth.setup_required(), 'registration_mode': auth.registration_mode()}

    def session_response(result, old_token=None):
        token, user = result
        if old_token:
            auth.logout(old_token)
        response = JSONResponse({'user': {k: v for k, v in user.items() if k != 'csrf'}, 'csrf_token': user['csrf']})
        response.set_cookie(auth.cookie, token, httponly=True, samesite='strict', max_age=auth.ttl, secure=os.environ.get('VRA_COOKIE_SECURE', 'false').lower() == 'true')
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.post('/api/auth/register')
    def register(body: Registration, request: Request):
        auth.throttle(body.username, request.client.host if request.client else 'unknown')
        return session_response(auth.register(body), request.cookies.get(auth.cookie))

    @app.post('/api/auth/login')
    def login(body: Credentials, request: Request):
        auth.throttle(body.username, request.client.host if request.client else 'unknown')
        return session_response(auth.login(body), request.cookies.get(auth.cookie))

    @app.get('/api/auth/me')
    def me(request: Request):
        user = request.state.user
        return {'user': {k: v for k, v in user.items() if k != 'csrf'}, 'csrf_token': user['csrf']}

    @app.post('/api/auth/logout')
    def logout(request: Request):
        auth.logout(request.cookies[auth.cookie])
        response = JSONResponse({'logged_out': True})
        response.delete_cookie(auth.cookie)
        return response

    @app.post('/api/auth/password')
    def change_password(body: PasswordChange, request: Request):
        user = request.state.user
        auth.throttle(user['username'], request.client.host if request.client else 'unknown')
        return session_response(auth.change_password(user['id'], body))

    @app.get('/api/projects', response_model=list[Project])
    def projects(request: Request):
        return [p for p in domain.store.list('project') if auth.allows(p['project_id'], request.state.user['id'])]

    @app.post('/api/projects', response_model=Project, status_code=201)
    def create_project(body: ProjectCreate, request: Request):
        project = domain.create_project(body)
        auth.own(project['project_id'], request.state.user['id'])
        return project

    @app.post('/api/reference-projects', response_model=Project, status_code=201)
    def reference_project(request: Request):
        project = domain.create_reference()
        auth.own(project['project_id'], request.state.user['id'])
        return project

    @app.get('/api/projects/{project_id}', response_model=Project)
    def project(project_id: str):
        return domain.store.get('project', project_id)

    @app.put('/api/projects/{project_id}/building', response_model=Project)
    def building(project_id: str, body: BuildingUpdate):
        return domain.update_building(project_id, body)

    @app.post('/api/projects/{project_id}/files', status_code=201)
    async def upload(project_id: str, file: UploadFile=File(...)):
        content = await file.read(maximum + 1)
        if len(content) > maximum:
            return JSONResponse({'detail': f'文件超过 {maximum // 1024 // 1024} MB，请拆分资料后上传'}, status_code=413)
        return domain.add_file(project_id, file.filename or 'unnamed', content)

    @app.get('/api/projects/{project_id}/files/{file_id}')
    def source_file(project_id: str, file_id: str):
        record, path = domain.file_record(project_id, file_id)
        return FileResponse(path, filename=record['name'], media_type='application/octet-stream')

    @app.post('/api/projects/{project_id}/evidence', response_model=Evidence, status_code=201)
    def add_evidence(project_id: str, body: EvidenceCreate):
        return domain.add_evidence(project_id, body)

    @app.get('/api/projects/{project_id}/evidence', response_model=list[Evidence])
    def evidence(project_id: str):
        domain.store.get('project', project_id)
        return domain.store.list('evidence', project_id)

    @app.patch('/api/projects/{project_id}/evidence/{evidence_id}', response_model=Evidence)
    def review(project_id: str, evidence_id: str, body: EvidenceReview):
        return domain.review(project_id, evidence_id, body)

    @app.get('/api/projects/{project_id}/evidence/{evidence_id}/history', response_model=list[Evidence])
    def evidence_history(project_id: str, evidence_id: str):
        ev = domain.store.get('evidence', evidence_id)
        if ev['project_id'] != project_id:
            raise core.ValidationError('Cross-project evidence rejected')
        return domain.store.history('evidence', evidence_id)

    @app.put('/api/projects/{project_id}/evidence/{evidence_id}/metadata', response_model=Evidence)
    def evidence_metadata(project_id: str, evidence_id: str, body: EvidenceMetadata):
        ev = domain.store.get('evidence', evidence_id)
        if ev['project_id'] != project_id:
            raise HTTPException(404, '资料不属于当前项目')
        if ev['source_file']:
            domain.file_record(project_id, ev['source_file'])
        return domain.store.put('evidence', {**ev, **body.model_dump(exclude={'expected_revision'}), 'review_state': 'pending', 'review_note': None, 'timestamp': core.now()}, body.expected_revision)

    @app.get('/api/projects/{project_id}/gate')
    def gate(project_id: str, scheme_id: str='baseline'):
        return domain.gate(project_id, scheme_id)

    @app.get('/api/projects/{project_id}/runs', response_model=list[RunView])
    def runs(project_id: str):
        domain.store.get('project', project_id)
        return [domain.view(j['run_id']) for j in domain.store.jobs(project_id)]

    @app.get('/api/factor-profiles')
    def factor_profiles():
        return core.profiles()

    @app.post('/api/runs', response_model=RunView, status_code=202)
    def create_run(body: RunCreate, request: Request):
        auth.require_project(body.project_id, request.state.user['id'])
        return domain.submit(body)

    @app.get('/api/runs/{run_id}', response_model=RunView)
    @app.get('/api/runs/{run_id}/result', response_model=RunView)
    def run(run_id: str):
        return domain.view(run_id)

    @app.get('/api/runs/{run_id}/evidence')
    def run_evidence(run_id: str):
        job = domain.store.job(run_id)
        return {'run_id': run_id, 'evidence': job['evidence_snapshot'], 'validation': domain.view(run_id)}

    @app.get('/api/runs/{run_id}/claims')
    def run_claims(run_id: str):
        return domain.claims(run_id)

    @app.get('/api/runs/{run_id}/artifacts')
    def artifacts(run_id: str):
        domain.store.job(run_id)
        rd = domain.store.root / 'runs' / run_id
        if not rd.is_dir():
            raise KeyError(run_id)
        content = io.BytesIO()
        with zipfile.ZipFile(content, 'w', zipfile.ZIP_DEFLATED) as archive:
            for path in rd.rglob('*'):
                if path.is_file():
                    archive.write(path, path.relative_to(rd).as_posix())
            archive.writestr('CURRENT_VALIDATION.json', json.dumps(domain.view(run_id), ensure_ascii=False, indent=2))
        return Response(content.getvalue(), media_type='application/zip', headers={'Content-Disposition': f'attachment; filename="{run_id}.zip"'})

    @app.get('/api/runs/{run_id}/report.json')
    def json_report(run_id: str):
        return domain.report(run_id)

    @app.get('/api/runs/{run_id}/report.html', response_class=HTMLResponse)
    def html_report(run_id: str):
        return report_html(domain.report(run_id))

    @app.get('/api/runs/{run_id}/report.pdf')
    def pdf_report(run_id: str):
        return Response(report_pdf(domain.report(run_id)), media_type='application/pdf', headers={'Content-Disposition': f'attachment; filename="{run_id}.pdf"'})

    @app.post('/api/comparisons')
    def compare(body: ComparisonRequest, request: Request):
        for run_id in body.run_ids:
            auth.require_run(run_id, request.state.user['id'])
        return domain.compare(body.run_ids)
    from .extensions import register_extensions
    register_extensions(app, domain, auth)
    from .product_api import register_product
    register_product(app, domain, auth)
    from .weather_api import register_weather
    register_weather(app, domain)
    from .intake import register_intake
    register_intake(app, domain, auth, maximum)
    from .workspace import register_workspace
    register_workspace(app, domain, auth)
    dist = core.ROOT / 'frontend/dist'
    if dist.is_dir():

        @app.get('/admin', include_in_schema=False)
        @app.get('/admin/', include_in_schema=False)
        def admin_page():
            return FileResponse(dist / 'index.html')
        app.mount('/', StaticFiles(directory=dist, html=True), name='frontend')

    def secured_openapi():
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
        schema.setdefault('components', {})['securitySchemes'] = {'sessionCookie': {'type': 'apiKey', 'in': 'cookie', 'name': auth.cookie}, 'csrfHeader': {'type': 'apiKey', 'in': 'header', 'name': 'X-CSRF-Token'}, 'projectToken': {'type': 'http', 'scheme': 'bearer', 'description': 'Project-scoped token; read/write/compute scopes. Token management and developer configuration require session authentication.'}}
        for path, methods in schema['paths'].items():
            if path.startswith('/api/') and path not in public_api:
                for method, operation in methods.items():
                    security = {'sessionCookie': []}
                    if method not in {'get', 'head', 'options'}:
                        security['csrfHeader'] = []
                    operation['security'] = [security]
                    if path.startswith(('/api/projects/{project_id}', '/api/runs/{run_id}')) and '/tokens' not in path:
                        operation['security'].append({'projectToken': []})
                    operation['responses'].setdefault('401', {'description': 'Authentication required'})
                    operation['responses'].setdefault('403', {'description': 'CSRF or origin rejected'})
        app.openapi_schema = schema
        return schema
    app.openapi = secured_openapi
    return app
app = create_app()
