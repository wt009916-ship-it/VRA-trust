from pathlib import Path
import hashlib
import json
import numpy as np
from PIL import Image

BASE = Path(__file__).parent
ROOT = BASE.parents[1]/'.codex_work/vra-resource-leveling-20261115'
sources = json.loads((BASE/'public-sources/holdout-source-receipts.json').read_text(encoding='utf-8'))
regions = {
    'twelfth-meeting-house.jpg': [
        ('vertical', [145, 220, 166, 295]), ('vertical', [438, 240, 459, 330]),
        ('horizontal', [270, 585, 375, 605]), ('horizontal', [655, 185, 755, 203]),
        ('horizontal', [652, 240, 707, 255]), ('vertical', [571, 465, 593, 525]),
        ('vertical', [865, 460, 884, 510]), ('horizontal', [760, 545, 825, 559])],
    'tudor-place-3840.jpg': [
        ('vertical', [3418, 1450, 3440, 1570]), ('vertical', [3045, 1460, 3080, 1580]),
        ('vertical', [1060, 1520, 1115, 1630]), ('vertical', [1888, 1560, 1920, 1670]),
        ('horizontal', [3200, 1780, 3340, 1820]), ('horizontal', [400, 1560, 520, 1600]),
        ('horizontal', [1950, 814, 2020, 850]), ('horizontal', [1560, 1025, 1620, 1060])]
}
for item in sources:
    path = BASE/'public-sources'/item['name']
    assert item['downloaded'] and hashlib.sha256(path.read_bytes()).hexdigest() == item['sha256']
    gray = np.asarray(Image.open(path).convert('L'))
    refs = []
    for index, (orientation, roi) in enumerate(regions[item['name']], 1):
        x0, y0, x1, y1 = roi
        projection = (gray[y0:y1, x0:x1] < 80).mean(axis=0 if orientation == 'vertical' else 1)
        offset = int(projection.argmax())
        support = float(projection[offset])
        points = ([[x0+offset+.5, y0+.5], [x0+offset+.5, y1-.5]] if orientation == 'vertical'
                  else [[x0+.5, y0+offset+.5], [x1-.5, y0+offset+.5]])
        refs.append({'id': f'S{index:02}', 'orientation': orientation, 'roi': roi, 'points': points,
                     'reference_dark_support': support, 'reference_established': support >= .7})
    target = BASE/(path.stem+'-frozen.json')
    assert not target.exists()
    result = {'source_file': 'public-sources/'+item['name'], 'source_sha256': item['sha256'],
        'linework_sha256': hashlib.sha256((ROOT/'backend/drawing_linework.py').read_bytes()).hexdigest(),
        'source_receipt': item, 'scope': 'One previously unused public sheet; selected drawn strokes only, not walls or dimensions.',
        'method': 'Manual ROIs on original downloaded pixels; independent gray<80 projection before any application run.',
        'criteria': {'minimum_reference_support': .7, 'maximum_offset_source_px': 4, 'minimum_union_coverage': .7},
        'references': refs, 'gap_interpretation': 'Physical damage unknown; all gap hypotheses remain unverified.'}
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'file': path.name, 'supports': [r['reference_dark_support'] for r in refs], 'points': [r['points'] for r in refs]}))

old = json.loads((BASE/'public-frozen.json').read_text(encoding='utf-8'))
old.update(source_file='public-sources/First_Floor_Plan_HABS.jpg',
           linework_sha256=hashlib.sha256((ROOT/'backend/drawing_linework.py').read_bytes()).hexdigest(),
           scope='Known first-sheet regression; original8 regions and criteria unchanged; not new independent validation.')
(BASE/'original-regression-v2-frozen.json').write_text(json.dumps(old, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
