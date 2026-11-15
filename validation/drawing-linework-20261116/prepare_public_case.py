"""Freeze pixel references before running the application on this public sheet."""
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image

BASE = Path(__file__).parent
ROOT = Path('D:/稀土agent-稀土制暖全流程/.codex_work/vra-resource-leveling-20261115')
source = BASE/'public-sources/First_Floor_Plan_HABS.jpg'
assert hashlib.sha256(source.read_bytes()).hexdigest() == 'ec3b9a9ec1c883f1913109438b47e417e04b7030f6411852324f4857f6b9ba8b'
gray = np.asarray(Image.open(source).convert('L'))
# Regions chosen from direct inspection of the original image, before any
# application output. Independent 1-D dark-pixel projection, not Hough lines.
regions = [('S01', 'vertical', [814, 707, 834, 837]),
           ('S02', 'vertical', [950, 710, 971, 838]),
           ('S03', 'vertical', [813, 904, 833, 996]),
           ('S04', 'vertical', [952, 916, 971, 996]),
           ('S05', 'vertical', [1288, 120, 1302, 178]),
           ('S06', 'horizontal', [1305, 106, 1364, 122]),
           ('S07', 'horizontal', [1036, 686, 1112, 706]),
           ('S08', 'horizontal', [680, 1080, 740, 1101])]
references = []
for name, orientation, roi in regions:
    x0, y0, x1, y1 = roi
    sub = gray[y0:y1, x0:x1] < 80
    projection = sub.mean(axis=0 if orientation == 'vertical' else 1)
    offset = int(projection.argmax())
    support = float(projection[offset])
    points = ([[x0+offset+0.5, y0+0.5], [x0+offset+0.5, y1-0.5]] if orientation == 'vertical'
              else [[x0+0.5, y0+offset+0.5], [x1-0.5, y0+offset+0.5]])
    references.append({'id': name, 'orientation': orientation, 'roi': roi, 'points': points,
                       'reference_dark_support': support, 'reference_established': support >= 0.7})
result = {'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
          'linework_sha256': hashlib.sha256((ROOT/'backend/drawing_linework.py').read_bytes()).hexdigest(),
          'method': 'Manual regions; independent grey<80 one-dimensional projection. Selected drawn strokes only, not walls or dimensions.',
          'scope': 'One previously unused public sheet, eight selected stroke references. Not eight drawings or full drawing comprehension.',
          'criteria': {'minimum_reference_support': 0.7, 'maximum_offset_source_px': 4,
                       'minimum_union_coverage': 0.7}, 'references': references,
          'gap_interpretation': 'No ground truth of physical damage on this historical sheet. Every proposed gap remains unverified.'}
target = BASE/'public-frozen.json'
assert not target.exists()
target.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(json.dumps({'selected': len(references), 'reference_established': sum(r['reference_established'] for r in references),
                  'supports': [round(r['reference_dark_support'], 3) for r in references]}))
