"""Disposable local embedding worker with verified public runtime and no network."""
from dataclasses import replace
from importlib.metadata import distribution
import json
import math
from pathlib import Path, PurePosixPath
import shutil
import sys
import tempfile
import threading
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from . import core, execution, parser_runtime, parser_runtime_cache, semantic_models
from .native_ownership import owned_temporary
from .native_staging import copy_file
from .runtime_lock import safe_path
from .semantic_worker import validate

ROOT = Path(__file__).resolve().parent
_capacity = threading.BoundedSemaphore(1)
POLICY = {'memory_bytes': 2 * 1024**3, 'cpu_seconds': 60, 'output_bytes': 2 * 1024**2,
          'output_files': 16, 'log_bytes': 256 * 1024}


def dependencies():
    pending = ['onnxruntime', 'numpy', 'tokenizers']; found = {}
    while pending:
        name = canonicalize_name(pending.pop())
        if name in found:
            continue
        if len(found) >= 64:
            raise ValueError('Semantic dependency count exceeded')
        dist = distribution(name); found[name] = dist
        for value in dist.requires or ():
            requirement = Requirement(value)
            if requirement.marker and not requirement.marker.evaluate({'extra': ''}):
                continue
            if requirement.url or requirement.extras:
                raise ValueError('Unsupported semantic dependency declaration')
            installed = distribution(requirement.name)
            if not requirement.specifier.contains(installed.version, prereleases=True):
                raise ValueError('Semantic dependency version mismatch')
            pending.append(requirement.name)
    if found['tokenizers'].version != '0.22.1':
        raise ValueError('Semantic tokenizer version differs from validated runtime')
    return found


def identity():
    try:
        semantic_models.paths()
        return core.hash_json({'base': parser_runtime.identity('standards'), 'model': semantic_models.ARTIFACTS,
            'modules': {n: core.sha(ROOT/n) for n in ('semantic_models.py', 'semantic_runtime.py', 'semantic_worker.py')},
            'dependencies': {k: v.version for k, v in dependencies().items()}, 'policy': POLICY})
    except (ValueError, OSError, ImportError) as exc:
        raise core.ValidationError('Semantic runtime unavailable or changed') from exc


def plan():
    # Reuse the verified Python/stdlib plan; it contains no user or project files.
    files, _ = parser_runtime.plan('standards')
    for dist in dependencies().values():
        base = safe_path(dist.locate_file(''))
        for entry in dist.files or ():
            relative = PurePosixPath(str(entry))
            if relative.is_absolute() or '..' in relative.parts or '__pycache__' in relative.parts or relative.suffix in {'.pyc', '.pth'}:
                continue
            path = safe_path(base/Path(relative)); name = 'packages/' + relative.as_posix()
            if name in files and files[name] != path:
                raise ValueError('Runtime destination collision')
            files[name] = path
    files['code/semantic_worker.py'] = ROOT/'semantic_worker.py'
    for name, path in semantic_models.paths().items():
        files['model/' + name] = path
    size = sum(p.stat().st_size for p in files.values())
    if len(files) > 20000 or size > 1024**3:
        raise ValueError('Semantic runtime exceeds staging budget')
    return files, size


def rank(query, documents):
    body = {'query': query, 'documents': documents}
    try:
        validate(body)
    except ValueError as exc:
        raise core.ValidationError(str(exc)) from exc
    encoded = json.dumps(body, ensure_ascii=False, allow_nan=False).encode('utf-8')
    if len(encoded) > 2 * 1024**2:
        raise core.ValidationError('Narrow semantic corpus; input byte budget exceeded')
    if not _capacity.acquire(False):
        raise core.ValidationError('Semantic retrieval busy; retry later')
    try:
        fingerprint = identity(); files, size = plan()
        if shutil.disk_usage(tempfile.gettempdir()).free < size + 128 * 1024**2:
            raise core.ValidationError('Insufficient temporary space for semantic retrieval')
        runtime = parser_runtime_cache.get('semantic', files, size, fingerprint, 1024**3, 20000)
        with parser_runtime._workspace() as scope, owned_temporary(Path(tempfile.gettempdir())) as control:
            root, work = scope['root'], scope['work']; cached = runtime['root']
            source = control/'request.json'; source.write_bytes(encoded)
            input_path = root/'request.json'; copied = copy_file(source, input_path, 2 * 1024**2)
            if copied['sha256'] != core.sha(source):
                raise core.ValidationError('Semantic input changed during staging')
            if sys.platform == 'linux':
                scope['isolation']['read_paths'].append(str(cached)); input_path.chmod(0o400)
            python = cached/'python/python.exe' if sys.platform == 'win32' else scope['python']
            args = [str(cached/'code/semantic_worker.py'), str(input_path), str(work/'result.json'), str(cached/'model')]
            bootstrap = 'import sys,runpy;sys.path[:0]=' + repr([str(cached/'code'), str(cached/'packages')]) + ';sys.argv=' + repr(args) + ';runpy.run_path(sys.argv[0],run_name="__main__")'
            logs = control/'logs'; logs.mkdir()
            try:
                receipt = execution.supervise([python, '-I', '-B', '-S', '-X', 'utf8', '-c', bootstrap], control, logs,
                    replace(execution.Policy(), **POLICY), 75, output=work, isolation=scope['isolation'], extra_output_roots=scope['extra_roots'])
            except execution.ExecutionError as exc:
                exc.parser_stderr = (logs/'stderr.log').read_text(encoding='utf-8', errors='replace') if (logs/'stderr.log').exists() else ''
                raise core.ValidationError('Isolated semantic execution failed; no substitute result') from exc
            result = core.read_json(work/'result.json')
            validate_result(result, documents)
            if identity() != fingerprint:
                raise core.ValidationError('Semantic runtime changed')
            return {**result, 'runtime_hash': fingerprint, 'model': semantic_models.MODEL_ID, 'revision': semantic_models.REVISION,
                    'resource_limits': {'enforced': True, 'execution_receipt': receipt, 'runtime_cache_hit': runtime['cache_hit'],
                                        'input_sha256': copied['sha256'], 'runtime_hash': runtime['hash']}}
    except core.ValidationError:
        raise
    except (OSError, ValueError, RuntimeError, ImportError, KeyError, TypeError) as exc:
        raise core.ValidationError('Semantic retrieval unavailable or invalid; no lexical fallback') from exc
    finally:
        _capacity.release()


def validate_result(result, documents):
    expected = {d['key']: d['text'] for d in documents}
    if not isinstance(result, dict) or set(result) != {'rankings', 'documents', 'chunks', 'truncated'}:
        raise core.ValidationError('Invalid semantic result')
    if type(result['documents']) is not int or result['documents'] != len(documents) or result['truncated'] is not False or type(result['chunks']) is not int or not len(documents) <= result['chunks'] <= 2000:
        raise core.ValidationError('Incomplete semantic coverage')
    rankings = result['rankings']
    if not isinstance(rankings, list) or len(rankings) != len(expected):
        raise core.ValidationError('Missing semantic source rankings')
    seen = set()
    for row in rankings:
        if not isinstance(row, dict) or set(row) != {'key', 'score', 'span'} or row['key'] not in expected or row['key'] in seen:
            raise core.ValidationError('Unknown or duplicate semantic source')
        seen.add(row['key']); span = row['span']; score = row['score']
        if type(score) not in (int, float) or not math.isfinite(score) or not -1 <= score <= 1:
            raise core.ValidationError('Invalid semantic score')
        if not isinstance(span, list) or len(span) != 2 or any(type(n) is not int for n in span) or not 0 <= span[0] < span[1] <= len(expected[row['key']]):
            raise core.ValidationError('Invalid semantic source span')
    if rankings != sorted(rankings, key=lambda r: (-r['score'], r['key'])):
        raise core.ValidationError('Invalid semantic ranking order')
