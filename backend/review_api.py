"""Engineering review uses shared project authorization, CSRF and revision checks."""
from fastapi import Request
from fastapi.responses import HTMLResponse, Response

from .engineering_review import Disposition, EngineeringReview, handoff, issue_bcf, review_html


def register_reviews(app, domain):
    review = EngineeringReview(domain, app.state.modeling)
    app.state.engineering_review = review

    @app.get('/api/projects/{project_id}/engineering-review')
    def snapshot(project_id: str):
        return review.snapshot(project_id)

    @app.get('/api/projects/{project_id}/engineering-review/comparison-inputs.json')
    def comparison_inputs(project_id: str):
        return review.snapshot(project_id)['comparison_inputs']

    @app.post('/api/projects/{project_id}/engineering-review/dispositions', status_code=201)
    def disposition(project_id: str, body: Disposition, request: Request):
        return review.record(project_id, body, request.state.user['display_name'])

    @app.get('/api/projects/{project_id}/engineering-review/findings/{finding_id}/history')
    def history(project_id: str, finding_id: str):
        return review.history(project_id, finding_id)

    @app.get('/api/projects/{project_id}/engineering-review/report.html', response_class=HTMLResponse)
    def html_report(project_id: str):
        return review_html(review.snapshot(project_id))

    @app.get('/api/projects/{project_id}/engineering-review/issues.bcfzip')
    def bcf_export(project_id: str):
        return Response(issue_bcf(review.snapshot(project_id)), media_type='application/octet-stream',
                        headers={'Content-Disposition': 'attachment; filename="engineering-issues.bcfzip"'})

    @app.get('/api/projects/{project_id}/engineering-review/handoff.zip')
    def export(project_id: str):
        return Response(handoff(review.snapshot(project_id)), media_type='application/zip',
                        headers={'Content-Disposition': 'attachment; filename="engineering-review.zip"'})
