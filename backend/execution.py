"""Supervised native execution and bounded artifact intake, not a disk sandbox."""
import json
import math
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from .private_storage import private_open
from .runtime_lock import safe_path
from .native_environment import environment

MIB=1024**2


class ExecutionError(ValueError):
    def __init__(self,message,receipt=None):
        super().__init__(message)
        self.receipt=receipt or {'calls_executed':0,'launch_state':'not_started'}


@dataclass(frozen=True)
class Policy:
    output_bytes: int = 256*MIB
    log_bytes: int = MIB
    output_files: int = 1024
    archive_bytes: int = 2048*MIB
    archive_files: int = 20000
    reserve_bytes: int = 256*MIB
    memory_bytes: int = 4*1024**3
    cpu_seconds: int = 300

    @classmethod
    def from_env(cls):
        values={}
        for key,name,scale in [('output_bytes','VRA_EXECUTION_OUTPUT_MB',MIB),('log_bytes','VRA_EXECUTION_LOG_MB',MIB),
                               ('archive_bytes','VRA_EXECUTION_ARCHIVE_MB',MIB),('output_files','VRA_EXECUTION_OUTPUT_FILES',1),
                               ('reserve_bytes','VRA_STORAGE_RESERVE_MB',MIB)]:
            if name in os.environ:
                raw=os.environ[name]
                if not re.fullmatch('[1-9][0-9]{0,5}',raw):raise ValueError(name+' must be a positive integer')
                values[key]=int(raw)*scale
        result=cls(**values)
        if result.output_bytes>1024**3 or result.log_bytes>16*MIB or result.output_files>10000:
            raise ValueError('Execution output/log/file limits exceed supported maxima')
        return result

    @property
    def reservation(self):
        # Input snapshots can be two 256 MiB uploads, plus output/log/metadata.
        return self.output_bytes+512*MIB+128*MIB+4*self.log_bytes+MIB


def inventory(root, max_bytes, max_files):
    """No links/special files; bounded nodes as well as bytes and file count."""
    root=safe_path(root)
    files=[];size=nodes=0;pending=[root] if root.exists() else []
    while pending:
        directory=pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                nodes+=1
                if nodes>max_files*4+16:raise ExecutionError('Artifact directory node budget exceeded')
                info=entry.stat(follow_symlinks=False)
                if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&0x400:
                    raise ExecutionError('Linked native artifacts rejected')
                if stat.S_ISDIR(info.st_mode):pending.append(Path(entry.path))
                elif stat.S_ISREG(info.st_mode):
                    size+=info.st_size;files.append((Path(entry.path),info.st_size))
                    if size>max_bytes or len(files)>max_files:raise ExecutionError('Native artifact byte/file budget exceeded')
                else:raise ExecutionError('Non-regular native artifact rejected')
    return files,size


_lanes={}
_mutex=threading.Lock()


@contextmanager
def archive_slot(root, roots, policy, cancel_check=None):
    key=os.path.normcase(str(safe_path(root)))
    with _mutex:lane=_lanes.setdefault(key,threading.BoundedSemaphore(1))
    deadline=time.monotonic()+300
    while not lane.acquire(timeout=.05):
        if cancel_check and cancel_check():raise ExecutionError('Execution cancelled before engine admission')
        if time.monotonic()>deadline:raise ExecutionError('Native execution admission timeout')
    try:
        if cancel_check and cancel_check():raise ExecutionError('Execution cancelled before engine admission')
        count=size=0
        for path in roots:
            entries,amount=inventory(path,policy.archive_bytes,policy.archive_files)
            count+=len(entries);size+=amount
        if size+policy.reservation>policy.archive_bytes or count+policy.output_files+16>policy.archive_files:
            raise ExecutionError('Execution archive capacity unavailable; old artifacts retained')
        if shutil.disk_usage(root).free<policy.reserve_bytes+2*policy.reservation:
            raise ExecutionError('Insufficient free space for native staging and archive reserve')
        yield
    finally:lane.release()


def _receipt(path,nonce):
    value={'launch_state':'unconfirmed','calls_executed':None}
    try:
        if path.stat().st_size>8192:return value
        data=json.loads(path.read_text(encoding='utf-8'))
        if data.get('nonce')!=nonce:return value
        state=data.get('state')
        if state=='launch_failed':return {**data,'launch_state':state,'calls_executed':0}
        if state in {'launched','finished','execution_failed'} and type(data.get('engine_pid')) is int:
            return {**data,'launch_state':state,'calls_executed':1}
        return {**data,**value}
    except (OSError,ValueError):return value


def _stop(process):
    if sys.platform=='linux':
        try:os.killpg(process.pid,signal.SIGKILL)
        except ProcessLookupError:pass
    elif process.poll() is None:
        process.kill()  # supervisor handle close kills inherited Windows job children
    process.wait(timeout=10)


def supervise(command, work, log_dir, policy, timeout, *, output=None, cancel_check=None, label='', isolation=None, extra_output_roots=()):
    if not isinstance(timeout,(int,float)) or isinstance(timeout,bool) or not math.isfinite(timeout) or not 0<timeout<=3600:
        raise ExecutionError('Invalid native timeout')
    work,log_dir=safe_path(work),safe_path(log_dir)
    nonce=uuid.uuid4().hex;request=work/(label+'engine-request.json')
    with private_open(request) as stream:
        stream.write(json.dumps({'nonce':nonce,'command':list(map(str,command)),'memory_bytes':policy.memory_bytes,
                                'cpu_seconds':policy.cpu_seconds,'file_bytes':min(policy.output_bytes,64*MIB),
                                'isolation':isolation,'parent_pid':os.getpid()}).encode())
    receipt_path=request.with_suffix('.receipt.json')
    worker=Path(__file__).with_name('engine_worker.py')
    error=threading.Event();reasons=[];readers=[];counts={};process=None
    started=time.monotonic();failure=None
    observed_output={}
    def check_output():
        files=size=0
        for root in ([output] if output is not None else [])+list(extra_output_roots):
            entries,amount=inventory(root,policy.output_bytes,policy.output_files)
            files+=len(entries);size+=amount
        observed_output.update(bytes=size,files=files,monitored_roots=len(extra_output_roots)+(output is not None))
        if size>policy.output_bytes or files>policy.output_files:raise ExecutionError('Combined native output/profile budget exceeded')
    def drain(pipe,path,name):
        total=0
        try:
            with private_open(path) as destination:
                while chunk:=pipe.read1(65536):
                    allowance=max(0,policy.log_bytes-total)
                    if allowance:destination.write(chunk[:allowance])
                    total+=len(chunk)
                    if total>policy.log_bytes and not error.is_set():
                        reasons.append('Native log budget exceeded');error.set()
                destination.flush();os.fsync(destination.fileno())
        except Exception:
            reasons.append('Native log persistence failed');error.set()
        finally:
            counts[name]=total;pipe.close()
    try:
        # Supervisor is stdlib-only. Bypass the Windows venv redirector so the
        # retained Popen handle belongs to the process that owns the Job handle.
        interpreter=getattr(sys,'_base_executable',sys.executable) if sys.platform=='win32' else sys.executable
        process=subprocess.Popen([interpreter,str(worker),str(request)],cwd=work,stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=sys.platform=='linux',
            env=environment(work),creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        for name,pipe in [('stdout',process.stdout),('stderr',process.stderr)]:
            thread=threading.Thread(target=drain,args=(pipe,log_dir/(label+name+'.log'),name),daemon=True)
            thread.start();readers.append(thread)
        while True:
            if cancel_check and cancel_check():raise ExecutionError('Native execution cancelled')
            if error.is_set():raise ExecutionError(reasons[0])
            if time.monotonic()-started>timeout:raise ExecutionError('Native execution timeout')
            check_output()
            if process.poll() is not None:break
            time.sleep(.05)
    except Exception as exc:failure=exc
    finally:
        if process is not None:
            try:_stop(process)
            except Exception as exc:failure=ExecutionError('Native process cleanup could not be confirmed: '+type(exc).__name__)
            finally:
                if process.stdin is not None:process.stdin.close()
            for thread in readers:thread.join(timeout=3)
            if any(t.is_alive() for t in readers):failure=ExecutionError('Native pipe cleanup incomplete')
    result=_receipt(receipt_path,nonce) if process is not None else {'calls_executed':0,'launch_state':'not_started'}
    isolated=(isolation is not None and sys.platform=='win32' and result.get('isolation',{}).get('mechanism')=='windows_lpac'
              and result['isolation'].get('appcontainer_sid')==isolation['sid']
              and result['isolation'].get('token_verified') is True and result['isolation'].get('job_verified') is True
              and result['isolation'].get('lpac_access_check_verified') is True and result['isolation'].get('capabilities_verified') is True
              and result['isolation'].get('capabilities')==['registryRead'] and result['isolation'].get('network_capabilities')==[])
    if isolation is not None and sys.platform=='linux':
        boundary=result.get('isolation',{})
        isolated=(boundary.get('mechanism')=='linux_landlock_seccomp'
                  and type(boundary.get('landlock_abi')) is int and boundary['landlock_abi']>=6
                  and boundary.get('seccomp_mode')==2 and boundary.get('no_new_privs') is True
                  and boundary.get('network')=='syscall_default_deny' and boundary.get('processes')=='thread_only_clone'
                  and boundary.get('pid')==result.get('engine_pid') and boundary.get('enforced_before_exec') is True
                  and type(boundary.get('uid')) is int and boundary['uid']>0)
    result.update(elapsed_seconds=time.monotonic()-started,log_bytes_observed=counts,
                  output_observed=observed_output,aggregate_output_enforcement='periodic_50ms_not_os_disk_quota',filesystem_network_sandbox=isolated)
    if failure:raise ExecutionError(str(failure),result) from failure
    if error.is_set():raise ExecutionError(reasons[0],result)
    expected='windows_job_object' if sys.platform=='win32' else 'linux_rlimit'
    limits_ok=(type(result.get('memory_bytes')) is int and 0<result['memory_bytes']<=policy.memory_bytes
               and type(result.get('cpu_seconds')) is int and 0<result['cpu_seconds']<=policy.cpu_seconds)
    if sys.platform=='win32':
        limits_ok=limits_ok and result.get('active_process_limit')==2 and result.get('kill_on_job_close') is True
    else:
        limits_ok=limits_ok and result.get('file_size_os_enforced') is True and type(result.get('file_bytes')) is int and 0<result['file_bytes']<=min(policy.output_bytes,64*MIB)
    lifetime=result.get('lifetime',{})
    lifetime_ok=(lifetime=={'mechanism':'windows_private_pipe','writer':'caller_only','child_inherits_lifeline':False}
                 if sys.platform=='win32' else lifetime=={'mechanism':'linux_pdeathsig','signal':int(signal.SIGKILL),'parent_pid':os.getpid()})
    if sys.platform=='linux' and isolation is not None:
        lifetime_ok=lifetime_ok and result.get('isolation',{}).get('parent_lifetime')=={
            'mechanism':'linux_pdeathsig','signal':int(signal.SIGKILL),'parent_pid':result.get('supervisor_pid')}
    if (isolation is not None and not isolated) or not lifetime_ok or not limits_ok or result.get('mechanism')!=expected or result.get('launch_state')!='finished' or result.get('exit_code')!=0 or process.returncode!=0:
        raise ExecutionError('Native process failed or lacks completed resource receipt',result)
    try:check_output()
    except ExecutionError as exc:raise ExecutionError(str(exc),result) from exc
    return result


def archive_output(source,destination,policy):
    files,_=inventory(source,policy.output_bytes,policy.output_files)
    destination=safe_path(destination);destination.mkdir(exist_ok=False)
    consumed=0
    for path,size in files:
        target=safe_path(destination/path.relative_to(source));target.parent.mkdir(parents=True,exist_ok=True)
        written=0
        with safe_path(path).open('rb') as inp,private_open(target) as out:
            while chunk:=inp.read(1024*1024):
                written+=len(chunk);consumed+=len(chunk)
                if written>size or consumed>policy.output_bytes:raise ExecutionError('Output changed/exceeded archive budget')
                out.write(chunk)
            if written!=size:raise ExecutionError('Output changed during archive copy')


def diagnostic(output,run_dir):
    """Retain a small explicitly partial ERR on failure, never a fake valid SQL."""
    try:
        path=safe_path(Path(output)/'eplusout.err')
        if path.is_file():
            with path.open('rb') as inp,private_open(Path(run_dir)/'partial-error-diagnostic.txt') as out:
                out.write(b'PARTIAL FAILURE DIAGNOSTIC; NOT A COMPLETE ENGINE REPORT\n')
                out.write(inp.read(65536))
    except (OSError,ValueError):pass
