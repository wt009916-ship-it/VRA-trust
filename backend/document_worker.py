"""One disposable process per document, with a parent-enforced deadline."""
import contextlib
import io
import json
import sys
from pathlib import Path

from . import core
from .document_reader import MAX_OCR_PAGES, MAX_PAGES, capability, model_paths

MAX_PIXELS = 30_000_000
MAX_SIDE = 2400


def raster(path, page=1):
    from PIL import Image, ImageOps
    if path.suffix.lower() == '.pdf':
        import pypdfium2 as pdfium
        with pdfium.PdfDocument(path) as doc:
            if not 1 <= page <= len(doc):
                raise core.ValidationError('页码不存在')
            source = doc[page - 1]
            try:
                width, height = source.get_size()
                if width <= 0 or height <= 0:
                    raise core.ValidationError('PDF 页面尺寸无效')
                scale = min(2.0, MAX_SIDE / max(width, height))
                bitmap = source.render(scale=scale)
                try:
                    return bitmap.to_pil().convert('RGB')
                finally:
                    bitmap.close()
            finally:
                source.close()
    if page != 1:
        raise core.ValidationError('图片只有第 1 页')
    with Image.open(path) as source:
        if source.width * source.height > MAX_PIXELS:
            raise core.ValidationError('图片超过 3000 万像素，请缩小或裁剪后上传')
        image = ImageOps.exif_transpose(source).convert('RGB')
        image.thumbnail((MAX_SIDE, MAX_SIDE))
        return image


def read(path):
    pages, warnings, engine = [], [], None
    provenance = None

    def recognize(image):
        nonlocal engine, provenance
        if engine is None:
            from rapidocr import RapidOCR
            paths = model_paths()  # Explicit paths prohibit automatic model download.
            params = {f'{k}.model_path': str(p) for k, p in paths.items()}
            params.update({'Global.log_level': 'error', 'Global.max_side_len': MAX_SIDE,
                           'EngineConfig.onnxruntime.intra_op_num_threads': 2,
                           'EngineConfig.onnxruntime.inter_op_num_threads': 1})
            engine = RapidOCR(params=params)
            provenance = {**capability(), 'model_hashes': {p.name: core.sha(p) for p in paths.values()}}
        result = engine(image)
        return [{'text': str(text)[:2000], 'confidence': round(float(score), 4),
                 'box': [[round(float(v), 2) for v in point] for point in box]}
                for text, score, box in zip(result.txts or [], result.scores or [],
                                            [] if result.boxes is None else result.boxes)][:2000]

    def scanned(number):
        image = raster(path, number)
        try:
            lines = recognize(image)
            return {'page': number, 'method': 'ocr', 'width': image.width, 'height': image.height,
                    'lines': lines, 'text': '\n'.join(line['text'] for line in lines)[:30000]}
        finally:
            image.close()

    if path.suffix.lower() == '.pdf':
        import pdfplumber
        ocr_count = 0
        with pdfplumber.open(path) as pdf:
            total = len(pdf.pages)
            for number, page in enumerate(pdf.pages[:MAX_PAGES], 1):
                text = (page.extract_text() or '')[:30000]
                # Hybrid drawing PDFs contain selectable captions plus raster labels.
                scan_coverage = max((max(0, float(i['width'])) * max(0, float(i['height'])) /
                                     max(1, float(page.width * page.height)) for i in page.images), default=0)
                needs_ocr = not text.strip() or scan_coverage > .25
                if needs_ocr and ocr_count < MAX_OCR_PAGES:
                    ocr_count += 1
                    try:
                        result = scanned(number)
                        result['native_text'] = text
                        pages.append(result)
                    except Exception as exc:
                        pages.append({'page': number, 'method': 'failed', 'text': text, 'error': str(exc)[:500]})
                        warnings.append(f'第 {number} 页 OCR 失败，请人工核对或重新上传。')
                elif needs_ocr:
                    pages.append({'page': number, 'method': 'skipped', 'text': text})
                    warnings.append(f'第 {number} 页未做 OCR：达到每份 {MAX_OCR_PAGES} 页上限。')
                else:
                    pages.append({'page': number, 'method': 'text', 'text': text})
            if total > MAX_PAGES:
                warnings.append(f'只处理前 {MAX_PAGES} 页，其余页未分析，请拆分上传。')
    else:
        total = 1
        pages.append(scanned(1))
    if not any(p['text'].strip() for p in pages):
        warnings.append('未识别到可读文字，请检查清晰度、旋转方向或手动校正；未补入猜测内容。')
    return {'pages': total, 'document_pages': pages, 'ocr': provenance,
            'text_preview': [{'page': p['page'], 'text': p['text'][:1600]} for p in pages[:3]],
            'warnings': warnings}


if __name__ == '__main__':
    try:
        path = Path(sys.argv[1])
        with contextlib.redirect_stdout(sys.stderr):
            if len(sys.argv) > 2:
                image = raster(path, int(sys.argv[3]))
                with image, io.BytesIO() as buffer:
                    image.save(buffer, format='PNG')
                    output = buffer.getvalue()
            else:
                output = json.dumps(read(path), ensure_ascii=False, allow_nan=False).encode('utf-8')
        sys.stdout.buffer.write(output)
    except Exception as exc:
        sys.stdout.buffer.write(json.dumps({'error': str(exc)[:500]}, ensure_ascii=False).encode('utf-8'))
        sys.exit(1)
