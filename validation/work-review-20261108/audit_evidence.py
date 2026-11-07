"""Read-only historical evidence locator; never rewrites manifest hashes."""
import hashlib
import json
from pathlib import Path

roots = [
    Path('C:/Users/18483/AppData/Local/Temp/vra-material-release-0cc36c02a1dc4072a7ef4b468e162b77/app'),
    Path('C:/Users/18483/AppData/Local/Temp/vra-design-release-a773af75c60e4c7db80c7091a498175b'),
    Path('D:/稀土agent-稀土制暖全流程/vra-trust'),
]
names = ['DESIGN_LOADS', 'HOURLY_THERMAL', 'DESIGN_INPUTS', 'LOCAL_MODEL',
         'AGENT_CALCULATIONS', 'AGENT_ENGINEERING', 'AGENT_OUTPUTS', 'IFC_GEOMETRY',
         'IFC_SELECTED_UNION', 'DRAWING_OCR', 'DRAWING_GEOMETRY', 'NATIVE_RECOVERY',
         'ENCRYPTED_BACKUP', 'MATERIAL_SCENARIOS', 'OPERATIONS', 'ENGINEERING',
         'CONSTRUCTION_SCHEDULE', 'CALCULATION_PROVENANCE', 'MATERIAL_COST']
rows = []
for name in names:
    manifest = roots[1] / 'docs' / (name + '_EVIDENCE.json')
    doc = json.loads(manifest.read_text(encoding='utf-8-sig'))
    records = []
    for key in ('files', 'artifacts', 'evidence_files', 'local_artifacts'):
        records.extend(doc.get(key, []))
    for item in records:
        path, expected = item.get('path'), item.get('sha256')
        if not path or not expected:
            continue
        found = []
        for root in roots:
            candidate = root / path
            if candidate.is_file():
                raw = candidate.read_bytes()
                actual = hashlib.sha256(raw).hexdigest()
                found.append({'root': str(root), 'sha256': actual, 'bytes': len(raw),
                              'matches': actual == expected})
                if actual == expected:
                    break
        rows.append({'manifest': name, 'path': path, 'expected': expected,
                     'verified': any(x['matches'] for x in found), 'locations': found})
out = Path(__file__).parent / 'historical-evidence-check.json'
out.write_text(json.dumps({'application_commit': '5209d744c9bf226b4310122d538905fee67993e2',
    'checked': len(rows), 'verified': sum(r['verified'] for r in rows),
    'unresolved': [r for r in rows if not r['verified']], 'records': rows},
    ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'checked': len(rows), 'verified': sum(r['verified'] for r in rows),
                  'unresolved': [{'manifest': r['manifest'], 'path': r['path'],
                                  'found': bool(r['locations'])} for r in rows if not r['verified']]},
                 ensure_ascii=False))
