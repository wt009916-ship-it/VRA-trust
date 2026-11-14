"""Pinned upstream OCR artifacts; this application does not download models at inference."""
from hashlib import sha256
from importlib.metadata import distribution, version

MODELS = {
    'Det': ('PP-OCRv6_det_small.onnx', '090f04abcd9d9a7498bc4ebf677e4cb9bdce1fe4197ddb7e529f1ef44e1ff94f'),
    'Rec': ('PP-OCRv6_rec_small.onnx', '6f327246b50388f3c176ae304bd95767ea6dc0c9ae92153ef8cbe210b3c14884'),
    'Cls': ('ch_ppocr_mobile_v2.0_cls_mobile.onnx', 'e47acedf663230f8863ff1ab0e64dd2d82b838fceb5957146dab185a89d6215c'),
}


def model_paths():
    if version('rapidocr') != '3.10.0':
        raise ValueError('OCR package version differs from validated model contract')
    root = distribution('rapidocr').locate_file('rapidocr/models')
    paths = {}
    for kind, (name, digest) in MODELS.items():
        path = root/name
        if not path.is_file() or sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('OCR model absent or hash mismatch; reinstall pinned dependency')
        paths[kind] = str(path)
    return paths
