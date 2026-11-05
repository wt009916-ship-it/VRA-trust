"""Fail-closed Linux native boundary: Landlock ABI >=6 and libseccomp.

Install only in a dedicated single-thread child BEFORE native imports/exec.
Not a namespace/VM: known-path metadata can remain observable. File contents,
mutations and execution use explicit Landlock grants; syscalls default to EPERM.
"""
import ctypes as c
import errno
import json
import os
from pathlib import Path
import platform
import subprocess
from contextlib import contextmanager

from .native_environment import environment


class Ruleset(c.Structure):
    _fields_=[('filesystem',c.c_uint64),('network',c.c_uint64),('scoped',c.c_uint64)]


class PathRule(c.Structure):
    _pack_=1
    _fields_=[('allowed',c.c_uint64),('parent_fd',c.c_int32)]


class Compare(c.Structure):
    _fields_=[('arg',c.c_uint),('op',c.c_uint),('a',c.c_uint64),('b',c.c_uint64)]


READ_FILE=1<<2
READ_DIR=1<<3
EXECUTE=1
WRITE=(1<<1)|(1<<4)|(1<<5)|(1<<7)|(1<<8)|(1<<13)|(1<<14)
HANDLED=(1<<16)-1  # Through ABI5 IOCTL_DEV; later unhandled rights aren't claimed.
ALLOW=0x7fff0000
DENY=0x00050000|errno.EPERM

# There is deliberately no networking, ptrace/process_vm, namespaces/mounts,
# io_uring, BPF, keys, credential change, device ioctl, hardlink or symlink call.
SYSCALLS='''read write readv writev pread64 pwrite64 preadv pwritev preadv2 pwritev2
close close_range dup dup2 dup3 fcntl flock fstat newfstatat stat lstat statx statfs fstatfs
open openat openat2 lseek getdents getdents64 access faccessat faccessat2 readlink readlinkat
mkdir mkdirat rmdir unlink unlinkat rename renameat renameat2 fsync fdatasync ftruncate truncate
mmap mprotect munmap mremap madvise brk msync mincore
rt_sigaction rt_sigprocmask rt_sigreturn rt_sigsuspend rt_sigtimedwait sigaltstack
futex futex_waitv set_tid_address set_robust_list get_robust_list rseq
sched_yield sched_getaffinity sched_getparam sched_getscheduler sched_get_priority_max sched_get_priority_min
clock_gettime clock_getres clock_nanosleep nanosleep gettimeofday time times getrusage
getpid getppid gettid getuid geteuid getgid getegid getgroups uname sysinfo getrandom
getcwd chdir fchdir umask getrlimit
pipe pipe2 poll ppoll select pselect6 epoll_create epoll_create1 epoll_ctl epoll_wait epoll_pwait epoll_pwait2
eventfd eventfd2 restart_syscall arch_prctl execve exit exit_group'''.split()


def _checked(result):
    if result<0:raise OSError(c.get_errno(),'Linux isolation kernel operation failed')
    return result


def _landlock(libc,read_paths,write_paths,execute_paths):
    # Linux assigns 444/445/446 on both supported 64-bit architectures.
    abi=_checked(libc.syscall(444,0,0,1))
    if abi<6:raise RuntimeError('Landlock ABI 6+ required; refusing unrestricted native execution')
    attributes=Ruleset(HANDLED,3,3)  # TCP bind/connect denied; Unix socket and signal scopes.
    ruleset=_checked(libc.syscall(444,c.byref(attributes),c.sizeof(attributes),0))
    try:
        grants={}
        for paths,rights in [(read_paths,READ_FILE|READ_DIR),(write_paths,READ_FILE|READ_DIR|WRITE),(execute_paths,READ_FILE|EXECUTE)]:
            for name in paths:
                p=Path(name)
                if not p.is_absolute():raise ValueError('Isolation paths must be absolute')
                p=p.resolve(strict=True)
                if str(p)=='/':raise ValueError('Root filesystem cannot be granted')
                access=rights if p.is_dir() else rights & (READ_FILE|EXECUTE|(1<<1)|(1<<14))
                grants[str(p)]=grants.get(str(p),0)|access
        for path,rights in sorted(grants.items()):
            fd=os.open(path,os.O_PATH|os.O_CLOEXEC)
            try:
                rule=PathRule(rights,fd)
                _checked(libc.syscall(445,ruleset,1,c.byref(rule),0))
            finally:os.close(fd)
        _checked(libc.prctl(38,1,0,0,0))  # PR_SET_NO_NEW_PRIVS
        if libc.prctl(39,0,0,0,0)!=1:raise RuntimeError('no_new_privs readback failed')
        _checked(libc.syscall(446,ruleset,0))
        return abi
    finally:os.close(ruleset)


def _seccomp(lib,libc):
    signatures=[('seccomp_init',[c.c_uint32],c.c_void_p),('seccomp_release',[c.c_void_p],None),
                ('seccomp_syscall_resolve_name',[c.c_char_p],c.c_int),
                ('seccomp_rule_add_array',[c.c_void_p,c.c_uint32,c.c_int,c.c_uint,c.POINTER(Compare)],c.c_int),
                ('seccomp_attr_set',[c.c_void_p,c.c_uint,c.c_uint32],c.c_int),('seccomp_load',[c.c_void_p],c.c_int)]
    for name,args,result in signatures:
        fn=getattr(lib,name);fn.argtypes=args;fn.restype=result
    ctx=lib.seccomp_init(DENY)
    if not ctx:raise RuntimeError('Cannot create syscall filter')
    def require(result):
        if result<0:raise OSError(-result,'Cannot install syscall policy')
    def add(name,action=ALLOW,comparisons=(),optional=False):
        number=lib.seccomp_syscall_resolve_name(name.encode('ascii'))
        if number<0:
            if optional:return
            raise RuntimeError('Required syscall unknown to libseccomp: '+name)
        array=(Compare*len(comparisons))(*comparisons) if comparisons else None
        require(lib.seccomp_rule_add_array(ctx,action,number,len(comparisons),array))
    try:
        require(lib.seccomp_attr_set(ctx,2,0x80000000))  # KILL_PROCESS on a different syscall ABI.
        require(lib.seccomp_attr_set(ctx,3,1))  # no_new_privs required
        require(lib.seccomp_attr_set(ctx,4,1))  # TSYNC; all existing threads must accept filter
        for name in SYSCALLS:add(name,optional=True)  # Some legacy calls don't exist on aarch64.
        # glibc falls back to clone only for ENOSYS, not EPERM. Only actual
        # CLONE_THREAD|VM|SIGHAND with known pthread flags is then permitted.
        add('clone3',0x00050000|errno.ENOSYS)
        required=0x100|0x800|0x10000
        optional=0x200|0x400|0x40000|0x80000|0x100000|0x200000|0x1000000
        add('clone',comparisons=[Compare(0,7,0xffffffffffffffff^optional,required)])
        add('prlimit64',comparisons=[Compare(0,4,0,0)])
        for option in [15,16,21,39]:add('prctl',comparisons=[Compare(0,4,option,0)])
        add('kill',comparisons=[Compare(0,4,os.getpid(),0)])
        add('tgkill',comparisons=[Compare(0,4,os.getpid(),0)])
        add('sched_setaffinity',comparisons=[Compare(0,4,0,0)])
        require(lib.seccomp_load(ctx))
        if libc.prctl(21,0,0,0,0)!=2 or libc.prctl(39,0,0,0,0)!=1:
            raise RuntimeError('Seccomp/no_new_privs readback failed')
    finally:lib.seccomp_release(ctx)


def install(read_paths,write_paths,execute_paths):
    if platform.system()!='Linux' or platform.machine() not in {'x86_64','aarch64'}:
        raise RuntimeError('Linux isolation requires x86_64 or aarch64')
    if os.geteuid()==0:raise RuntimeError('Native isolation requires a non-root service account')
    if len(list(Path('/proc/self/task').iterdir()))!=1:
        raise RuntimeError('Install isolation before starting any threads')
    # Resolve libseccomp before restricting filesystem lookup; do not invoke an
    # external ldconfig or compiler to discover libraries in a preexec child.
    libc=c.CDLL(None,use_errno=True);libc.syscall.restype=c.c_long
    libc.prctl.argtypes=[c.c_int,c.c_ulong,c.c_ulong,c.c_ulong,c.c_ulong];libc.prctl.restype=c.c_int
    seccomp=c.CDLL('libseccomp.so.2',use_errno=True)
    abi=_landlock(libc,read_paths,write_paths,execute_paths)
    _seccomp(seccomp,libc)
    return {'mechanism':'linux_landlock_seccomp','landlock_abi':abi,'minimum_abi':6,
            'filesystem_handled_mask':HANDLED,'network':'syscall_default_deny',
            'processes':'thread_only_clone','seccomp_mode':2,'no_new_privs':True,
            'unix_socket_signal_scope':True,'metadata_namespace_isolation':False,'uid':os.getuid()}


def runtime_reads():
    """Public OS runtime locations, not home directories or the full /etc tree."""
    paths=['/lib','/lib64','/usr/lib','/usr/lib64','/usr/local/lib',
           '/etc/ld.so.cache','/etc/localtime','/usr/share/zoneinfo',
           '/proc/cpuinfo','/proc/meminfo','/proc/self/status','/proc/self/stat',
           '/sys/devices/system/cpu','/dev/null','/dev/urandom']
    return [str(Path(p).resolve()) for p in paths if Path(p).exists()]


def runtime_loader():
    # Landlock checks EXECUTE for the ELF interpreter as well as the program.
    # Grant the architecture's exact system loader, never a library directory.
    name={'x86_64':'/lib64/ld-linux-x86-64.so.2',
          'aarch64':'/lib/ld-linux-aarch64.so.1'}.get(platform.machine())
    if name is None:raise RuntimeError('Unsupported ELF runtime architecture')
    loader=Path(name).resolve(strict=True)
    if not loader.is_file():raise RuntimeError('System ELF loader unavailable')
    return str(loader)


@contextmanager
def launch(command,specification):
    """Trusted, single-thread supervisor only; receipt pipe closes before exec.

    The untrusted program never inherits a writable policy receipt descriptor.
    Popen's exec handshake also fails if installation/exec itself fails.
    """
    if len(list(Path('/proc/self/task').iterdir()))!=1:
        raise RuntimeError('Linux launch requires a dedicated single-thread supervisor')
    read_fd,write_fd=os.pipe2(os.O_CLOEXEC)
    process=None
    supervisor_pid=os.getpid()
    def prepare():
        from .execution_lifetime import bind_linux_parent
        lifetime=bind_linux_parent(supervisor_pid)
        loader=runtime_loader()
        receipt=install(runtime_reads()+specification['read_paths'],[specification['work']],
                        specification['execute_paths']+[loader])
        receipt['elf_loader']=loader
        receipt['parent_lifetime']=lifetime
        receipt.update(pid=os.getpid(),enforced_before_exec=True,inherited_handles='standard_streams_only')
        data=json.dumps(receipt).encode('utf-8')
        if len(data)>4096 or os.write(write_fd,data)!=len(data):raise RuntimeError('Incomplete isolation handshake')
        os.close(write_fd)
    try:
        process=subprocess.Popen(command,cwd=specification['work'],stdin=subprocess.DEVNULL,
            env=environment(specification['work']),close_fds=True,pass_fds=(write_fd,),preexec_fn=prepare)
        os.close(write_fd);write_fd=None
        data=os.read(read_fd,4097)
        if len(data)>4096:raise RuntimeError('Oversized isolation handshake')
        receipt=json.loads(data)
        if receipt.get('pid')!=process.pid or receipt.get('enforced_before_exec') is not True:
            raise RuntimeError('Invalid isolation handshake')
        process.isolation_receipt=receipt
        yield process
    finally:
        if write_fd is not None:os.close(write_fd)
        os.close(read_fd)
        if process is not None and process.poll() is None:
            process.kill();process.wait(timeout=5)
