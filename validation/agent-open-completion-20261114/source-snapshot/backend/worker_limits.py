"""OS-enforced budgets for disposable parsers, NOT a filesystem/network sandbox.

Imported before native parser libraries in each worker's command-line entry.
Windows caps private committed memory/job user CPU; mapped memory is NOT capped.
Linux caps address space/process CPU; neither isolates files or networking.
"""
import json
import os
import sys
from pathlib import Path

POLICIES = {
    'cad': {'memory_bytes': 2*1024**3, 'cpu_seconds': 20},
    'drawing': {'memory_bytes': 2*1024**3, 'cpu_seconds': 40},
    'standards': {'memory_bytes': 512*1024**2, 'cpu_seconds': 20},
}
_job = None  # Retain until process exit; closing the last handle kills this job.


def _windows(memory, cpu):
    import ctypes as c
    from ctypes import wintypes as w

    class Basic(c.Structure):
        _fields_ = [('ProcessTime',c.c_int64),('JobTime',c.c_int64),('Flags',w.DWORD),
                    ('MinWorkingSet',c.c_size_t),('MaxWorkingSet',c.c_size_t),('ActiveProcesses',w.DWORD),
                    ('Affinity',c.c_size_t),('Priority',w.DWORD),('Scheduling',w.DWORD)]

    class IO(c.Structure):
        _fields_ = [(n,c.c_uint64) for n in ('ReadOps','WriteOps','OtherOps','ReadBytes','WriteBytes','OtherBytes')]

    class Extended(c.Structure):
        _fields_ = [('Basic',Basic),('IO',IO),('ProcessMemory',c.c_size_t),('JobMemory',c.c_size_t),
                    ('PeakProcessMemory',c.c_size_t),('PeakJobMemory',c.c_size_t)]

    kernel = c.WinDLL('kernel32',use_last_error=True)
    kernel.CreateJobObjectW.argtypes=[c.c_void_p,w.LPCWSTR];kernel.CreateJobObjectW.restype=w.HANDLE
    kernel.SetInformationJobObject.argtypes=[w.HANDLE,c.c_int,c.c_void_p,w.DWORD];kernel.SetInformationJobObject.restype=w.BOOL
    kernel.QueryInformationJobObject.argtypes=[w.HANDLE,c.c_int,c.c_void_p,w.DWORD,c.c_void_p];kernel.QueryInformationJobObject.restype=w.BOOL
    kernel.AssignProcessToJobObject.argtypes=[w.HANDLE,w.HANDLE];kernel.AssignProcessToJobObject.restype=w.BOOL
    kernel.GetCurrentProcess.argtypes=[];kernel.GetCurrentProcess.restype=w.HANDLE
    kernel.CloseHandle.argtypes=[w.HANDLE];kernel.CloseHandle.restype=w.BOOL
    kernel.SetErrorMode.argtypes=[w.UINT];kernel.SetErrorMode.restype=w.UINT
    # No crash dialog for an isolated parser; do not change any parent setting.
    kernel.SetErrorMode(0x0001 | 0x0002 | 0x8000)
    handle=kernel.CreateJobObjectW(None,None)
    if not handle:raise c.WinError(c.get_last_error())
    limits=Extended();limits.Basic.Flags=0x0004|0x0008|0x0100|0x0200|0x2000
    limits.Basic.JobTime=cpu*10_000_000;limits.Basic.ActiveProcesses=1
    limits.ProcessMemory=memory;limits.JobMemory=memory
    assigned=False
    try:
        if not kernel.SetInformationJobObject(handle,9,c.byref(limits),c.sizeof(limits)):
            raise c.WinError(c.get_last_error())
        check=Extended()
        if not kernel.QueryInformationJobObject(handle,9,c.byref(check),c.sizeof(check),None):
            raise c.WinError(c.get_last_error())
        if (check.Basic.Flags,check.Basic.JobTime,check.Basic.ActiveProcesses,check.ProcessMemory,check.JobMemory)!=(limits.Basic.Flags,limits.Basic.JobTime,1,memory,memory):
            raise RuntimeError('Windows resource limits readback mismatch')
        if not kernel.AssignProcessToJobObject(handle,kernel.GetCurrentProcess()):
            raise c.WinError(c.get_last_error())
        assigned=True
        global _job
        _job=(kernel,handle)
    finally:
        if not assigned:kernel.CloseHandle(handle)
    return {'mechanism':'windows_job_object','memory_semantics':'private_committed_bytes_per_process_and_job',
            'memory_bytes':memory,'cpu_semantics':'job_user_seconds','cpu_seconds':cpu,
            'active_process_limit':1,'kill_on_job_close':True,'mapped_memory_bounded':False}


def _linux(memory,cpu):
    import resource
    def limit(kind,requested):
        _,hard=resource.getrlimit(kind)
        value=requested if hard==resource.RLIM_INFINITY else min(requested,hard)
        if value<=0 and requested>0:raise RuntimeError('Inherited resource budget unavailable')
        resource.setrlimit(kind,(value,value))
        if resource.getrlimit(kind)!=(value,value):raise RuntimeError('rlimit readback mismatch')
        return value
    memory=limit(resource.RLIMIT_AS,memory)
    cpu=limit(resource.RLIMIT_CPU,cpu)
    limit(resource.RLIMIT_CORE,0)
    # Per-file protection does not claim an aggregate filesystem quota.
    file_bytes=limit(resource.RLIMIT_FSIZE,64*1024**2)
    return {'mechanism':'linux_rlimit','memory_semantics':'virtual_address_space_per_process',
            'memory_bytes':memory,'cpu_semantics':'process_user_and_system_seconds','cpu_seconds':cpu,
            'core_dump_bytes':0,'single_file_bytes':file_bytes,
            'active_process_limit':None,'kill_on_job_close':False,'mapped_memory_bounded':True}


def apply_limits(memory,cpu):
    if type(memory) is not int or type(cpu) is not int or not 32*1024**2<=memory<=4*1024**3 or not 1<=cpu<=60:
        raise ValueError('Invalid parser resource policy')
    if sys.platform=='win32':return _windows(memory,cpu)
    if sys.platform=='linux':return _linux(memory,cpu)
    raise RuntimeError('Parser resource enforcement is unsupported on this platform')


def initialize(kind):
    """Fail before importing parsers when limits cannot be installed."""
    policy=POLICIES[kind]
    try:
        applied=apply_limits(policy['memory_bytes'],policy['cpu_seconds'])
        receipt={'kind':kind,'enforced':True,'pid':os.getpid(),**applied,
                 'boundary':'RESOURCE_BUDGET_NOT_FILESYSTEM_OR_NETWORK_SANDBOX'}
        Path(sys.argv[2]).with_suffix('.limits.json').write_text(json.dumps(receipt),encoding='utf-8')
    except Exception:
        # No inference/output fallback. Parent treats exit 70 as failure.
        raise SystemExit(70) from None


def receipt(output,kind):
    """Validate the worker's kernel-readback receipt before persisting a result."""
    path=Path(output).with_suffix('.limits.json')
    if not path.is_file() or path.stat().st_size>4096:raise ValueError('Missing parser resource receipt')
    data=json.loads(path.read_text(encoding='utf-8'))
    policy=POLICIES[kind]
    expected='windows_job_object' if sys.platform=='win32' else 'linux_rlimit' if sys.platform=='linux' else None
    if (data.get('kind')!=kind or data.get('enforced') is not True or data.get('mechanism')!=expected or expected is None
        or type(data.get('memory_bytes')) is not int or not 0<data['memory_bytes']<=policy['memory_bytes']
        or type(data.get('cpu_seconds')) is not int or not 0<data['cpu_seconds']<=policy['cpu_seconds']):
        raise ValueError('Invalid parser resource receipt')
    return data
