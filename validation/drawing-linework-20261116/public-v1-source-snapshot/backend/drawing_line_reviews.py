"""Append-only human disposition of geometric hypotheses, never engineering approval."""
import base64
import hashlib
import html
import json
from typing import Literal

from fastapi import Request
from fastapi.responses import Response
from pydantic import Field, StrictInt

from . import core
from .schema import Contract


class LineReview(Contract):
    expected_revision: StrictInt = Field(ge=1)
    candidate_id: str = Field(pattern=r'^gap_[1-9][0-9]{0,2}$')
    decision: Literal['keep_unknown', 'reject_hypothesis', 'retain_hypothesis']
    basis: str = Field(min_length=10, max_length=2000)


def review(drawings, pid, did, body, reviewer):
    current = drawings.view(pid, did)
    if current['status'] == 'stale' or not (current['result'] or {}).get('linework'):
        raise core.ValidationError('Current line analysis required')
    gaps = current['result']['linework']['gaps']
    if not any(g['candidate_id'] == body.candidate_id for g in gaps):
        raise core.ValidationError('Gap hypothesis does not exist; cannot invent geometry')
    obj = drawings._record(pid, did)
    action = {**body.model_dump(exclude={'expected_revision'}), 'reviewer_id': reviewer, 'reviewed_at': core.now(),
              'source_kind': 'HUMAN_REVIEW_OF_GEOMETRIC_HYPOTHESIS', 'engineering_validated': False}
    obj['line_reviews'] = {**obj.get('line_reviews', {}), body.candidate_id: action}
    obj['last_line_review'] = action
    obj.pop('revision', None)
    obj.pop('hash', None)
    obj['hash'] = core.hash_json(obj)
    drawings.store.put('drawing', obj, expected=body.expected_revision)
    return drawings.view(pid, did)


def overlay(drawings, pid, did):
    record = drawings.view(pid, did)
    if record['status'] == 'stale' or not (record['result'] or {}).get('linework'):
        raise core.ValidationError('Current line analysis required for export')
    work = record['result']['linework']
    path = drawings.derivative(pid, did, 'linework-preview.png')
    with path.open('rb') as source:
        raw = source.read(8*1024*1024+1)
    if len(raw) > 8*1024*1024 or hashlib.sha256(raw).hexdigest() != work['preview_sha256']:
        raise core.ValidationError('Linework preview changed or exceeds export budget')
    width, height = work['source_size']
    reviews = record.get('line_reviews') or {}
    metadata = {'drawing_id': did, 'drawing_hash': record['hash'], 'revision': record['revision'],
                'source_hash': record['source']['hash'], 'analysis_preview_hash': work['preview_sha256'],
                'analysis_size': work['analysis_size'], 'coordinate_basis': work['coordinate_basis'],
                'policy': work['policy'], 'assessment': 'ANNOTATED_GEOMETRIC_HYPOTHESES_NOT_RESTORED_ENGINEERING_DATA',
                'reviews': reviews, 'automatic_gap_fill': False, 'original_preserved': True}
    lines = []
    for gap in work['gaps']:
        state = reviews.get(gap['candidate_id'], {}).get('decision', 'keep_unknown')
        if state == 'reject_hypothesis':
            continue
        a, b = gap['points_source_px']
        color = '#c13535' if state == 'retain_hypothesis' else '#b87910'
        dash = '' if state == 'retain_hypothesis' else ' stroke-dasharray="3 2"'
        lines.append(f'<line x1="{a[0]}" y1="{a[1]}" x2="{b[0]}" y2="{b[1]}" stroke="{color}" stroke-width="2"{dash}>'
                     f'<title>{gap["candidate_id"]} / {state} / unverified hypothesis</title></line>')
    encoded = base64.b64encode(raw).decode('ascii')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height+70}" viewBox="0 -70 {width} {height+70}">'
            '<title>图纸几何假设核查层，非工程修复或认证</title>'
            f'<metadata>{html.escape(json.dumps(metadata, ensure_ascii=False))}</metadata>'
            f'<rect x="0" y="-70" width="{width}" height="{height+70}" fill="white"/>'
            '<text x="8" y="-44" font-size="14" fill="#333">几何假设核查层 · 非工程修复或认证</text>'
            '<text x="8" y="-20" font-size="12" fill="#333">红线：人工保留假设；黄虚线：未知；底图为分析缩略图，原件另存。</text>'
            f'<image x="0" y="0" width="{width}" height="{height}" preserveAspectRatio="none" href="data:image/png;base64,{encoded}"/>'
            + ''.join(lines) + '</svg>')


def register(app, drawings):
    @app.post('/api/projects/{project_id}/drawings/{drawing_id}/line-review')
    def line_review(project_id: str, drawing_id: str, body: LineReview, request: Request):
        return review(drawings, project_id, drawing_id, body, request.state.user['id'])

    @app.get('/api/projects/{project_id}/drawings/{drawing_id}/line-overlay.svg')
    def line_overlay(project_id: str, drawing_id: str):
        return Response(overlay(drawings, project_id, drawing_id), media_type='image/svg+xml', headers={
            'Content-Disposition': 'attachment; filename="drawing-line-hypotheses.svg"',
            'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
            'Content-Security-Policy': "default-src 'none'; img-src data:; sandbox"})
