"""Local raster wall topology + OCR labels. All outputs remain review candidates."""
import contextlib
import copy
from collections import OrderedDict
import json
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

from . import core

_CACHE = OrderedDict()
_CACHE_LOCK = threading.Lock()


def extract(path, options):
    if path.suffix.lower() not in {'.pdf', '.png', '.jpg', '.jpeg'}:
        raise core.ValidationError('本地图纸建模支持 PDF、PNG、JPEG')
    started = time.perf_counter()
    from . import drawing_damage, document_reader, document_worker, model_schema
    fingerprints = {m.__name__: core.sha(m.__file__) for m in (drawing_damage, document_reader, document_worker, model_schema)}
    if options.ocr_labels:
        fingerprints['ocr_models'] = {key: core.sha(p) for key, p in document_reader.model_paths().items()}
    source_hash = core.sha(path)
    key = core.hash_json([source_hash, path.suffix.lower(), options.model_dump(exclude={'file_id'}), core.sha(__file__), fingerprints])
    with _CACHE_LOCK:
        cached = _CACHE.get(key)
        if cached:
            _CACHE.move_to_end(key)
            data = copy.deepcopy(cached)
            data['metadata']['recognition_cache'] = {'hit': True, 'key': key, 'source_sha256': source_hash,
                                                     'request_seconds': time.perf_counter()-started}
            return data
    try:
        result = subprocess.run([sys.executable, '-X', 'utf8', '-m', 'backend.floorplan', str(path.resolve())],
            input=options.model_dump_json().encode(), capture_output=True, timeout=120,
            cwd=Path(__file__).resolve().parents[1], creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except subprocess.TimeoutExpired as exc:
        raise core.ValidationError('图纸建模超过 120 秒，已终止；请裁切单张平面后重试') from exc
    try:
        data = json.loads(result.stdout)
    except ValueError as exc:
        raise core.ValidationError('图纸建模进程失败，请检查图页') from exc
    if result.returncode:
        if data.get('diagnostics'):
            from .model_import import ImportDiagnosticError
            raise ImportDiagnosticError(data.get('error', '破损图纸未得到可用空间'), data['diagnostics'])
        raise core.ValidationError(data.get('error', '图纸建模失败'))
    if core.sha(path) != source_hash:
        raise core.ValidationError('识别期间原件发生变化，未采纳或缓存结果')
    with _CACHE_LOCK:
        _CACHE[key] = copy.deepcopy(data)
        while len(_CACHE) > 8:
            _CACHE.popitem(last=False)
    data['metadata']['recognition_cache'] = {'hit': False, 'key': key, 'source_sha256': source_hash,
                                             'request_seconds': time.perf_counter()-started}
    return data


def recognize(path, options):
    import cv2
    import numpy as np
    from shapely.geometry import Point, Polygon
    from .document_worker import raster, read
    from .model_schema import Room

    with raster(path, options.page) as image:
        rgb = np.array(image)
    height, width = rgb.shape[:2]
    x0, y0, x1, y1 = options.crop_px or (0, 0, width, height)
    if x1 > width or y1 > height or x1-x0 < 30 or y1-y0 < 30:
        raise core.ValidationError('裁剪范围超出图页或过小，请重新在预览中框选平面')
    factor = options.scale_to_m
    # Keep achromatic line work; coloured annotations are not wall evidence.
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    saturation = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)[:, :, 1]
    ink = ((gray < 190) & (saturation < 45)).astype('uint8')[y0:y1, x0:x1] * 255
    run = max(8, min(100, round(.5 / factor)))
    gap = max(1, round(options.closure_m / factor))
    if gap > 300:
        raise core.ValidationError('门窗缺口闭合超过 300 像素，请核对比例或减小闭合距离')
    damage = None
    if options.mode == 'damaged_raster':
        from .drawing_damage import prepare
        walls, inverse, damage = prepare(rgb[y0:y1, x0:x1], options, (x0, y0))
    else:
        horizontal = cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((1, run), np.uint8))
        vertical = cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((run, 1), np.uint8))
        horizontal = cv2.morphologyEx(horizontal, cv2.MORPH_CLOSE, np.ones((1, gap), np.uint8))
        vertical = cv2.morphologyEx(vertical, cv2.MORPH_CLOSE, np.ones((gap, 1), np.uint8))
        walls = cv2.bitwise_or(horizontal, vertical)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(255-walls, connectivity=4)
    doc = read(path, selected_page=options.page) if options.ocr_labels else {
        'document_pages': [{'lines': []}], 'ocr': {'enabled': False, 'external_upload': False}}
    texts = doc['document_pages'][0]['lines']
    rooms, regions = [], []
    for index in range(1, count):
        x, y, w, h, _ = map(int, stats[index])
        if x == 0 or y == 0 or x+w >= x1-x0 or y+h >= y1-y0:
            continue  # Connected to crop border: not an enclosed room.
        mask = (labels == index).astype('uint8')
        contours, hierarchy = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
        exterior = max(contours, key=cv2.contourArea)
        if len(exterior) < 3:
            regions.append({'status': 'excluded', 'reason': '不足3个轮廓顶点的像素细线，不作为闭合空间',
                            'pixel_bounds': [x+x0, y+y0, x+w+x0, y+h+y0], 'area_m2': 0.})
            continue
        raw = Polygon(exterior.reshape(-1, 2))
        clean = raw.buffer(0)  # Remove zero-width pixel spurs; never invent missing area.
        if clean.geom_type != 'Polygon' or abs(clean.area-raw.area)*factor**2 > .01:
            regions.append({'status': 'blocked', 'reason': '像素轮廓自交且无法无损修复', 'pixel_bounds': [x+x0, y+y0, x+w+x0, y+h+y0]})
            continue
        clean = clean.simplify(max(.75, .015/factor), preserve_topology=True)
        if damage:
            from .drawing_damage import map_points
            pixels = map_points(list(clean.exterior.coords)[:-1], inverse, (x0, y0))
        else:
            pixels = [(float(px+x0), float(py+y0)) for px, py in list(clean.exterior.coords)[:-1]]
        polygon = Polygon([(px*factor, (height-py)*factor) for px, py in pixels])
        if not polygon.is_valid or polygon.area < .5:
            continue
        included = []
        for line in texts:
            px = sum(pt[0] for pt in line['box']) / 4
            py = sum(pt[1] for pt in line['box']) / 4
            if Polygon(pixels).covers(Point(px, py)):
                included.append(line)
        areas = []
        for line in included:
            match = re.search(r'(\d+(?:[.,]\d+)?)\s*m\s*[²2]', line['text'], re.I)
            if match:
                areas.append((float(match[1].replace(',', '.')), line))
        region = {'pixel_bounds': [x+x0, y+y0, x+w+x0, y+h+y0], 'area_m2': polygon.area,
                  'pixel_cleanup_area_delta_m2': (clean.area-raw.area)*factor**2,
                  'texts': included, 'status': 'candidate', 'reason': None}
        # Never silently fill large internal obstacles/courtyards into room volume.
        holes = [cv2.contourArea(c)*factor**2 for c, hi in zip(contours, hierarchy[0]) if hi[3] >= 0]
        if any(a > .1 for a in holes):
            region.update(status='blocked', reason='内部孔洞/障碍大于 0.1 m²，须补充轮廓，未填平')
        elif polygon.area < options.min_room_area_m2 or min(w, h)*factor < .5:
            region.update(status='excluded', reason='小于设定面积或净宽 0.5 m；可能为窗洞/图框，须核对')
        elif len(pixels) > 100:
            region.update(status='blocked', reason='边界超过 100 顶点，请拆分或修正')
        regions.append(region)
        if region['status'] != 'candidate':
            continue
        annotated = areas[0][0] if len(areas) == 1 else None
        if areas:
            ay = sum(p[1] for p in areas[0][1]['box']) / 4
            names = [line['text'] for line in included if not re.search(r'\d\s*m\s*[²2]', line['text'], re.I)
                     and 0 < ay-sum(p[1] for p in line['box'])/4 < 65]
        else:
            names = []
        rid = f'R{len(rooms)+1}'
        label = ' / '.join(names)[:120] or f'未标注区域 {len(rooms)+1}'
        region['room_id'] = rid
        rooms.append(Room(id=rid, name=label, polygon=list(polygon.exterior.coords)[:-1],
            height_m=options.height_m, elevation_m=options.elevation_m, conditioned=None, include_floor_area=None,
            source_locator=f'LOCAL_INFERRED page={options.page}; scale={factor}; close={options.closure_m}m; {options.scale_basis}'[:500],
            drawing={'page': options.page, 'pixels': [width, height], 'polygon_px': pixels, 'scale_to_m': factor,
                     'scale_basis': options.scale_basis, 'closure_m': options.closure_m, 'label': label,
                     'annotated_area_m2': annotated,
                     'area_error_percent': 100*(polygon.area-annotated)/annotated if annotated else None,
                     'damage_analysis_hash': core.hash_json(damage) if damage else None}).model_dump())
        if len(rooms) > 100:
            raise core.ValidationError('识别空间超过 100 个，请缩小裁剪区域')
    if not rooms:
        if damage:
            from .model_import import ImportDiagnosticError
            raise ImportDiagnosticError('未提取出可用闭合空间；保留破损分析、校正及补接提议，请补充原件或人工绘制边界',
                                        {'damage_analysis': damage, 'regions': regions})
        raise core.ValidationError('未提取出可用闭合空间；请核对裁剪、比例和门洞闭合距离。斜墙/弧墙扫描图暂不适用本算法')
    return {'rooms': rooms, 'warnings': [
        'LOCAL_INFERRED：本地线形态学候选；斜墙、曲墙、家具及重叠标注可能误识，须在原图上逐区核对。',
        f'门窗缺口按 {options.closure_m:g} m 闭合；该操作不是已证实的墙体，未自动推断门窗面积。',
        '未标注区域、排除区域和孔洞清单均保留；OCR 面积只用于误差对照，未用来缩放轮廓。',
        '层高/标高来自导入设置；空调用途、计入面积必须复核。分隔墙间隙需明确邻接依据后才能用于热模型。'],
        'metadata': {'engine': 'OpenCV directional morphology + RapidOCR', 'opencv_version': cv2.__version__,
            'pixels': [width, height], 'crop_px': [x0, y0, x1, y1], 'scale_to_m': factor,
            'scale_basis': options.scale_basis, 'closure_m': options.closure_m, 'regions': regions, 'ocr': doc['ocr'],
            'damage_analysis': damage}}


if __name__ == '__main__':
    try:
        from .model_schema import ImportOptions
        options = ImportOptions.model_validate_json(sys.stdin.buffer.read())
        with contextlib.redirect_stdout(sys.stderr):
            output = recognize(Path(sys.argv[1]), options)
        sys.stdout.write(json.dumps(output, ensure_ascii=False, allow_nan=False))
    except Exception as exc:
        sys.stdout.write(json.dumps({'error': str(exc)[:500], 'diagnostics': getattr(exc, 'diagnostics', None)}, ensure_ascii=False))
        sys.exit(1)
