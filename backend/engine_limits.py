"""Budgets installed by a trusted supervisor BEFORE it launches the engine.

No filesystem/network isolation. Windows private commit != all mapped memory;
Linux address-space/CPU limits are per process, not an aggregate cgroup budget.
"""
import sys


def install(memory, cpu, file_bytes):
    if (type(memory) is not int or not 64*1024**2<=memory<=4*1024**3
        or type(cpu) is not int or not 1<=cpu<=600
        or type(file_bytes) is not int or not 1024<=file_bytes<=1024**3):
        raise ValueError('Invalid engine resource budget')
    if sys.platform=='win32':
        import ctypes as c
        from ctypes import wintypes as w
        from . import worker_limits
        # First bind the trusted Python supervisor to an existing audited job
        # implementation, then permit exactly supervisor + one engine process.
        receipt=worker_limits._windows(memory,cpu)
        kernel,handle=worker_limits._job
        class Basic(c.Structure):
            _fields_=[('ProcessTime',c.c_int64),('JobTime',c.c_int64),('Flags',w.DWORD),
                      ('MinWorkingSet',c.c_size_t),('MaxWorkingSet',c.c_size_t),('ActiveProcesses',w.DWORD),
                      ('Affinity',c.c_size_t),('Priority',w.DWORD),('Scheduling',w.DWORD)]
        class IO(c.Structure):
            _fields_=[(n,c.c_uint64) for n in ('ReadOps','WriteOps','OtherOps','ReadBytes','WriteBytes','OtherBytes')]
        class Extended(c.Structure):
            _fields_=[('Basic',Basic),('IO',IO),('ProcessMemory',c.c_size_t),('JobMemory',c.c_size_t),
                      ('PeakProcessMemory',c.c_size_t),('PeakJobMemory',c.c_size_t)]
        value=Extended()
        if not kernel.QueryInformationJobObject(handle,9,c.byref(value),c.sizeof(value),None):raise c.WinError(c.get_last_error())
        original_flags=value.Basic.Flags
        # Do not reset CPU time after assigning the supervisor: JOB_TIME adds
        # already consumed user time. PRESERVE_JOB_TIME retains the first cap.
        value.Basic.Flags=(original_flags & ~0x0004)|0x0040
        value.Basic.ActiveProcesses=2
        if not kernel.SetInformationJobObject(handle,9,c.byref(value),c.sizeof(value)):raise c.WinError(c.get_last_error())
        check=Extended()
        if not kernel.QueryInformationJobObject(handle,9,c.byref(check),c.sizeof(check),None):raise c.WinError(c.get_last_error())
        if (check.Basic.ActiveProcesses,check.Basic.Flags,check.JobMemory,check.ProcessMemory,check.Basic.JobTime)!=(2,original_flags,memory,memory,cpu*10_000_000):
            raise RuntimeError('Engine job policy readback mismatch: '+repr((check.Basic.ActiveProcesses,check.Basic.Flags,check.JobMemory,check.ProcessMemory,check.Basic.JobTime,value.Basic.Flags,cpu*10_000_000)))
        return {**receipt,'active_process_limit':2,'file_size_os_enforced':False}
    if sys.platform=='linux':
        import resource
        def bound(kind,requested):
            _,hard=resource.getrlimit(kind)
            value=requested if hard==resource.RLIM_INFINITY else min(hard,requested)
            resource.setrlimit(kind,(value,value))
            if resource.getrlimit(kind)!=(value,value):raise RuntimeError('Engine resource readback mismatch')
            return value
        actual_memory=bound(resource.RLIMIT_AS,memory)
        actual_cpu=bound(resource.RLIMIT_CPU,cpu)
        actual_file=bound(resource.RLIMIT_FSIZE,file_bytes)
        bound(resource.RLIMIT_CORE,0)
        return {'mechanism':'linux_rlimit','memory_bytes':actual_memory,'cpu_seconds':actual_cpu,
                'memory_semantics':'per_process_address_space','cpu_semantics':'per_process_cpu',
                'file_size_os_enforced':True,'file_bytes':actual_file,'aggregate_tree_budget':False}
    raise RuntimeError('Engine resource policy supports Windows and Linux only')
