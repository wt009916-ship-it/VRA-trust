"""Pinned public embedding artifacts; no download or model-supplied code at inference."""
import os
from pathlib import Path
from . import core
from .runtime_lock import safe_path

MODEL_ID = 'Xenova/bge-small-zh-v1.5'
REVISION = '75c43b069aac4d136ba6bc1122f995fedcfd2781'
ARTIFACTS = {
    'onnx/model.onnx': '69a0b846f4f116b5e6aabf9546ea6754d02264f3211a13a1bd69b31b8040749a',
    'tokenizer.json': '48cea5d44424912a6fd1ea647bf4fe50b55ab8b1e5879c3275f80e339e8fae26',
}


def paths():
    location = os.environ.get('VRA_SEMANTIC_MODEL_DIR')
    if not location:
        raise core.ValidationError('Local semantic retrieval is not configured')
    root = safe_path(Path(location))
    result = {name: safe_path(root/name) for name in ARTIFACTS}
    for name, path in result.items():
        if not path.is_file() or core.sha(path) != ARTIFACTS[name]:
            raise core.ValidationError('Semantic model absent or hash mismatch; no lexical fallback')
    return result
