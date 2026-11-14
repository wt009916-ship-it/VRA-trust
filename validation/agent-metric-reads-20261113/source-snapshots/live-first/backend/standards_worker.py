"""Bounded PDF text extraction in a disposable subprocess; no OCR or URL fetch."""
if __name__ == '__main__':
    from worker_limits import initialize
    initialize('standards')

import json
import sys
from pathlib import Path
from pypdf import PdfReader, PdfWriter
import hashlib
import re


def extract(path):
    if path.stat().st_size > 20*1024*1024 or path.read_bytes()[:5] != b'%PDF-':
        raise ValueError('Expected PDF up to 20 MiB')
    reader = PdfReader(path, strict=True)
    if reader.is_encrypted:
        raise ValueError('Encrypted PDF is not supported')
    if not 0 < len(reader.pages) <= 500:
        raise ValueError('PDF page count must be 1–500')
    pages, total = [], 0
    for index, page in enumerate(reader.pages):
        text = page.extract_text() or ''
        total += len(text)
        if len(text) > 40000 or total > 400000:
            raise ValueError('PDF text budget exceeded')
        # Preserve raw text. This named-watermark heuristic is advisory only;
        # it must not certify that any remaining characters are usable body text.
        remainder=re.sub(r'\s+', '', text)
        for mark in ('住房城乡建设部信息公开','浏览专用'): remainder=remainder.replace(mark,'')
        pages.append({'pdf_page': index+1, 'text': text,
                      'text_layer_assessment':'empty' if not text.strip() else
                          'known_watermark_only' if not remainder else 'unverified_text'})
    return {'page_count': len(pages), 'text_pages': sum(bool(p['text'].strip()) for p in pages),
            'pages': pages, 'ocr_performed': False}


def select_page(path, number, target):
    if not 0<path.stat().st_size<=20*1024**2 or path.read_bytes()[:5]!=b'%PDF-':
        raise ValueError('Expected PDF up to 20 MiB')
    reader=PdfReader(path,strict=True)
    if reader.is_encrypted or not 1<=number<=len(reader.pages)<=500:
        raise ValueError('Encrypted PDF or page outside supported range')
    writer=PdfWriter();writer.add_page(reader.pages[number-1]);writer.write(target)
    if not 0<target.stat().st_size<=10*1024**2: raise ValueError('Selected page exceeds OCR budget')
    return {'original_pdf_page':number,'page_count':len(reader.pages),
            'selected_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
            'operation':'single_page_copy_not_original','ocr_performed':False}


if __name__ == '__main__':
    try:
        result = extract(Path(sys.argv[1]))
    except Exception as exc:
        Path(sys.argv[2]).write_text(json.dumps({'error': type(exc).__name__}), encoding='utf-8')
        sys.exit(1)
    Path(sys.argv[2]).write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
