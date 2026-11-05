"""Windows LPAC launch boundary for staged native engines.

No network/COM capability. registryRead permits the Windows loader to work.
LPAC also has Windows' implicit ALL RESTRICTED APPLICATION PACKAGES access;
this is not a VM, a registry sandbox, or a hard disk/mapped-memory quota.
Only fresh staging directories receive ACLs. Original inputs/installations do not.
"""
import ctypes as c
from ctypes import wintypes as w
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import uuid

from .native_environment import environment
from .private_storage import private_temporary, _windows, _sid
from .runtime_lock import safe_path


class SI(c.Structure):
    _fields_=[('cb',w.DWORD),('reserved',w.LPWSTR),('desktop',w.LPWSTR),('title',w.LPWSTR),
              ('x',w.DWORD),('y',w.DWORD),('xs',w.DWORD),('ys',w.DWORD),('xc',w.DWORD),
              ('yc',w.DWORD),('fill',w.DWORD),('flags',w.DWORD),('show',w.WORD),
              ('reserved2size',w.WORD),('reserved2',c.c_void_p),
              ('stdin',w.HANDLE),('stdout',w.HANDLE),('stderr',w.HANDLE)]


class SX(c.Structure):
    _fields_=[('startup',SI),('attributes',c.c_void_p)]


class PI(c.Structure):
    _fields_=[('process',w.HANDLE),('thread',w.HANDLE),('pid',w.DWORD),('tid',w.DWORD)]


class SA(c.Structure):
    _fields_=[('sid',c.c_void_p),('attributes',w.DWORD)]


class CAPS(c.Structure):
    _fields_=[('sid',c.c_void_p),('capabilities',c.c_void_p),('count',w.DWORD),('reserved',w.DWORD)]


def api():
    k=c.WinDLL('kernel32',use_last_error=True)
    a=c.WinDLL('advapi32',use_last_error=True)
    u=c.WinDLL('userenv',use_last_error=True)
    b=c.WinDLL('kernelbase',use_last_error=True)
    def sig(lib,name,args,ret):
        f=getattr(lib,name);f.argtypes=args;f.restype=ret
    sig(u,'CreateAppContainerProfile',[w.LPCWSTR,w.LPCWSTR,w.LPCWSTR,c.c_void_p,w.DWORD,c.POINTER(c.c_void_p)],c.c_long)
    sig(u,'DeleteAppContainerProfile',[w.LPCWSTR],c.c_long)
    sig(u,'GetAppContainerFolderPath',[w.LPCWSTR,c.POINTER(c.c_void_p)],c.c_long)
    sig(a,'FreeSid',[c.c_void_p],c.c_void_p)
    sig(a,'ConvertSidToStringSidW',[c.c_void_p,c.POINTER(c.c_void_p)],w.BOOL)
    sig(a,'ConvertStringSidToSidW',[w.LPCWSTR,c.POINTER(c.c_void_p)],w.BOOL)
    sig(a,'ConvertStringSecurityDescriptorToSecurityDescriptorW',[w.LPCWSTR,w.DWORD,c.POINTER(c.c_void_p),c.c_void_p],w.BOOL)
    sig(a,'GetSecurityDescriptorDacl',[c.c_void_p,c.POINTER(w.BOOL),c.POINTER(c.c_void_p),c.POINTER(w.BOOL)],w.BOOL)
    sig(a,'GetSecurityDescriptorSacl',[c.c_void_p,c.POINTER(w.BOOL),c.POINTER(c.c_void_p),c.POINTER(w.BOOL)],w.BOOL)
    sig(a,'SetNamedSecurityInfoW',[w.LPWSTR,c.c_int,w.DWORD,c.c_void_p,c.c_void_p,c.c_void_p,c.c_void_p],w.DWORD)
    sig(a,'OpenProcessToken',[w.HANDLE,w.DWORD,c.POINTER(w.HANDLE)],w.BOOL)
    sig(a,'GetTokenInformation',[w.HANDLE,c.c_int,c.c_void_p,w.DWORD,c.POINTER(w.DWORD)],w.BOOL)
    sig(a,'EqualSid',[c.c_void_p,c.c_void_p],w.BOOL)
    sig(a,'DuplicateToken',[w.HANDLE,c.c_int,c.POINTER(w.HANDLE)],w.BOOL)
    sig(a,'AccessCheck',[c.c_void_p,w.HANDLE,w.DWORD,c.c_void_p,c.c_void_p,c.POINTER(w.DWORD),c.POINTER(w.DWORD),c.POINTER(w.BOOL)],w.BOOL)
    sig(k,'InitializeProcThreadAttributeList',[c.c_void_p,w.DWORD,w.DWORD,c.POINTER(c.c_size_t)],w.BOOL)
    sig(k,'UpdateProcThreadAttribute',[c.c_void_p,w.DWORD,c.c_size_t,c.c_void_p,c.c_size_t,c.c_void_p,c.c_void_p],w.BOOL)
    sig(k,'DeleteProcThreadAttributeList',[c.c_void_p],None)
    sig(k,'CreateProcessW',[w.LPCWSTR,w.LPWSTR,c.c_void_p,c.c_void_p,w.BOOL,w.DWORD,c.c_void_p,w.LPCWSTR,c.POINTER(SX),c.POINTER(PI)],w.BOOL)
    sig(k,'WaitForSingleObject',[w.HANDLE,w.DWORD],w.DWORD)
    sig(k,'GetExitCodeProcess',[w.HANDLE,c.POINTER(w.DWORD)],w.BOOL)
    sig(k,'TerminateProcess',[w.HANDLE,w.UINT],w.BOOL)
    sig(k,'ResumeThread',[w.HANDLE],w.DWORD)
    sig(k,'CloseHandle',[w.HANDLE],w.BOOL)
    sig(k,'LocalFree',[c.c_void_p],c.c_void_p)
    sig(k,'GetCurrentProcess',[],w.HANDLE)
    sig(k,'GetStdHandle',[w.DWORD],w.HANDLE)
    sig(k,'DuplicateHandle',[w.HANDLE,w.HANDLE,w.HANDLE,c.POINTER(w.HANDLE),w.DWORD,w.BOOL,w.DWORD],w.BOOL)
    sig(k,'IsProcessInJob',[w.HANDLE,w.HANDLE,c.POINTER(w.BOOL)],w.BOOL)
    sig(b,'DeriveCapabilitySidsFromName',[w.LPCWSTR,c.POINTER(c.POINTER(c.c_void_p)),c.POINTER(w.DWORD),c.POINTER(c.POINTER(c.c_void_p)),c.POINTER(w.DWORD)],w.BOOL)
    return k,a,u,b


def checked(value):
    if not value:raise c.WinError(c.get_last_error())
    return value


def verify_lpac_access(token,sid_text,apis):
    """Verify LPAC's documented ACL semantics, not undocumented token fields.

    GetTokenInformation(46) is rejected on the tested Windows build. Require
    positive explicit-package and restricted-package controls, plus negative
    ALL APPLICATION PACKAGES and Everyone-only controls, before ResumeThread.
    """
    k,a,_,_=apis;duplicate=w.HANDLE()
    class Mapping(c.Structure):
        _fields_=[('read',w.DWORD),('write',w.DWORD),('execute',w.DWORD),('all',w.DWORD)]
    checked(a.DuplicateToken(token,2,c.byref(duplicate)))
    try:
        for principal,expected in [(sid_text,True),('S-1-15-2-2',True),('S-1-15-2-1',False),(None,False)]:
            sd=c.c_void_p()
            text='O:SYG:SYD:(A;;0x1;;;WD)'+(f'(A;;0x1;;;{principal})' if principal else '')
            checked(a.ConvertStringSecurityDescriptorToSecurityDescriptorW(text,1,c.byref(sd),None))
            try:
                mapping=Mapping(1,2,4,7);privileges=c.create_string_buffer(1024)
                length=w.DWORD(len(privileges));granted=w.DWORD();status=w.BOOL()
                checked(a.AccessCheck(sd,duplicate,1,c.byref(mapping),privileges,c.byref(length),c.byref(granted),c.byref(status)))
                if bool(status.value)!=expected or (expected and granted.value!=1):
                    raise RuntimeError('LPAC access-check controls failed')
            finally:k.LocalFree(sd)
    finally:k.CloseHandle(duplicate)


@contextmanager
def registry_capability(apis):
    k,_,_,b=apis
    groups=c.POINTER(c.c_void_p)();sids=c.POINTER(c.c_void_p)();ng=w.DWORD();nc=w.DWORD()
    checked(b.DeriveCapabilitySidsFromName('registryRead',c.byref(groups),c.byref(ng),c.byref(sids),c.byref(nc)))
    try:
        if not 0<nc.value<=4:raise RuntimeError('Unexpected capability SID count')
        yield (SA*nc.value)(*[SA(sids[i],4) for i in range(nc.value)])
    finally:
        for values,count in [(groups,ng.value),(sids,nc.value)]:
            for i in range(count):k.LocalFree(values[i])
            k.LocalFree(values)


def _protect_directory(path,sid,write,apis):
    """Private helper: caller owns a fresh staging directory, never existing paths."""
    k,a,_,_=apis
    owner=_sid(_windows());sd=c.c_void_p();present=w.BOOL();default=w.BOOL()
    dacl=c.c_void_p();sacl=c.c_void_p()
    text=f'D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;{owner})(A;OICI;{"FA" if write else "GRGX"};;;{sid})S:(ML;OICI;NW;;;LW)'
    checked(a.ConvertStringSecurityDescriptorToSecurityDescriptorW(text,1,c.byref(sd),None))
    try:
        checked(a.GetSecurityDescriptorDacl(sd,c.byref(present),c.byref(dacl),c.byref(default)))
        checked(a.GetSecurityDescriptorSacl(sd,c.byref(present),c.byref(sacl),c.byref(default)))
        result=a.SetNamedSecurityInfoW(str(path),1,0x80000014,None,None,dacl,sacl)
        if result:raise c.WinError(result)
    finally:k.LocalFree(sd)


@contextmanager
def staging():
    """Parent owns profile lifetime, including when its supervisor is cancelled."""
    apis=api();k,a,u,_=apis;sid=c.c_void_p()
    name='VRA.Engine.'+uuid.uuid4().hex
    with private_temporary(Path(tempfile.gettempdir())) as root:
        if not str(root).isascii():raise ValueError('Native engine needs ASCII TEMP')
        with registry_capability(apis) as capabilities:
            hr=u.CreateAppContainerProfile(name,name,'Temporary VRA native engine',capabilities,len(capabilities),c.byref(sid))
            if hr<0:raise RuntimeError('AppContainer profile creation failed: '+hex(hr&0xffffffff))
        try:
            text=c.c_void_p()
            checked(a.ConvertSidToStringSidW(sid,c.byref(text)))
            try:sid_text=c.wstring_at(text)
            finally:k.LocalFree(text)
            folder=c.c_void_p()
            hr=u.GetAppContainerFolderPath(sid_text,c.byref(folder))
            if hr<0:raise RuntimeError('AppContainer folder lookup failed')
            try:profile_root=safe_path(Path(c.wstring_at(folder)).parent)
            finally:
                ole=c.OleDLL('ole32');ole.CoTaskMemFree.argtypes=[c.c_void_p];ole.CoTaskMemFree.restype=None
                ole.CoTaskMemFree(folder)
            packages=safe_path(Path(os.environ['LOCALAPPDATA'])/'Packages')
            if profile_root.parent!=packages or profile_root.name.casefold()!=name.casefold():
                raise RuntimeError('Unexpected AppContainer profile storage path')
            _protect_directory(root,sid_text,False,apis)
            work=root/'output';work.mkdir()
            _protect_directory(work,sid_text,True,apis)
            yield {'root':root,'work':work,'sid':sid_text,'profile':name,'profile_root':profile_root}
        finally:
            a.FreeSid(sid)
            hr=u.DeleteAppContainerProfile(name)
            if hr<0:raise RuntimeError('AppContainer profile cleanup failed: '+hex(hr&0xffffffff))


def copy_file(source,target,maximum):
    """Fresh file and bounded streaming copy; identity of copied bytes is returned."""
    source=safe_path(source);size=source.stat().st_size
    if not source.is_file() or size>maximum:raise ValueError('Native staging file invalid/oversized')
    digest=hashlib.sha256();count=0
    with source.open('rb') as inp,target.open('xb') as out:
        while chunk:=inp.read(1024*1024):
            count+=len(chunk)
            if count>maximum:raise ValueError('Native staging file grew beyond budget')
            digest.update(chunk);out.write(chunk)
    if count!=size:raise ValueError('Native staging file changed size')
    return {'sha256':digest.hexdigest(),'bytes':count}


@contextmanager
def engine_workspace(engine,model=None,weather=None):
    engine=safe_path(engine)
    with staging() as scope:
        runtime=scope['root']/'runtime';runtime.mkdir()
        sources=[engine]
        for path in engine.parent.iterdir():
            if path.suffix.lower()=='.dll' or path.name=='Energy+.idd':sources.append(path)
        if len(sources)>256:raise ValueError('Native runtime file count exceeded')
        budget=128*1024**2;identities={}
        for source in sources:
            identity=copy_file(source,runtime/source.name,budget)
            budget-=identity['bytes'];identities[source.name]=identity
        for name,source in [('model.idf',model),('weather.epw',weather)]:
            if source is not None:identities[name]=copy_file(source,scope['root']/name,256*1024**2)
        yield {**scope,'engine':runtime/engine.name,'identities':identities}


@contextmanager
def launch(command,work,sid_text):
    """Run in LPAC, verifying token and inherited Job BEFORE resuming execution.

    This is called only by the trusted supervisor after installing its Job.
    HANDLE_LIST restricts inherited handles to three duplicated standard streams.
    """
    apis=api();k,a,_,_=apis;sid=c.c_void_p();pi=PI();attributes=None
    handles=[];token=w.HANDLE();initialized=False
    checked(a.ConvertStringSidToSidW(sid_text,c.byref(sid)))
    try:
        with registry_capability(apis) as capabilities:
            size=c.c_size_t();k.InitializeProcThreadAttributeList(None,3,0,c.byref(size))
            attributes=c.create_string_buffer(size.value)
            checked(k.InitializeProcThreadAttributeList(attributes,3,0,c.byref(size)));initialized=True
            caps=CAPS(sid,c.cast(capabilities,c.c_void_p),len(capabilities),0)
            optout=w.DWORD(1)
            checked(k.UpdateProcThreadAttribute(attributes,0,0x20009,c.byref(caps),c.sizeof(caps),None,None))
            checked(k.UpdateProcThreadAttribute(attributes,0,0x2000f,c.byref(optout),c.sizeof(optout),None,None))
            current=k.GetCurrentProcess()
            for number in [-10,-11,-12]:
                handle=w.HANDLE()
                checked(k.DuplicateHandle(current,k.GetStdHandle(number&0xffffffff),current,c.byref(handle),0,True,2))
                handles.append(handle.value)
            handle_list=(w.HANDLE*3)(*handles)
            checked(k.UpdateProcThreadAttribute(attributes,0,0x20002,handle_list,c.sizeof(handle_list),None,None))
            startup=SX();startup.startup.cb=c.sizeof(startup);startup.startup.flags=0x100
            startup.startup.stdin,startup.startup.stdout,startup.startup.stderr=handles
            startup.attributes=c.cast(attributes,c.c_void_p)
            cmd=c.create_unicode_buffer(subprocess.list2cmdline(list(map(str,command))))
            env=c.create_unicode_buffer('\0'.join(key+'='+value for key,value in sorted(environment(work).items()))+'\0\0')
            checked(k.CreateProcessW(str(command[0]),cmd,None,None,True,0x80000|0x8000000|0x400|0x4,
                                     env,str(work),c.byref(startup),c.byref(pi)))
            checked(a.OpenProcessToken(pi.process,8|2,c.byref(token)))
            value=w.DWORD();returned=w.DWORD()
            checked(a.GetTokenInformation(token,29,c.byref(value),4,c.byref(returned)))
            if value.value!=1:raise RuntimeError('Child is not an AppContainer')
            verify_lpac_access(token,sid_text,apis)
            a.GetTokenInformation(token,31,None,0,c.byref(returned))
            if not 8<=returned.value<=4096:raise RuntimeError('Unexpected token SID size')
            token_info=c.create_string_buffer(returned.value)
            checked(a.GetTokenInformation(token,31,token_info,len(token_info),c.byref(returned)))
            actual_sid=c.cast(token_info,c.POINTER(c.c_void_p)).contents
            if not a.EqualSid(sid,actual_sid):raise RuntimeError('AppContainer SID mismatch')
            a.GetTokenInformation(token,30,None,0,c.byref(returned))
            if not 8<=returned.value<=4096:raise RuntimeError('Unexpected capability token size')
            capability_info=c.create_string_buffer(returned.value)
            checked(a.GetTokenInformation(token,30,capability_info,len(capability_info),c.byref(returned)))
            class Groups(c.Structure):
                _fields_=[('count',w.DWORD),('groups',SA*len(capabilities))]
            actual_caps=Groups.from_buffer(capability_info)
            if actual_caps.count!=len(capabilities):raise RuntimeError('Unexpected token capabilities')
            for actual,expected in zip(actual_caps.groups,capabilities):
                if actual.attributes!=4 or not a.EqualSid(actual.sid,expected.sid):
                    raise RuntimeError('Token capability readback mismatch')
            in_job=w.BOOL();checked(k.IsProcessInJob(pi.process,None,c.byref(in_job)))
            if not in_job.value:raise RuntimeError('Native process escaped supervisor Job')
            if k.ResumeThread(pi.thread)!=1:raise RuntimeError('Native process resume failed')
            yield Process(k,pi.process,pi.pid)
    finally:
        if pi.process:
            if k.WaitForSingleObject(pi.process,0)!=0:
                checked(k.TerminateProcess(pi.process,70))
                if k.WaitForSingleObject(pi.process,5000)!=0:raise RuntimeError('Native cleanup unconfirmed')
            k.CloseHandle(pi.process);k.CloseHandle(pi.thread)
        if token:k.CloseHandle(token)
        for handle in handles:k.CloseHandle(handle)
        if initialized:k.DeleteProcThreadAttributeList(attributes)
        k.LocalFree(sid)


class Process:
    def __init__(self,kernel,handle,pid):self.kernel,self.handle,self.pid=kernel,handle,pid

    def wait(self):
        if self.kernel.WaitForSingleObject(self.handle,0xffffffff)!=0:raise RuntimeError('Native wait failed')
        code=w.DWORD();checked(self.kernel.GetExitCodeProcess(self.handle,c.byref(code)))
        return code.value
