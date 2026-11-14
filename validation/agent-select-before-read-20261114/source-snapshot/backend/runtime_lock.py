"""Cooperative local service/maintenance exclusion; not an OS security sandbox."""
import os
import stat
import sys
import threading
from functools import wraps
from pathlib import Path

_mutex = threading.RLock()
_leases = {}


def safe_path(path):
    """Reject symlinks/junctions before resolving a local maintenance path."""
    path = Path(os.path.abspath(path))
    for part in [*reversed(path.parents), path]:
        if part.exists() or part.is_symlink():
            info = part.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
                raise ValueError('Linked/reparse maintenance paths are not allowed')
    return path


class RuntimeLease:
    def __init__(self, root, mode='service'):
        if mode not in {'service', 'maintenance'}:
            raise ValueError('Unknown lease mode')
        self.root, self.mode, self.active = safe_path(root), mode, False

    def __enter__(self):
        with _mutex:
            key = os.path.normcase(str(self.root))
            held = _leases.get(key)
            if held:
                if self.mode != 'service' or held['mode'] != 'service':
                    raise ValueError('Data directory busy; stop the application and background tasks first')
                held['count'] += 1
            else:
                self.root.mkdir(parents=True, exist_ok=True)
                path = safe_path(self.root / '.vra.lock')
                stream = path.open('a+b')
                try:
                    stream.seek(0)
                    if sys.platform == 'win32':
                        import msvcrt
                        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                    elif sys.platform == 'linux':
                        import fcntl
                        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    else:
                        raise ValueError('Runtime locking requires Windows or Linux')
                except OSError:
                    stream.close()
                    raise ValueError('Data directory busy; another process holds the runtime lock') from None
                except Exception:
                    stream.close()
                    raise
                _leases[key] = {'stream': stream, 'mode': self.mode, 'count': 1}
            self.key, self.active = key, True
        return self

    def __exit__(self, *_):
        with _mutex:
            if self.active:
                held = _leases[self.key]
                held['count'] -= 1
                if held['count'] == 0:
                    held['stream'].close()  # OS releases the lock, including after process death.
                    del _leases[self.key]
                self.active = False


def runtime_operation(function):
    @wraps(function)
    def guarded(self, *args, **kwargs):
        with RuntimeLease(self.store.root):
            return function(self, *args, **kwargs)
    return guarded
