"""Local ONNX ranking, invoked only inside the native filesystem/network boundary."""
import json
import math
import os
import sys
from pathlib import Path

PREFIX = '为这个句子生成表示以用于检索相关文章：'
MAX_DOCUMENTS = 2000
MAX_CHARACTERS = 500000
MAX_CHUNKS = 2000


def validate(body):
    if not isinstance(body, dict) or set(body) != {'query', 'documents'}:
        raise ValueError('Invalid semantic request')
    query, docs = body['query'], body['documents']
    if not isinstance(query, str) or not query.strip() or len(query) > 1000:
        raise ValueError('Invalid semantic query')
    if not isinstance(docs, list) or not 1 <= len(docs) <= MAX_DOCUMENTS:
        raise ValueError('Narrow semantic corpus to at most 2000 clauses')
    keys = set()
    for doc in docs:
        if not isinstance(doc, dict) or set(doc) != {'key', 'text'}:
            raise ValueError('Invalid semantic document')
        if not isinstance(doc['key'], str) or not 1 <= len(doc['key']) <= 100 or doc['key'] in keys:
            raise ValueError('Invalid semantic key')
        if not isinstance(doc['text'], str) or not 1 <= len(doc['text']) <= 8000:
            raise ValueError('Invalid semantic source text')
        keys.add(doc['key'])
    if sum(len(d['text']) for d in docs) > MAX_CHARACTERS:
        raise ValueError('Narrow semantic corpus; character budget exceeded')


def rank(body, model_root):
    validate(body)
    import numpy as np
    import onnxruntime as ort
    from tokenizers import Tokenizer
    tokenizer = Tokenizer.from_file(str(model_root/'tokenizer.json'))
    tokenizer.no_padding(); tokenizer.no_truncation()
    query = tokenizer.encode(PREFIX + body['query'])
    if len(query.ids) > 512:
        raise ValueError('Query exceeds model token budget; narrow it, do not truncate')
    tokenizer.enable_truncation(max_length=512, stride=64)
    segments = []
    for doc in body['documents']:
        encoded = tokenizer.encode(doc['text'])
        for part in [encoded, *encoded.overflowing]:
            positions = [(a, b) for a, b in part.offsets if b > a]
            if not positions:
                raise ValueError('Document has no encodable source span')
            start, end = min(a for a, b in positions), max(b for a, b in positions)
            if not 0 <= start < end <= len(doc['text']):
                raise ValueError('Invalid source character offsets')
            segments.append((doc['key'], start, end, part))
            if len(segments) > MAX_CHUNKS:
                raise ValueError('Narrow semantic corpus; chunk budget exceeded')
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2; options.inter_op_num_threads = 1
    session = ort.InferenceSession(str(model_root/'onnx/model.onnx'), sess_options=options, providers=['CPUExecutionProvider'])
    if {i.name for i in session.get_inputs()} != {'input_ids', 'attention_mask', 'token_type_ids'}:
        raise ValueError('Unexpected embedding model inputs')

    def embed(parts):
        length = max(len(p.ids) for p in parts)
        if length > 512:
            raise ValueError('Embedding token budget exceeded')
        def array(field):
            return np.array([getattr(p, field) + [0] * (length - len(p.ids)) for p in parts], dtype=np.int64)
        value = session.run(None, {'input_ids': array('ids'), 'attention_mask': array('attention_mask'),
                                  'token_type_ids': array('type_ids')})[0]
        if value.shape != (len(parts), length, 512) or not np.isfinite(value).all():
            raise ValueError('Invalid model output')
        cls = value[:, 0, :]; norm = np.linalg.norm(cls, axis=1, keepdims=True)
        if not (norm > 0).all():
            raise ValueError('Invalid vector norm')
        return cls / norm

    qv = embed([query])[0]; best = {}
    for start in range(0, len(segments), 8):
        batch = segments[start:start+8]
        scores = embed([s[3] for s in batch]) @ qv
        for (key, a, b, _), score in zip(batch, scores):
            score = float(score)
            if not math.isfinite(score) or not -1.00001 <= score <= 1.00001:
                raise ValueError('Invalid cosine score')
            score = max(-1.0, min(1.0, score))
            if key not in best or score > best[key]['score']:
                best[key] = {'key': key, 'score': score, 'span': [a, b]}
    return {'rankings': sorted(best.values(), key=lambda r: (-r['score'], r['key'])),
            'documents': len(body['documents']), 'chunks': len(segments), 'truncated': False}


def main():
    source, target, model = map(Path, sys.argv[1:])
    os.environ.update(HF_HUB_OFFLINE='1', TOKENIZERS_PARALLELISM='false')
    for name in ('HOME', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'XDG_CACHE_HOME'):
        os.environ[name] = str(target.parent)
    if not 0 < source.stat().st_size <= 2 * 1024**2:
        raise ValueError('Semantic input exceeds budget')
    result = rank(json.loads(source.read_text(encoding='utf-8')), model)
    target.write_text(json.dumps(result, allow_nan=False), encoding='utf-8')


if __name__ == '__main__':
    main()
