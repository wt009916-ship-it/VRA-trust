"""Re-export preserved isolated records without re-running image parsing."""
from pathlib import Path
import hashlib
import json
import sys
from xml.etree import ElementTree

BASE = Path(__file__).parent
ROOT = BASE.parents[1]/'.codex_work/vra-resource-leveling-20261115'
sys.path.insert(0, str(ROOT))
from backend.api import create_app
from backend.drawings import Drawings
from backend.drawing_line_reviews import overlay

rows = []
for name in ['original-regression-v2', 'holdout-meeting-v2', 'holdout-tudor-v2']:
    out = BASE/name
    record = json.loads((out/'response.json').read_text(encoding='utf-8'))
    app = create_app(out/'private-runtime', start_worker=False)
    drawings = Drawings(app.state.domain)
    current = drawings.view(record['project_id'], record['drawing_id'])
    assert current['hash'] == record['hash'] and current['status'] != 'stale'
    xml = overlay(drawings, record['project_id'], record['drawing_id'])
    parsed = ElementTree.fromstring(xml)
    meta = json.loads(parsed.find('{http://www.w3.org/2000/svg}metadata').text)
    assert meta['truncated'] == record['result']['linework']['truncated']
    assert ('结果截断，不完整' in xml) == meta['truncated']
    assert meta['line_candidate_count'] == len(record['result']['linework']['lines'])
    assert meta['source_hash'] == record['source']['hash']
    assert drawings._record(record['project_id'], record['drawing_id'])['hash'] == record['hash']
    (out/'overlay-with-coverage.svg').write_text(xml, encoding='utf-8')
    rows.append({'run': name, 'source_hash': meta['source_hash'], 'drawing_hash': current['hash'],
        'truncated': meta['truncated'], 'visible_coverage_warning_correct': True,
        'record_unchanged': True, 'export_sha256': hashlib.sha256(xml.encode()).hexdigest()})
result = {'scope': 'Current export function on three retained real parsed records; no parser rerun, no HTTP or browser claim.',
          'exporter_sha256': hashlib.sha256((ROOT/'backend/drawing_line_reviews.py').read_bytes()).hexdigest(), 'records': rows}
(BASE/'export-coverage-recheck.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(json.dumps(result))
