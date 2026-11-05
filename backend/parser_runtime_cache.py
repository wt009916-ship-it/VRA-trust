"""Process-owned, verified public-code snapshots; never stores task/user data.

Windows grants read/execute to ALL RESTRICTED APPLICATION PACKAGES so fresh
per-task LPAC identities can share public wheels without sharing their inputs.
No original directory ACLs are changed. Forced-process-exit cleanup is not claimed.
"""
import atexit
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


def get(kind,files,size,fingerprint,maximum,maximum_files):
    # Installed source changes must not silently reuse a different version.
    stamps={name:(str(p),p.stat().st_size,p.stat().st_mtime_ns) for name,p in files.items()}
    key=core.hash_json({'policy':fingerprint,'files':stamps})
    with _lock:
        cached=_entries.get(kind)
        if cached is not None:
            if cached['key']!=key:raise core.ValidationError('Parser runtime changed; restart service to refresh its verified snapshot')
            observed,_=execution.inventory(cached['root'],maximum,maximum_files)
            if {p.relative_to(cached['root']).as_posix() for p,_ in observed}!=set(cached['identities']):
                raise core.ValidationError('Parser runtime cache inventory changed')
            for path,_ in observed:
                if core.sha(path)!=cached['identities'][path.relative_to(cached['root']).as_posix()]['sha256']:
                    raise core.ValidationError('Parser runtime cache identity mismatch')
            return {**cached,'cache_hit':True}
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
            return {**cached,'cache_hit':False}
