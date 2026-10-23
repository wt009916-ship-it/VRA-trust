"""Bounded, local document workers. Uploaded documents never go to an OCR API."""
import importlib.util
import json
import subprocess
import sys
import threading
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from . import core

MODELS = {'Det': 'PP-OCRv6_det_small.onnx', 'Rec': 'PP-OCRv6_rec_small.onnx',
          'Cls': 'ch_ppocr_mobile_v2.0_cls_mobile.onnx'}
MAX_PAGES = 80
MAX_OCR_PAGES = 20
TIMEOUT = 180
_preview_slots = threading.BoundedSemaphore(2)


def model_paths():
    spec = importlib.util.find_spec('rapidocr')
    if spec is None:
        raise core.ValidationError('本地 OCR 未安装，请管理员安装 backend/requirements.txt')
    root = Path(spec.origin).parent / 'models'
    paths = {k: root / name for k, name in MODELS.items()}
    if not all(p.is_file() for p in paths.values()):
        raise core.ValidationError('本地 OCR 模型不完整，请管理员重新安装 rapidocr==3.10.0；不会在线下载或上传文件')
    return paths


def capability():
    try:
        paths = model_paths()
        return {'available': True, 'engine': 'RapidOCR', 'version': version('rapidocr'),
                'runtime': 'ONNX Runtime CPU ' + version('onnxruntime'),
                'models': [p.name for p in paths.values()], 'max_ocr_pages': MAX_OCR_PAGES,
                'max_text_pages': MAX_PAGES, 'timeout_seconds': TIMEOUT, 'external_upload': False}
    except (core.ValidationError, PackageNotFoundError) as exc:
        return {'available': False, 'error': str(exc), 'external_upload': False}


def worker(path, page=None):
    args = [sys.executable, '-X', 'utf8', '-m', 'backend.document_worker', str(path.resolve())]
    if page is not None:
        args += ['--preview', str(page)]
    try:
        result = subprocess.run(args, cwd=Path(__file__).resolve().parent.parent,
                                capture_output=True, timeout=25 if page is not None else TIMEOUT,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except subprocess.TimeoutExpired as exc:
        raise core.ValidationError('文档处理超时，任务已终止；请拆分页数或降低图片分辨率后重试') from exc
    if result.returncode:
        # The worker returns a bounded JSON error, not library traces or local paths.
        try:
            message = json.loads(result.stdout)['error']
        except (ValueError, KeyError):
            message = '文档处理失败，请核对文件是否损坏、加密或超出限制'
        raise core.ValidationError(message)
    return result.stdout if page is not None else json.loads(result.stdout)


def preview(path, page):
    if not _preview_slots.acquire(blocking=False):
        raise core.ValidationError('预览任务已满，请稍后重试')
    try:
        return worker(path, page)
    finally:
        _preview_slots.release()
