"""Pinned, optional Windows DWG converter. No download or unrestricted fallback."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sys
import tempfile
import threading

from . import core, execution
from .native_ownership import owned_temporary
from .native_staging import copy_file
from .runtime_lock import safe_path

MIB = 1024**2
_cache = {}
_lock = threading.RLock()


def configuration():
    location = os.environ.get('VRA_DWG_RUNTIME')
    if sys.platform != 'win32' or not location:
        raise core.ValidationError('DWG converter unavailable: configure the verified Windows runtime')
    root = safe_path(Path(location))
    manifest_path = safe_path(root/'manifest.json')
    if manifest_path.stat().st_size > MIB:
        raise core.ValidationError('DWG runtime manifest exceeds budget')
    manifest = core.read_json(manifest_path)
    files = manifest.get('files', {})
    if (manifest.get('schema') != 1 or manifest.get('engine') != 'ACadSharp 3.8.35'
        or manifest.get('framework') != '8.0.21' or not isinstance(files, dict)
        or not 5 <= len(files) <= 300
        or not {'dotnet.exe','Converter.dll','Converter.runtimeconfig.json','ACadSharp.dll',
                'host/fxr/8.0.21/hostfxr.dll'} <= set(files)):
        raise core.ValidationError('Unsupported DWG runtime manifest')
    paths = {}
    for name in files:
        p = Path(name)
        allowed = name in {'dotnet.exe','Converter.dll','Converter.runtimeconfig.json','ACadSharp.dll','host/fxr/8.0.21/hostfxr.dll'}
        allowed |= name.startswith('shared/Microsoft.NETCore.App/8.0.21/') and len(p.parts) == 4 and p.suffix in {'.dll','.json'}
        if not allowed or p.is_absolute() or '..' in p.parts or '\\' in name:
            raise core.ValidationError('Invalid DWG runtime member')
        paths[name] = safe_path(root/p)
    # Trusted admin-installed files: cache only while all file identities/stamps
    # match. Every execution also hashes every byte in its read-only snapshot.
    stamps = tuple((name,p.stat().st_dev,p.stat().st_ino,p.stat().st_size,p.stat().st_mtime_ns,p.stat().st_ctime_ns) for name,p in sorted(paths.items()))
    if sum(s[3] for s in stamps) > 256*MIB:
        raise core.ValidationError('DWG runtime exceeds byte budget')
    identity = core.hash_json({'manifest':manifest,'bridge':core.sha(Path(__file__)),
                               'isolation':core.sha(Path(__file__).with_name('execution.py'))})
    with _lock:
        key = (str(root),identity)
        if _cache.get(key) != stamps:
            if any(core.sha(p) != files[n] for n,p in paths.items()):
                raise core.ValidationError('DWG runtime integrity failed')
            _cache.clear(); _cache[key] = stamps
    return root,manifest,paths,identity


def fingerprint():
    return configuration()[3]


def current():
    try:
        return fingerprint()
    except (OSError,ValueError,KeyError,TypeError):
        return None


def notifications(log):
    if not log.is_file() or log.stat().st_size > 256*1024:
        raise core.ValidationError('DWG diagnostic output missing or oversized')
    rows = []
    done = None
    for line in log.read_text(encoding='utf-8-sig').splitlines():
        item = json.loads(line)
        if not isinstance(item,dict):
            raise core.ValidationError('Invalid DWG diagnostics')
        if item.get('phase') == 'done':
            if done is not None:
                raise core.ValidationError('Duplicate DWG completion receipt')
            done = item
        else:
            if (item.get('phase') not in {'read','write'} or item.get('type') not in {'None','Warning','NotImplemented','NotSupported'}
                or not isinstance(item.get('message'),str) or len(item['message']) > 8000 or len(rows) >= 1000 or done is not None):
                raise core.ValidationError('DWG converter reported error or invalid diagnostics')
            rows.append(item)
    if done is None or type(done.get('entities')) is not int or not 0 <= done['entities'] <= 10000:
        raise core.ValidationError('DWG completion receipt missing or entity budget exceeded')
    return rows,done


@contextmanager
def convert(source):
    try:
        _,manifest,paths,before = configuration()
        from .native_windows import staging
        with staging() as scope, owned_temporary(Path(tempfile.gettempdir())) as control:
            runtime = scope['root']/'runtime'; runtime.mkdir()
            for name,path in paths.items():
                target = runtime/name; target.parent.mkdir(parents=True,exist_ok=True)
                copied = copy_file(path,target,64*MIB)
                if copied['sha256'] != manifest['files'][name]:
                    raise core.ValidationError('DWG runtime changed during staging')
            original = copy_file(source,scope['root']/'input.dwg',10*MIB)
            logs = control/'logs'; logs.mkdir()
            output = scope['work']/'output.dxf'
            receipt = execution.supervise([runtime/'dotnet.exe',runtime/'Converter.dll',scope['root']/'input.dwg',output],
                control,logs,execution.Policy(memory_bytes=1024**3,cpu_seconds=20,output_bytes=16*MIB,
                    output_files=32,log_bytes=256*1024),40,output=scope['work'],
                isolation={'sid':scope['sid'],'work':str(scope['work'])},extra_output_roots=[scope['profile_root']])
            notes,done = notifications(logs/'stdout.log')
            if not output.is_file() or not 0 < output.stat().st_size <= 10*MIB:
                raise core.ValidationError('DWG converted output missing or oversized')
            if fingerprint() != before:
                raise core.ValidationError('DWG runtime changed during conversion')
            yield output,{'engine':manifest['engine'],'runtime_hash':before,'source_sha256':original['sha256'],
                          'notifications':notes,'completion':done,'resource_limits':receipt,
                          'coverage':'partial_not_lossless','original_preserved':True}
    except core.ValidationError:
        raise
    except (OSError,ValueError,RuntimeError,KeyError,TypeError) as exc:
        raise core.ValidationError('DWG isolated conversion failed; original preserved') from exc
