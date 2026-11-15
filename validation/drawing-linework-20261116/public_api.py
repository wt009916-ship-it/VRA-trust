"""One real authenticated, isolated public-sheet run; original references frozen."""
import hashlib
import json
from pathlib import Path
import secrets
import sys
import time

BASE = Path(__file__).parent
ROOT = Path('D:/稀土agent-稀土制暖全流程/.codex_work/vra-resource-leveling-20261115')
sys.path.insert(0, str(ROOT))
from fastapi.testclient import TestClient
from backend.api import create_app


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def assess(reference, lines, criteria):
    if not reference['reference_established']:
        return {'id': reference['id'], 'passed': False, 'state': 'reference_not_established'}
    axis = 1 if reference['orientation'] == 'vertical' else 0
    cross = 1-axis
    start, end = reference['points']
    lo, hi = start[axis], end[axis]
    intervals = []
    for line in lines:
        a, b = line['points_source_px']
        delta = b[axis]-a[axis]
        if abs(delta) < 1 or abs(b[cross]-a[cross]) > 0.05*abs(delta):
            continue
        low, high = sorted((a[axis], b[axis]))
        left, right = max(lo, low), min(hi, high)
        if right <= left:
            continue
        positions = [a[cross]+(q-a[axis])*(b[cross]-a[cross])/delta for q in (left, right)]
        if max(abs(p-start[cross]) for p in positions) <= criteria['maximum_offset_source_px']:
            intervals.append((left, right))
    merged = []
    for left, right in sorted(intervals):
        if merged and left <= merged[-1][1]:
            merged[-1][1] = max(right, merged[-1][1])
        else:
            merged.append([left, right])
    coverage = sum(b-a for a, b in merged)/(hi-lo)
    return {'id': reference['id'], 'passed': coverage >= criteria['minimum_union_coverage'],
            'coverage': coverage, 'covered_intervals': merged}


def main():
    out = BASE/'public-api-v1'
    out.mkdir(exist_ok=False)
    frozen = json.loads((BASE/'public-frozen.json').read_text(encoding='utf-8'))
    image = (BASE/'public-sources/First_Floor_Plan_HABS.jpg').read_bytes()
    assert hashlib.sha256(image).hexdigest() == frozen['source_sha256']
    assert hashlib.sha256((ROOT/'backend/drawing_linework.py').read_bytes()).hexdigest() == frozen['linework_sha256']
    receipt = {'completed': False, 'scope': frozen['scope'], 'frozen_sha256': hashlib.sha256((BASE/'public-frozen.json').read_bytes()).hexdigest(),
               'source_sha256': frozen['source_sha256'], 'linework_sha256': frozen['linework_sha256'], 'score_delta': 0}
    app = create_app(out/'private-runtime', start_worker=False)
    try:
        with TestClient(app) as client:
            registration = client.post('/api/auth/register', json={'username': 'public_line_test', 'display_name': 'Isolated reference validation', 'password': secrets.token_urlsafe(32)})
            registration.raise_for_status()
            client.headers['X-CSRF-Token'] = registration.json()['csrf_token']
            project = client.post('/api/projects', json={'name': 'Public drawing pixel reference',
                'building': {'use': 'reference_only', 'location': 'not_field_data', 'region': 'reference', 'area_m2': 1}})
            project.raise_for_status()
            before = project.json()
            base = '/api/projects/'+before['project_id']
            upload = client.post(base+'/files', files={'file': ('public-habs.jpg', image, 'image/jpeg')})
            upload.raise_for_status()
            body = {'file_id': upload.json()['file_id'], 'processing': {'line_analysis': True}}
            save(out/'request.json', body)
            started = time.monotonic()
            response = client.post(base+'/drawings', json=body)
            receipt['elapsed_seconds'] = round(time.monotonic()-started, 3)
            receipt['http_status'] = response.status_code
            save(out/'response.json', response.json())
            response.raise_for_status()
            drawing = response.json()
            work = drawing['result']['linework']
            results = [assess(r, work['lines'], frozen['criteria']) for r in frozen['references']]
            exported = client.get(base+'/drawings/'+drawing['drawing_id']+'/line-overlay.svg')
            exported.raise_for_status()
            (out/'overlay.svg').write_bytes(exported.content)
            after = client.get(base).json()
            original = client.get(base+'/files/'+body['file_id'])
            assert original.status_code == 200 and hashlib.sha256(original.content).hexdigest() == frozen['source_sha256']
            assert after == before and not client.get(base+'/evidence').json()
            assert all(g['source_kind'] == 'INFERRED_GEOMETRY_NOT_ENGINEERING' for g in work['gaps'])
            assert work['automatic_gap_fill'] is False and work['probability_of_correctness'] is None
            save(out/'project-before.json', before)
            save(out/'project-after.json', after)
            receipt.update(completed=True, references=results, reference_passed=sum(r['passed'] for r in results),
                           reference_total=len(results), detected_lines=len(work['lines']), gap_hypotheses=len(work['gaps']),
                           truncated=work['truncated'], source_unchanged=True, project_unchanged=True,
                           export_sha256=hashlib.sha256(exported.content).hexdigest())
    finally:
        save(out/'receipt.json', receipt)
    print(json.dumps({k: receipt[k] for k in ('completed', 'reference_passed', 'reference_total', 'detected_lines', 'gap_hypotheses', 'truncated', 'elapsed_seconds', 'score_delta')}))


if __name__ == '__main__':
    main()
