"""Private native workspace journal and kernel-held leases.

Recovery never searches arbitrary temporary folders or terminates a PID. Only
entries created beneath this account's dedicated registry are eligible. Active
leases are inherited by the trusted supervisor, not by untrusted native code.
Administrators and malicious same-account processes remain outside the boundary.
"""
from contextlib import contextmanager
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
import uuid

from .private_storage import private_mkdir, private_open, verify_private
from .runtime_lock import safe_path

_mutex=threading.RLock()
_active={}
_initialized=set()
MAX_ENTRIES=256


class RecoveryError(ValueError):
    pass


class Busy(Exception):
    pass


def identity(path):
    info=safe_path(path).stat()
    if not info.st_ino:raise RecoveryError('Native resource has no stable file identity')
    return {'device':info.st_dev,'inode':info.st_ino}


def _fd_identity(fd):
    info=os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or not info.st_ino:
        raise RecoveryError('Invalid native lease file')
    return {'device':info.st_dev,'inode':info.st_ino}


def _sync_directory(path):
    if sys.platform=='linux':
        fd=os.open(path,os.O_DIRECTORY|os.O_RDONLY|os.O_CLOEXEC)
        try:os.fsync(fd)
        finally:os.close(fd)


class Lease:
    def __init__(self,path,create=False):
        self.path=safe_path(path);self.stream=None
        if create:
            try:
                with private_open(self.path) as stream:
                    stream.write(b'VRA native resource lease\n');stream.flush();os.fsync(stream.fileno())
            except FileExistsError:pass
        verify_private(self.path)
        expected=identity(self.path)
        if sys.platform=='win32':
            import ctypes as c
            import msvcrt
            from .private_storage import _windows,_win_path
            kernel=_windows()[3]
            handle=kernel.CreateFileW(_win_path(self.path),0xC0000000,0,None,3,0x80,None)
            if handle==c.c_void_p(-1).value:
                error=c.get_last_error()
                if error in (32,33):raise Busy() from None
                raise c.WinError(error)
            try:fd=msvcrt.open_osfhandle(handle,os.O_RDWR|os.O_BINARY)
            except Exception:
                kernel.CloseHandle(handle);raise
        elif sys.platform=='linux':
            import fcntl
            fd=os.open(self.path,os.O_RDWR|os.O_CLOEXEC|os.O_NOFOLLOW)
            try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except OSError as error:
                os.close(fd)
                if error.errno in (errno.EAGAIN,errno.EACCES):raise Busy() from None
                raise
        else:raise RecoveryError('Unsupported native recovery platform')
        self.stream=os.fdopen(fd,'r+b')
        try:
            self.identity=_fd_identity(fd)
            if self.identity!=expected:raise RecoveryError('Native lease identity changed while opening')
        except Exception:
            self.close();raise

    def close(self):
        if self.stream is not None:self.stream.close();self.stream=None


def registry(parent=None):
    parent=safe_path(parent or tempfile.gettempdir())
    if sys.platform=='win32':
        from .private_storage import _sid,_windows
        account=_sid(_windows())
    elif sys.platform=='linux':account=str(os.getuid())
    else:raise RecoveryError('Native recovery requires Windows or Linux')
    root=parent/('vra-native-v1-'+hashlib.sha256(account.encode()).hexdigest()[:16])
    try:private_mkdir(root)
    except FileExistsError:pass
    verify_private(root,True)
    return root


@contextmanager
def _gate(root):
    deadline=time.monotonic()+15
    while True:
        try:lease=Lease(root/'registry.lock',create=True);break
        except Busy:
            if time.monotonic()>deadline:raise RecoveryError('Native workspace registry busy') from None
            time.sleep(.05)
    try:yield
    finally:lease.close()


def _write(entry,value):
    temporary=entry/('.record-'+uuid.uuid4().hex+'.tmp')
    with private_open(temporary) as stream:
        stream.write(json.dumps(value,allow_nan=False).encode());stream.flush();os.fsync(stream.fileno())
    temporary.replace(entry/'record.json');_sync_directory(entry)


def _read(entry,lease):
    path=safe_path(entry/'record.json');verify_private(path)
    if path.stat().st_size>8192:raise RecoveryError('Oversized native ownership record')
    value=json.loads(path.read_text(encoding='utf-8'))
    required={'version','id','entry_identity','lease_identity','data_identity','profile','state'}
    if (not isinstance(value,dict) or set(value)!=required or type(value['version']) is not int or value['version']!=1 or value['id']!=entry.name
        or value['entry_identity']!=identity(entry) or value['lease_identity']!=lease.identity
        or value['state'] not in ('active','cleaning')):
        raise RecoveryError('Native ownership identity mismatch')
    return value


def _inventory(root):
    # Check every node before recursive deletion; bounded discovery. Linked and
    # special files are retained for inspection, including swapped junctions.
    count=0
    for directory,dirs,files in os.walk(safe_path(root),followlinks=False):
        for name in dirs+files:
            path=safe_path(Path(directory)/name);info=path.stat()
            count+=1
            if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
                raise RecoveryError('Special file in native workspace')
            if count>80000:raise RecoveryError('Native recovery inventory budget exceeded')


def _profile_api():
    import ctypes as c
    from ctypes import wintypes as w
    from .native_windows import api
    k,a,u,_=api()
    u.DeriveAppContainerSidFromAppContainerName.argtypes=[w.LPCWSTR,c.POINTER(c.c_void_p)]
    u.DeriveAppContainerSidFromAppContainerName.restype=c.c_long
    return c,k,a,u


def _profile_sid(name):
    c,k,a,u=_profile_api();sid=c.c_void_p();text=c.c_void_p()
    if u.DeriveAppContainerSidFromAppContainerName(name,c.byref(sid))<0:raise RecoveryError('Cannot derive owned profile identity')
    try:
        if not a.ConvertSidToStringSidW(sid,c.byref(text)):raise c.WinError(c.get_last_error())
        try:return c.wstring_at(text)
        finally:k.LocalFree(text)
    finally:a.FreeSid(sid)


def _profile_path(sid):
    c,_,_,u=_profile_api();folder=c.c_void_p()
    result=u.GetAppContainerFolderPath(sid,c.byref(folder))
    if (result&0xffffffff)==0x80070002:return None
    if result<0:raise RecoveryError('Cannot inspect owned profile mapping')
    try:return safe_path(Path(c.wstring_at(folder)).parent)
    finally:
        ole=c.OleDLL('ole32');ole.CoTaskMemFree.argtypes=[c.c_void_p];ole.CoTaskMemFree(folder)


def _cleanup_profile(entry,profile):
    if profile is None:return
    if sys.platform!='win32' or not isinstance(profile,dict) or set(profile)!={'name','sid','identity'}:
        raise RecoveryError('Invalid native profile ownership')
    name='VRA.Engine.Managed.'+entry.name
    if profile['name']!=name or profile['sid']!=_profile_sid(name):raise RecoveryError('Native profile identity mismatch')
    target=safe_path(Path(os.environ['LOCALAPPDATA'])/'Packages'/name)
    actual=_profile_path(profile['sid'])
    if actual is not None and actual!=target:raise RecoveryError('Native profile storage escaped its registered location')
    if target.exists():
        if profile['identity'] is not None and identity(target)!=profile['identity']:
            raise RecoveryError('Native profile storage identity changed')
        if actual is None:raise RecoveryError('Profile directory exists without its registered identity')
        _inventory(target)
    _,_,_,u=_profile_api()
    if u.DeleteAppContainerProfile(name)<0 or target.exists():raise RecoveryError('Native profile cleanup incomplete; journal retained')


def _cleanup(entry,lease):
    value=_read(entry,lease);data=safe_path(entry/'data')
    if data.exists():
        if value['data_identity'] is None:
            verify_private(data,True)
            if any(data.iterdir()):raise RecoveryError('Uncommitted native directory is not empty')
        elif identity(data)!=value['data_identity']:raise RecoveryError('Native data directory identity changed')
        _inventory(data)
    elif value['data_identity'] is not None and value['state']!='cleaning':
        raise RecoveryError('Registered native data directory is missing')
    allowed={'data','lease','record.json'}
    for path in entry.iterdir():
        safe_path(path)
        if path.name not in allowed and not re.fullmatch(r'\.record-[0-9a-f]{32}\.tmp',path.name):
            raise RecoveryError('Unexpected ownership metadata; retained')
        if path.name!='data' and not path.is_file():raise RecoveryError('Invalid ownership metadata file')
    value['state']='cleaning';_write(entry,value)
    _cleanup_profile(entry,value['profile'])
    if data.exists():shutil.rmtree(data)
    # The registry gate remains held while the last lease closes and metadata
    # is removed, so a second process cannot claim a half-deleted entry.
    _remove_metadata(entry,lease)


def _remove_metadata(entry,lease):
    # Remove the journal before the lease, only AFTER all resources are gone.
    # A crash then leaves either a cleaning journal with its original lease or
    # empty allocation scaffolding, both safely resumable on the next startup.
    lease.close()
    for path in entry.iterdir():
        if path.name!='lease':safe_path(path).unlink()
    safe_path(entry/'lease').unlink()
    entry.rmdir();_sync_directory(entry.parent)


def _recover(root):
    entries=[p for p in root.iterdir() if p.name!='registry.lock']
    if len(entries)>MAX_ENTRIES:raise RecoveryError('Native ownership registry capacity exceeded')
    report={'recovered':[],'active':0}
    for entry in entries:
        safe_path(entry);verify_private(entry,True)
        if not re.fullmatch('[0-9a-f]{32}',entry.name):raise RecoveryError('Unknown native registry entry; retained')
        incomplete=not (entry/'record.json').exists()
        if incomplete:
            for path in entry.iterdir():
                safe_path(path)
                if not (path.name=='lease' or re.fullmatch(r'\.record-[0-9a-f]{32}\.tmp',path.name)) or not path.is_file():
                    raise RecoveryError('Missing native journal with allocated resources; retained')
                verify_private(path)
                if path.stat().st_size>8192:raise RecoveryError('Incomplete ownership metadata oversized')
        try:lease=Lease(entry/'lease',create=incomplete)
        except Busy:report['active']+=1;continue
        try:
            if incomplete:
                _remove_metadata(entry,lease)
            else:_cleanup(entry,lease)
            report['recovered'].append(entry.name)
        except Exception as error:
            raise RecoveryError('Native recovery refused for '+entry.name+': '+str(error)) from error
        finally:lease.close()
    return report


def recover(parent=None):
    root=registry(parent)
    with _mutex,_gate(root):
        report=_recover(root);_initialized.add(str(root))
    return report


@contextmanager
def owned_temporary(parent=None):
    root=registry(parent);lease=None;entry=None
    with _mutex,_gate(root):
        if str(root) not in _initialized:_recover(root);_initialized.add(str(root))
        if len(list(root.iterdir()))>MAX_ENTRIES:raise RecoveryError('Native workspace capacity exceeded')
        entry=private_mkdir(root/uuid.uuid4().hex)
        try:
            lease=Lease(entry/'lease',create=True)
            value={'version':1,'id':entry.name,'entry_identity':identity(entry),'lease_identity':lease.identity,
                   'data_identity':None,'profile':None,'state':'active'}
            _write(entry,value);data=private_mkdir(entry/'data')
            value['data_identity']=identity(data);_write(entry,value)
            _active[str(data)]=(entry,lease)
        except Exception:
            if lease is not None:lease.close()
            # Preserve partial ownership metadata for verified recovery.
            raise
    try:yield data
    finally:
        try:
            with _mutex,_gate(root):_cleanup(entry,lease)
        finally:
            with _mutex:_active.pop(str(data),None)
            lease.close()


def reserve_profile(data):
    with _mutex:
        entry,lease=_active[str(data)];value=_read(entry,lease)
        name='VRA.Engine.Managed.'+entry.name;sid=_profile_sid(name)
        if _profile_path(sid) is not None or safe_path(Path(os.environ['LOCALAPPDATA'])/'Packages'/name).exists():
            raise RecoveryError('Refuse to adopt an existing AppContainer profile')
        value['profile']={'name':name,'sid':sid,'identity':None};_write(entry,value)
        return name


def confirm_profile(data,sid,path):
    with _mutex:
        entry,lease=_active[str(data)];value=_read(entry,lease);profile=value['profile']
        expected=safe_path(Path(os.environ['LOCALAPPDATA'])/'Packages'/profile['name'])
        if sid!=profile['sid'] or safe_path(path)!=expected:raise RecoveryError('Created profile ownership mismatch')
        profile['identity']=identity(path);_write(entry,value)


@contextmanager
def inherit_leases(paths):
    """Duplicate only leases for the actual command/runtime/control paths."""
    duplicates=[];items=[];options={}
    try:
        with _mutex:
            selected={str(Path(p).absolute()) for p in paths if p is not None}
            for data,(_,lease) in _active.items():
                if not any(Path(p).is_relative_to(data) for p in selected):continue
                fd=os.dup(lease.stream.fileno());duplicates.append(fd)
                if sys.platform=='win32':
                    import msvcrt
                    handle=msvcrt.get_osfhandle(fd);os.set_handle_inheritable(handle,True)
                else:handle=fd
                items.append({'handle':handle,'identity':_fd_identity(fd)})
        if sys.platform=='win32' and items:
            startup=subprocess.STARTUPINFO();startup.lpAttributeList={'handle_list':[x['handle'] for x in items]}
            options['startupinfo']=startup
        elif sys.platform=='linux':options['pass_fds']=tuple(x['handle'] for x in items)
        yield {'items':items,'popen':options}
    finally:
        for fd in duplicates:os.close(fd)


def verify_inherited(items):
    if not isinstance(items,list) or len(items)>16:raise RecoveryError('Invalid inherited lease list')
    held=[]
    try:
        for item in items:
            if not isinstance(item,dict) or set(item)!={'handle','identity'} or type(item['handle']) is not int:
                raise RecoveryError('Invalid inherited lease descriptor')
            if sys.platform=='win32':
                import msvcrt
                fd=msvcrt.open_osfhandle(item['handle'],os.O_RDWR|os.O_BINARY)
            else:fd=item['handle']
            stream=os.fdopen(fd,'r+b');held.append(stream)
            if _fd_identity(fd)!=item['identity']:raise RecoveryError('Inherited lease identity mismatch')
        return held
    except Exception:
        for stream in held:stream.close()
        raise
