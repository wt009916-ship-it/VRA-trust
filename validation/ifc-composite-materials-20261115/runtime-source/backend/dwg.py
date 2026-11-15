"""DWG -> derived DXF -> existing strict parser, with current dependency gates."""
import shutil
import threading

from . import core, parser_runtime, dwg_runtime
from .domain import identifier
from .runtime_lock import safe_path, runtime_operation

_capacity = threading.BoundedSemaphore(1)


@runtime_operation
def inspect(cad,pid,body):
    source,path = cad.domain.file_record(pid,body.file_id)
    if path.suffix.lower() != '.dwg' or source['size'] > 10*1024**2:
        raise core.ValidationError('DWG conversion accepts files up to 10 MiB')
    if not _capacity.acquire(False):
        raise core.ValidationError('DWG converter busy; retry later')
    try:
        if len([r for r in cad.store.list('cad',pid) if r.get('conversion')]) >= 20:
            raise core.ValidationError('Project DWG conversion record limit is 20')
        from .cad import parser_version
        before = parser_version()
        with dwg_runtime.convert(path) as (converted,conversion):
            with parser_runtime.run('cad',converted) as scope:
                output = scope['work']/'result.json'
                if not output.is_file() or output.stat().st_size > 8*1024**2:
                    raise core.ValidationError('Converted DXF strict parsing output missing or oversized')
                result = core.read_json(output)
                if result.get('error') or result.get('format') != 'DXF':
                    raise core.ValidationError('Converted DXF failed strict inspection; original preserved')
                result['resource_limits'] = scope['resource_limits']
            current,_ = cad.domain.file_record(pid,body.file_id)
            if (current['hash'] != conversion['source_sha256'] or current['hash'] != source['hash']
                or parser_version() != before or dwg_runtime.current() != conversion['runtime_hash']):
                raise core.ValidationError('DWG source or runtime changed during processing')
            if shutil.disk_usage(cad.store.root).free < 256*1024**2 + converted.stat().st_size:
                raise core.ValidationError('Insufficient space to preserve converted DXF safely')
            cid = identifier('cad')
            folder = safe_path(cad.store.root/'conversions'/cid)
            folder.mkdir(parents=True,exist_ok=False)
            target = folder/'converted.dxf'
            from .native_staging import copy_file
            copied = copy_file(converted,target,10*1024**2)
            obj = {'cad_id':cid,'project_id':pid,'source':source,'created_at':core.now(),
                   'parser_hash':before,'result':result,'conversion':conversion,
                   'derivative':{'path':target.relative_to(cad.store.root).as_posix(),'sha256':copied['sha256'],'size':copied['bytes']}}
        obj['hash'] = core.hash_json(obj)
        cad.store.put('cad',obj)
        return cad.view(pid,cid)
    finally:
        _capacity.release()


def state(cad,obj,current_runtime):
    if not obj.get('conversion'):
        return []
    reasons = []
    if current_runtime is None:
        reasons.append('converter_unavailable')
    elif current_runtime != obj['conversion']['runtime_hash']:
        reasons.append('converter_changed')
    try:
        path = core.relative_file(cad.store.root,obj['derivative']['path'])
        if core.sha(path) != obj['derivative']['sha256']:
            reasons.append('converted_file_changed')
    except (OSError,ValueError,KeyError):
        reasons.append('converted_file_unavailable')
    return reasons


def download(cad,pid,cid):
    obj = cad.view(pid,cid)
    if obj['status'] != 'parsed' or not obj.get('conversion'):
        raise core.ValidationError('Converted DXF unavailable or stale; no current download')
    return core.relative_file(cad.store.root,obj['derivative']['path'])
