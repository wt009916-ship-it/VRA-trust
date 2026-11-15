from pathlib import Path
import json
import math
import cv2
import numpy as np
from PIL import Image

BASE = Path(__file__).parent
frozen = json.loads((BASE/'public-frozen.json').read_text(encoding='utf-8'))
response = json.loads((BASE/'public-api-v1/response.json').read_text(encoding='utf-8'))
source = Image.open(BASE/'public-sources/First_Floor_Plan_HABS.jpg').convert('RGB')
rows = []
cv2.setNumThreads(1)
cv2.setRNGSeed(0)
for name, size in [('original', source.size), ('reduced', tuple(response['result']['linework']['analysis_size']))]:
    image = source.resize(size, Image.Resampling.BILINEAR)
    sx, sy = source.width/image.width, source.height/image.height
    dark = np.asarray(image.convert('L')) < 128
    excluded = np.zeros(dark.shape, dtype='uint8')
    for c in response['result']['candidates']:
        if c['source_polygon_inside_raster']:
            points = np.rint([[p[0]/sx, p[1]/sy] for p in c['polygon_source_px']]).astype('int32')
            cv2.fillPoly(excluded, [points], 1)
    excluded = cv2.dilate(excluded, np.ones((3, 3), dtype='uint8'))
    ink = (dark & ~excluded.astype(bool)).astype('uint8')*255
    lines = cv2.HoughLinesP(ink, 1, math.pi/1800, 40, minLineLength=40, maxLineGap=0)
    lines = [] if lines is None else lines.reshape(-1, 4).tolist()
    checks = []
    for r in frozen['references']:
        a, b = r['points']
        n = math.ceil(math.dist(a, b))+1
        points = np.linspace(a, b, n)/[sx, sy]
        xy = np.rint(points-.5).astype(int)
        axis = 1 if r['orientation'] == 'vertical' else 0
        cross = 1-axis
        matches = []
        for line in lines:
            p, q = [(np.array(line[i:i+2])+.5)*[sx, sy] for i in (0, 2)]
            if max(abs(p[cross]-a[cross]), abs(q[cross]-a[cross])) <= 4:
                lo, hi = sorted((p[axis], q[axis]))
                coverage = max(0, min(hi, b[axis])-max(lo, a[axis]))/(b[axis]-a[axis])
                if coverage > 0:
                    matches.append(coverage)
        checks.append({'id': r['id'], 'dark_support': float(dark[xy[:, 1], xy[:, 0]].mean()),
                       'excluded_fraction': float(excluded[xy[:, 1], xy[:, 0]].mean()),
                       'max_single_hough_coverage': max(matches, default=0)})
    rows.append({'mode': name, 'size': size, 'native_count': len(lines), 'references': checks})
out = BASE/'short-line-diagnosis.json'
assert not out.exists()
out.write_text(json.dumps(rows, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(json.dumps(rows))
