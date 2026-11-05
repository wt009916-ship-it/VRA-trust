"""Process-owned, verified public-code snapshots; never stores task/user data.

Windows grants read/execute to ALL RESTRICTED APPLICATION PACKAGES so fresh
per-task LPAC identities can share public wheels without sharing their inputs.
No original directory ACLs are changed. Forced-process-exit cleanup is not claimed.
"""
import atexit
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import os
from pathlib import Path
import sys
import tempfile
import threading
import time

from . import core, execution
from .native_staging import copy_file
from .private_storage import private_temporary

_lock=threading.RLock()
_entries={}
_contexts=ExitStack()


def close():
    with _lock:
        _contexts.close();_entries.clear()


atexit.register(close)


def _verify_hashes(root,paths,identities):
    """Read every byte on every reuse; bound threads and queued batches to eight.

    Windows first reads of thousands of freshly copied wheel files can stall
    serial verification. Linux and small snapshots retain the serial path.
    Waiting for every batch also closes all readers before an error escapes.
    """
    workers=8 if sys.platform=='win32' and len(paths)>=128 else 1
    started=time.monotonic()
    def check(batch):
        for path in batch:
            if core.sha(path)!=identities[path.relative_to(root).as_posix()]['sha256']:
                raise core.ValidationError('Parser runtime cache identity mismatch')
    if workers==1:check(paths)
    else:
        with ThreadPoolExecutor(max_workers=workers,thread_name_prefix='vra-runtime-verify') as pool:
            futures=[pool.submit(check,paths[index::workers]) for index in range(workers)]
            for future in futures:future.result()
    return {'workers':workers,'files':len(paths),'seconds':time.monotonic()-started}


def get(kind,files,size,fingerprint,maximum,maximum_files):
    # Installed source changes must not silently reuse a different version.
    stamps={}
    for name,path in files.items():
        info=path.stat();stamps[name]=(str(path),info.st_size,info.st_mtime_ns)
    key=core.hash_json({'policy':fingerprint,'files':stamps})
    with _lock:
        cached=_entries.get(kind)
        if cached is not None:
            if cached['key']!=key:raise core.ValidationError('Parser runtime changed; restart service to refresh its verified snapshot')
            observed,_=execution.inventory(cached['root'],maximum,maximum_files)
            if {p.relative_to(cached['root']).as_posix() for p,_ in observed}!=set(cached['identities']):
                raise core.ValidationError('Parser runtime cache inventory changed')
            verification=_verify_hashes(cached['root'],[path for path,_ in observed],cached['identities'])
            return {**cached,'cache_hit':True,'verification':verification}
        with ExitStack() as pending:
            root=pending.enter_context(private_temporary(Path(tempfile.gettempdir())))
            if sys.platform=='win32':
                from .native_windows import _protect_directory,api
                _protect_directory(root,'S-1-15-2-2',False,api())
            identities={};budget=maximum;started=time.monotonic()
            for name,source in sorted(files.items()):
                if time.monotonic()-started>120:raise core.ValidationError('Parser runtime preparation timed out')
                destination=root/name;destination.parent.mkdir(parents=True,exist_ok=True)
                item=copy_file(source,destination,budget);budget-=item['bytes'];identities[name]=item
                if sys.platform=='linux':os.chmod(destination,0o400)
            if maximum-budget!=size:raise core.ValidationError('Parser runtime source changed during snapshot')
            # Public code and wheel bytes only. Inputs/output/profile live elsewhere.
            cached={'root':root,'key':key,'identities':identities,'bytes':size,'files':len(identities),
                    'hash':core.hash_json(identities)}
            _contexts.enter_context(pending.pop_all());_entries[kind]=cached
            return {**cached,'cache_hit':False,'verification':{'workers':1,'files':len(identities),
                    'seconds':time.monotonic()-started,'method':'hash_during_bounded_copy'}}
