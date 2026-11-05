"""Owned synthetic process tree; stable handles prevent PID-reuse cleanup races."""
from contextlib import ExitStack
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


class ProcessHandle:
    def __init__(self, pid):
        self.pid = pid
        if sys.platform == 'win32':
            import ctypes as c
            from ctypes import wintypes as w
            self.c = c
            self.kernel = c.WinDLL('kernel32', use_last_error=True)
            for name, args, result in [
                ('OpenProcess', [w.DWORD, w.BOOL, w.DWORD], w.HANDLE),
                ('WaitForSingleObject', [w.HANDLE, w.DWORD], w.DWORD),
                ('TerminateProcess', [w.HANDLE, w.UINT], w.BOOL),
                ('CloseHandle', [w.HANDLE], w.BOOL),
            ]:
                fn = getattr(self.kernel, name); fn.argtypes = args; fn.restype = result
            self.handle = self.kernel.OpenProcess(0x100001, False, pid)
            if not self.handle: raise c.WinError(c.get_last_error())
        else:
            self.handle = os.pidfd_open(pid)

    def exited(self):
        if sys.platform == 'win32':
            value = self.kernel.WaitForSingleObject(self.handle, 0)
            if value not in (0, 258): raise self.c.WinError(self.c.get_last_error())
            return value == 0
        import select
        return bool(select.select([self.handle], [], [], 0)[0])

    def stop(self):
        if self.exited(): return
        if sys.platform == 'win32':
            if not self.kernel.TerminateProcess(self.handle, 79):
                if not self.exited(): raise self.c.WinError(self.c.get_last_error())
        else:
            try: signal.pidfd_send_signal(self.handle, signal.SIGKILL)
            except ProcessLookupError: pass

    def close(self):
        if sys.platform == 'win32': self.kernel.CloseHandle(self.handle)
        else: os.close(self.handle)


def probe(root, target='caller', observation=2):
    """Caller is disposable; the outer harness owns staging and recovery."""
    root = Path(root).resolve(); root.mkdir(parents=True, exist_ok=False)
    control = root/'control'; control.mkdir()
    logs = root/'logs'; logs.mkdir()
    repo = Path(__file__).resolve().parents[1]
    handles = []; caller = None; result = None
    with ExitStack() as stack:
        if sys.platform == 'win32':
            from backend.native_windows import staging
            from tests.test_native_isolation import stage_python
            scope = stack.enter_context(staging())
            python = stage_python(scope); work = scope['work']
            spec = {'sid': scope['sid'], 'work': str(work)}
            extra = [str(scope['profile_root'])]
            removed = [scope['root'], scope['profile_root']]
        else:
            from backend.private_storage import private_temporary
            private = stack.enter_context(private_temporary(root))
            work = private/'output'; work.mkdir()
            python = Path(getattr(sys, '_base_executable', sys.executable)).resolve()
            spec = {'mechanism': 'linux_landlock_seccomp', 'work': str(work),
                    'read_paths': [str(Path(sys.base_prefix)/'lib')], 'execute_paths': [str(python)]}
            extra = []; removed = [private]
        code = "from pathlib import Path; import sys,time; assert sys.stdin.buffer.read() == b''; Path('ready').write_text('synthetic'); time.sleep(60)"
        args = dict(command=[str(python), '-I', '-B', '-c', code], work=str(control), log_dir=str(logs),
                    timeout=55, output=str(work), isolation=spec, extra_output_roots=extra)
        caller_code = ('import sys; sys.path.insert(0,' + repr(str(repo)) + '); '
                       'from backend.execution import supervise,Policy; '
                       'from dataclasses import replace; '
                       'supervise(policy=replace(Policy(),memory_bytes=512*1024**2,cpu_seconds=10),**' + repr(args) + ')')
        interpreter = getattr(sys, '_base_executable', sys.executable) if sys.platform == 'win32' else sys.executable
        try:
            with (root/'caller.log').open('wb') as stream:
                caller = subprocess.Popen([interpreter, '-c', caller_code], stdout=stream, stderr=stream,
                    stdin=subprocess.DEVNULL, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            deadline = time.monotonic()+35; receipt = None
            while time.monotonic() < deadline:
                try:
                    receipt = json.loads((control/'engine-request.receipt.json').read_text())
                    if receipt.get('state') == 'launched' and (work/'ready').exists(): break
                except (OSError, ValueError): pass
                if caller.poll() is not None: raise RuntimeError('Caller failed: '+(root/'caller.log').read_text())
                time.sleep(.02)
            else: raise RuntimeError('Synthetic child did not become ready')
            # Capture exact kernel objects BEFORE killing their parent.
            for name in ('supervisor_pid', 'engine_pid'): handles.append(ProcessHandle(receipt[name]))
            assert not any(handle.exited() for handle in handles)
            started = time.monotonic()
            if target == 'caller': caller.kill(); caller.wait(timeout=5)
            elif target == 'supervisor': handles[0].stop()
            else: raise ValueError(target)
            while time.monotonic()-started < observation and not all(h.exited() for h in handles): time.sleep(.01)
            result = {'platform': sys.platform, 'target': target, 'elapsed_seconds': time.monotonic()-started,
                      'supervisor_exited': handles[0].exited(), 'engine_exited': handles[1].exited(),
                      'receipt': receipt, 'scope': 'synthetic isolated supervision chain, not full ASGI recovery'}
        finally:
            if caller is not None and caller.poll() is None: caller.kill(); caller.wait(timeout=5)
            for handle in handles: handle.stop()
            deadline = time.monotonic()+5
            while handles and not all(h.exited() for h in handles) and time.monotonic()<deadline: time.sleep(.02)
            try: assert all(h.exited() for h in handles), 'Owned test tree cleanup incomplete'
            finally:
                for handle in handles: handle.close()
    result['outer_harness_staging_removed'] = all(not path.exists() for path in removed)
    assert result['outer_harness_staging_removed']
    return result


if __name__ == '__main__':
    destination = Path(sys.argv[1])
    value = probe(destination, sys.argv[2] if len(sys.argv)>2 else 'caller')
    (destination/'observations.json').write_text(json.dumps(value, indent=2), encoding='utf-8')
    print(json.dumps(value, indent=2))
