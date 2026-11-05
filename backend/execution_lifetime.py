"""Fail closed when the owner of a dedicated native supervisor disappears.

Windows uses an anonymous pipe whose only writer belongs to the caller, never
a PID lookup. Linux binds both generations with kernel parent-death SIGKILL.
Linux's binding follows the creating thread; its exit also aborts the task.
"""
import os
import signal
import stat
import sys
import threading


def bind_linux_parent(expected_pid):
    import ctypes as c
    if type(expected_pid) is not int or expected_pid <= 1:
        raise RuntimeError('Invalid supervisor parent identity')
    libc = c.CDLL(None, use_errno=True)
    libc.prctl.argtypes = [c.c_int, c.c_ulong, c.c_ulong, c.c_ulong, c.c_ulong]
    libc.prctl.restype = c.c_int
    if libc.prctl(1, signal.SIGKILL, 0, 0, 0) != 0:
        raise OSError(c.get_errno(), 'Cannot bind parent lifetime')
    actual = c.c_int()
    if libc.prctl(2, c.cast(c.byref(actual), c.c_void_p).value, 0, 0, 0) != 0 or actual.value != signal.SIGKILL:
        raise RuntimeError('Parent lifetime policy readback failed')
    # A parent that died before prctl does not generate a retrospective signal.
    # Reparenting changes getppid; never attach to a newly reused PID.
    if os.getppid() != expected_pid:
        raise RuntimeError('Native owner already exited')
    return {'mechanism': 'linux_pdeathsig', 'signal': int(signal.SIGKILL), 'parent_pid': expected_pid}


def bind_supervisor(expected_pid):
    if not stat.S_ISFIFO(os.fstat(0).st_mode):
        raise RuntimeError('Native supervisor requires a private caller lifeline')
    if sys.platform == 'linux':
        return bind_linux_parent(expected_pid)
    if sys.platform != 'win32':
        raise RuntimeError('Unsupported native lifetime boundary')

    def watch():
        # EOF, unexpected bytes, or a read error all fail closed. Nothing is
        # ever written to this pipe; native children receive a fresh DEVNULL.
        try: os.read(0, 1)
        finally: os._exit(71)

    watcher = threading.Thread(target=watch, name='native-owner-lifeline', daemon=True)
    watcher.start()
    return {'mechanism': 'windows_private_pipe', 'writer': 'caller_only', 'child_inherits_lifeline': False}
