"""Project authorization and CSRF are enforced by the shared API middleware."""
import json
import zipfile

from fastapi import HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response

from .decision import Decisions, StudyCreate
from .decision_reports import decision_html, decision_pdf
from .materials import MaterialCard, MaterialUpdate


def register_decisions(app, domain):
    decisions = Decisions(domain)
    domain.decisions = app.state.decisions = decisions

    @app.get('/api/projects/{project_id}/diagnosis')
    def diagnosis(project_id: str):
        return decisions.diagnosis(project_id)

    @app.get('/api/projects/{project_id}/materials')
    def materials(project_id: str):
        return decisions.materials.list(project_id)

    @app.post('/api/projects/{project_id}/materials', status_code=201)
    def create_material(project_id: str, body: MaterialCard):
        return decisions.materials.save(project_id, body)

    @app.put('/api/projects/{project_id}/materials/{material_id}')
    def update_material(project_id: str, material_id: str, body: MaterialUpdate):
        return decisions.materials.save(project_id, body, material_id)

    @app.get('/api/projects/{project_id}/materials/{material_id}/history')
    def material_history(project_id: str, material_id: str):
        decisions.materials.get(project_id, material_id)
        return domain.store.history('material', material_id)

    @app.get('/api/projects/{project_id}/material-targets/{run_id}')
    def material_targets(project_id: str, run_id: str):
        return decisions.catalog(project_id, run_id)

    @app.post('/api/projects/{project_id}/studies', status_code=202)
    def start_study(project_id: str, body: StudyCreate):
        return decisions.start(project_id, body)

    @app.get('/api/projects/{project_id}/studies')
    def studies(project_id: str):
        return [decisions.view(project_id, s['study_id']) for s in domain.store.list('study', project_id)]

    @app.get('/api/projects/{project_id}/studies/{study_id}')
    def study(project_id: str, study_id: str):
        return decisions.view(project_id, study_id)

    @app.post('/api/projects/{project_id}/studies/{study_id}/reevaluate')
    def reevaluate(project_id: str, study_id: str):
        return decisions.reevaluate(project_id, study_id)

    @app.get('/api/projects/{project_id}/studies/{study_id}/report.json')
    def report_json(project_id: str, study_id: str):
        return decisions.report(project_id, study_id)

    @app.get('/api/projects/{project_id}/studies/{study_id}/report.html', response_class=HTMLResponse)
    def report_html(project_id: str, study_id: str):
        return decision_html(decisions.report(project_id, study_id))

    @app.get('/api/projects/{project_id}/studies/{study_id}/report.pdf')
    def report_pdf(project_id: str, study_id: str):
        return Response(decision_pdf(decisions.report(project_id, study_id)), media_type='application/pdf',
                        headers={'Content-Disposition': 'attachment; filename="material-decision.pdf"'})

    @app.get('/api/projects/{project_id}/studies/{study_id}/artifacts')
    def artifacts(project_id: str, study_id: str):
        report = decisions.report(project_id, study_id)
        if report['study']['status'] == 'running':
            raise HTTPException(409, '研究仍在执行，完成后再导出')
        root = domain.store.root / 'studies' / study_id
        target = domain.store.root / 'exports' / (study_id + '.zip')
        target.parent.mkdir(exist_ok=True)
        with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
            for path in root.rglob('*'):
                if path.is_file():
                    archive.write(path, 'study/' + path.relative_to(root).as_posix())
            baseline = domain.store.root / 'runs' / report['study']['source_run_id']
            for path in baseline.rglob('*'):
                if path.is_file():
                    archive.write(path, 'baseline/' + path.relative_to(baseline).as_posix())
            archive.writestr('DECISION_REPORT.json', json.dumps(report, ensure_ascii=False, indent=2))
            archive.writestr('DECISION_REPORT.html', decision_html(report))
        return FileResponse(target, media_type='application/zip', filename=target.name)
