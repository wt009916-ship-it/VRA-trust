"""Offline image/PDF-page OCR. Candidates never become engineering parameters."""
import hashlib
import json
import math
import socket
import sys
import warnings
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_PIXELS = 12000000
MAX_SIDE = 6000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


def load_page(path, page_number):
    if not 0 < path.stat().st_size <= 10*1024*1024:
        raise ValueError('Drawing must be 1 byte..10 MiB')
    if path.suffix.lower() == '.pdf':
        import pypdfium2 as pdfium
        with pdfium.PdfDocument(path) as doc:
            count = len(doc)
            if not 1 <= page_number <= count <= 200:
                raise ValueError('PDF page outside supported range 1..200')
            page = doc[page_number-1]
            width, height = page.get_size()
            scale = 150/72
            # Match PDFium's ceil for each dimension (including floating-point
            # rounding), before native allocation; continuous area can undercount.
            if not all(math.isfinite(x) and x > 0 for x in (width,height)):
                raise ValueError('Invalid PDF page size')
            raster_size = (math.ceil(width*scale), math.ceil(height*scale))
            if raster_size[0]*raster_size[1] > MAX_PIXELS or max(raster_size) > MAX_SIDE:
                raise ValueError('PDF raster page exceeds pixel budget at 150 dpi')
            bitmap = page.render(scale=scale)
            image = bitmap.to_pil().copy()
            bitmap.close(); page.close()
        info = {'kind':'pdf_raster','page':page_number,'page_count':count,'dpi':150,
                'raster_rounding':'ceil per axis, matching PDFium; coordinates refer to actual raster pixels',
                'orientation':'PDF page rotation applied by PDFium'}
    elif path.suffix.lower() in {'.png','.jpg','.jpeg'}:
        if page_number != 1:
            raise ValueError('Raster image supports page 1 only')
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            try:
                source = Image.open(path, formats=('PNG','JPEG'))
            except UnidentifiedImageError as exc:
                raise ValueError('Only single-frame PNG/JPEG supported') from exc
            with source:
                if source.format not in {'PNG','JPEG'} or getattr(source,'n_frames',1) != 1:
                    raise ValueError('Only single-frame PNG/JPEG supported')
                if source.width*source.height > MAX_PIXELS or max(source.size) > MAX_SIDE or min(source.size) < 32:
                    raise ValueError('Raster dimensions exceed supported budget')
                orientation = source.getexif().get(274,1)
                image = ImageOps.exif_transpose(source).copy()
        info = {'kind':'raster','page':1,'page_count':1,'exif_orientation':orientation,'orientation':'EXIF orientation applied; boxes refer to normalized preview'}
    else:
        raise ValueError('Unsupported drawing format')
    rgba = image.convert('RGBA')
    background = Image.new('RGBA',rgba.size,'white')
    image = Image.alpha_composite(background,rgba).convert('RGB')
    return image, info


def parse(path, page_number, preview_path):
    if __package__:
        from .drawing_models import model_paths, MODELS
    else:
        from drawing_models import model_paths, MODELS
    paths = model_paths()
    image, info = load_page(path,page_number)
    import onnxruntime
    from rapidocr import RapidOCR
    onnxruntime.disable_telemetry_events()
    # All input is a local decoded raster; fail if a dependency attempts Python networking.
    def offline(*args, **kwargs):
        raise RuntimeError('Network disabled in OCR worker')
    socket.create_connection = offline
    socket.socket.connect = offline
    socket.socket.connect_ex = offline
    params = {f'{kind}.model_path':value for kind,value in paths.items()}
    params.update({'EngineConfig.onnxruntime.intra_op_num_threads':2,'EngineConfig.onnxruntime.inter_op_num_threads':1,
                   'Global.log_level':'error','Global.max_side_len':4000,'Global.text_score':0.,
                   'Det.limit_side_len':1600,'Det.limit_type':'max','Det.max_candidates':1000})
    engine = RapidOCR(params=params)
    output = engine(image,text_score=0.)
    boxes, texts, scores = output.boxes, output.txts, output.scores
    candidates = []
    if texts is not None:
        if boxes is None or scores is None or not len(texts) == len(boxes) == len(scores) or len(texts) > 500:
            raise ValueError('OCR output exceeds candidate budget or is inconsistent')
        for i,(box,text,score) in enumerate(zip(boxes,texts,scores)):
            polygon = [[float(x),float(y)] for x,y in box]
            score = float(score)
            if len(polygon)!=4 or not math.isfinite(score) or not 0<=score<=1 or not isinstance(text,str) or len(text)>2000:
                raise ValueError('Invalid OCR candidate')
            if not all(math.isfinite(x) and math.isfinite(y) and 0<=x<=image.width and 0<=y<=image.height for x,y in polygon):
                raise ValueError('OCR polygon outside normalized image')
            candidates.append({'candidate_id':f'text_{i+1}','text':text,'polygon_px':polygon,
                               'recognition_score':score,'review_required':True,'source_kind':'AI_INFERRED'})
    image.save(preview_path,format='PNG')
    return {'page':info,'width':image.width,'height':image.height,'candidates':candidates,
            'state':'candidates_require_review' if candidates else 'no_text_detected_not_proof_of_absence',
            'preview_sha256':hashlib.sha256(preview_path.read_bytes()).hexdigest(),
            'models':{kind:{'name':name,'sha256':digest} for kind,(name,digest) in MODELS.items()},
            'settings':{k:v for k,v in params.items() if not k.endswith('.model_path')},
            'limitations':['识别分数不是正确概率或工程可信度，漏检和高分误识别仍可能发生；所有候选均需人工核对。',
                           '文字与位置是AI候选，不推断缺失尺寸、构件、比例尺或结构安全，不自动写入工程参数。',
                           '仅做方向规范化、白底合成或PDF光栅化；没有修补墙线或生成缺失工程信息，原件保持不变。',
                           '检测最长边缩至1600像素；小字、噪声、重叠和复杂图纸可能遗漏，未识别不表示不存在。',
                           '框坐标基于当前规范化预览；不直接对应PDF矢量坐标或工程长度单位。']}


if __name__ == '__main__':
    try:
        path,out,preview=map(Path,(sys.argv[1],sys.argv[2],sys.argv[3]))
        result=parse(path,int(sys.argv[4]),preview)
        text=json.dumps(result,ensure_ascii=False,allow_nan=False)
        if len(text.encode('utf-8'))>2*1024*1024:
            raise ValueError('OCR result exceeds budget')
        out.write_text(text,encoding='utf-8')
    except Exception as exc:
        Path(sys.argv[2]).write_text(json.dumps({'error':type(exc).__name__}),encoding='utf-8')
        sys.exit(1)
