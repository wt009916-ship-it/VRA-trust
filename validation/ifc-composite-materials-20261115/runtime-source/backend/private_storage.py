"""Create NEW local maintenance objects with restrictive permissions before data.

Not protection from administrators, same-user processes, memory dumps or disk recovery.
"""
import os
import re
import shutil
import stat
import sys
import uuid
from contextlib import contextmanager

from .runtime_lock import safe_path


def _windows():
    import ctypes as c
    from ctypes import wintypes as w
    adv = c.WinDLL('advapi32', use_last_error=True)
    kernel = c.WinDLL('kernel32', use_last_error=True)
    signatures = [
        (kernel,'GetCurrentProcess',[],w.HANDLE),
        (kernel,'CloseHandle',[w.HANDLE],w.BOOL),
        (kernel,'LocalFree',[c.c_void_p],c.c_void_p),
        (kernel,'CreateDirectoryW',[w.LPCWSTR,c.c_void_p],w.BOOL),
        (kernel,'CreateFileW',[w.LPCWSTR,w.DWORD,w.DWORD,c.c_void_p,w.DWORD,w.DWORD,w.HANDLE],w.HANDLE),
        (adv,'OpenProcessToken',[w.HANDLE,w.DWORD,c.POINTER(w.HANDLE)],w.BOOL),
        (adv,'GetTokenInformation',[w.HANDLE,c.c_int,c.c_void_p,w.DWORD,c.POINTER(w.DWORD)],w.BOOL),
        (adv,'ConvertSidToStringSidW',[c.c_void_p,c.POINTER(c.c_void_p)],w.BOOL),
        (adv,'ConvertStringSecurityDescriptorToSecurityDescriptorW',[w.LPCWSTR,w.DWORD,c.POINTER(c.c_void_p),c.c_void_p],w.BOOL),
        (adv,'GetNamedSecurityInfoW',[w.LPWSTR,c.c_int,w.DWORD,c.c_void_p,c.c_void_p,c.c_void_p,c.c_void_p,c.POINTER(c.c_void_p)],w.DWORD),
        (adv,'ConvertSecurityDescriptorToStringSecurityDescriptorW',[c.c_void_p,w.DWORD,w.DWORD,c.POINTER(c.c_void_p),c.c_void_p],w.BOOL),
        (adv,'GetSecurityDescriptorControl',[c.c_void_p,c.POINTER(w.WORD),c.POINTER(w.DWORD)],w.BOOL),
    ]
    for lib,name,args,result in signatures:
        function=getattr(lib,name);function.argtypes=args;function.restype=result
    return c,w,adv,kernel


def _sid(api):
    c,w,adv,kernel=api
    token=w.HANDLE()
    if not adv.OpenProcessToken(kernel.GetCurrentProcess(),8,c.byref(token)):
        raise c.WinError(c.get_last_error())
    try:
        size=w.DWORD()
        adv.GetTokenInformation(token,1,None,0,c.byref(size))
        data=c.create_string_buffer(size.value)
        if not adv.GetTokenInformation(token,1,data,size,c.byref(size)):
            raise c.WinError(c.get_last_error())
        sid=c.cast(data,c.POINTER(c.c_void_p))[0]
        text=c.c_void_p()
        if not adv.ConvertSidToStringSidW(sid,c.byref(text)):
            raise c.WinError(c.get_last_error())
        try:return c.wstring_at(text)
        finally:kernel.LocalFree(text)
    finally:kernel.CloseHandle(token)


def _win_path(path):
    if str(path).startswith('\\\\'):
        raise ValueError('Maintenance protection requires a local filesystem')
    return '\\\\?\\'+str(path)


def _verify_windows(path, directory, api=None):
    api=api or _windows();c,w,adv,kernel=api
    expected=_sid(api);descriptor=c.c_void_p();text=c.c_void_p()
    status=adv.GetNamedSecurityInfoW(_win_path(path),1,5,None,None,None,None,c.byref(descriptor))
    if status:raise c.WinError(status)
    try:
        control=w.WORD();revision=w.DWORD()
        if not adv.GetSecurityDescriptorControl(descriptor,c.byref(control),c.byref(revision)):
            raise c.WinError(c.get_last_error())
        if control.value & 0x1004 != 0x1004:
            raise ValueError('Maintenance DACL is missing or inherits broad permissions')
        if not adv.ConvertSecurityDescriptorToStringSecurityDescriptorW(descriptor,1,5,c.byref(text),None):
            raise c.WinError(c.get_last_error())
        sddl=c.wstring_at(text)
        normalize=lambda sid:'S-1-5-18' if sid=='SY' else sid
        owner=re.match(r'O:(.*?)(?:D:|G:|S:|$)',sddl)
        aces=[x.split(';') for x in re.findall(r'\(([^()]*)\)',sddl)]
        if (not owner or normalize(owner[1])!=expected or len(aces)!=2
            or {normalize(x[5]) for x in aces if len(x)==6}!={expected,'S-1-5-18'}
            or any(len(x)!=6 or x[0]!='A' or x[1]!=('OICI' if directory else '')
                   or x[2] not in {'FA','0x1f01ff'} or x[3] or x[4] for x in aces)):
            raise ValueError('Maintenance permission readback mismatch')
        return {'mechanism':'windows_protected_dacl','owner':'current_account','allowed':['current_account','SYSTEM'],
                'inheritance_from_parent':False,'verified':True}
    finally:
        if text.value:kernel.LocalFree(text)
        kernel.LocalFree(descriptor)


@contextmanager
def _security(api, directory):
    c,w,adv,kernel=api
    class Attributes(c.Structure):
        _fields_=[('length',w.DWORD),('descriptor',c.c_void_p),('inherit',w.BOOL)]
    sid=_sid(api);flags='OICI' if directory else ''
    sddl=f'O:{sid}D:P(A;{flags};FA;;;{sid})(A;{flags};FA;;;SY)'
    descriptor=c.c_void_p()
    if not adv.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl,1,c.byref(descriptor),None):
        raise c.WinError(c.get_last_error())
    try:
        attributes=Attributes(c.sizeof(Attributes),descriptor,False)
        yield c.byref(attributes)
    finally:kernel.LocalFree(descriptor)


def verify_private(path, directory=False):
    path=safe_path(path)
    if sys.platform=='win32':return _verify_windows(path,directory)
    if sys.platform=='linux':
        info=path.stat();expected=0o700 if directory else 0o600
        if info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=expected:
            raise ValueError('Maintenance owner/mode verification failed')
        return {'mechanism':'posix_owner_mode','mode':oct(expected),'owner':'current_account','verified':True}
    raise ValueError('Private maintenance storage supports Windows and Linux only')


def private_mkdir(path):
    path=safe_path(path)
    if sys.platform=='win32':
        api=_windows();c,_,_,kernel=api
        with _security(api,True) as attributes:
            if not kernel.CreateDirectoryW(_win_path(path),attributes):
                raise c.WinError(c.get_last_error())
    elif sys.platform=='linux':
        path.mkdir(mode=0o700,exist_ok=False)
        os.chmod(path,0o700)
    else:raise ValueError('Private maintenance storage unsupported')
    verify_private(path,True)
    return path


def private_open(path):
    path=safe_path(path)
    if sys.platform=='win32':
        import msvcrt
        api=_windows();c,_,_,kernel=api
        with _security(api,False) as attributes:
            handle=kernel.CreateFileW(_win_path(path),0xC0000000,1,attributes,1,0x80,None)
            if handle==c.c_void_p(-1).value:raise c.WinError(c.get_last_error())
        try:fd=msvcrt.open_osfhandle(handle,os.O_RDWR|os.O_BINARY)
        except Exception:
            kernel.CloseHandle(handle);raise
    elif sys.platform=='linux':
        fd=os.open(path,os.O_RDWR|os.O_CREAT|os.O_EXCL,0o600)
        try:os.fchmod(fd,0o600)
        except Exception:
            os.close(fd);raise
    else:raise ValueError('Private maintenance storage unsupported')
    stream=os.fdopen(fd,'w+b')
    try:verify_private(path)
    except Exception:
        stream.close();raise
    return stream


@contextmanager
def private_temporary(parent):
    parent=safe_path(parent)
    path=private_mkdir(parent/('vra-private-'+uuid.uuid4().hex))
    try:yield path
    finally:
        # Only our newly created, exact child; never follow swapped junctions/links.
        if path.parent!=parent or not path.name.startswith('vra-private-'):
            raise ValueError('Refuse unsafe maintenance cleanup')
        safe_path(path)
        for root,dirs,files in os.walk(path,followlinks=False):
            for name in dirs+files:safe_path(os.path.join(root,name))
        shutil.rmtree(path)
