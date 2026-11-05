"""Real owner/supervisor death, plus refusal of unbound execution receipts."""
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from backend import execution as ex
from tests.lifetime_probe import probe
from tests.test_execution import run_probe


@pytest.mark.parametrize('target', ['caller', 'supervisor'])
def test_isolated_child_exits_when_its_owner_dies(tmp_path, target):
    if sys.platform == 'linux':
        if os.geteuid() == 0: pytest.skip('Requires non-root real Linux isolation')
        libc = ctypes.CDLL(None, use_errno=True); libc.syscall.restype = ctypes.c_long
        if libc.syscall(444, 0, 0, 1) < 6: pytest.skip('Landlock ABI 6+ required')
    result = probe(tmp_path/'owned', target, observation=5)
    assert result['supervisor_exited'] and result['engine_exited'], result
    assert result['outer_harness_staging_removed']
    recovery = tmp_path/'recovery'; recovery.mkdir()
    assert run_probe(recovery, 'print("recovered")')['exit_code'] == 0


@pytest.mark.parametrize('lifetime', [None, {}, {'mechanism':'invented'},
    {'mechanism':'linux_pdeathsig','signal':9,'parent_pid':1},
    {'mechanism':'windows_private_pipe','writer':'caller_only','child_inherits_lifeline':True}])
def test_success_without_lifetime_receipt_is_rejected(tmp_path, monkeypatch, lifetime):
    original = ex._receipt
    monkeypatch.setattr(ex, '_receipt', lambda path, nonce: {**original(path, nonce), 'lifetime':lifetime})
    with pytest.raises(ex.ExecutionError, match='receipt'):
        run_probe(tmp_path, 'print("actual process ran, untrusted receipt rejected")')


def test_worker_without_private_lifeline_refuses_before_engine_launch(tmp_path):
    request = tmp_path/'request.json'
    sentinel = tmp_path/'must-not-exist'
    python = getattr(sys, '_base_executable', sys.executable)
    request.write_text(json.dumps({'parent_pid':os.getpid(), 'nonce':'synthetic',
        'command':[python, '-c', 'from pathlib import Path; Path('+repr(str(sentinel))+').touch()'],
        'memory_bytes':256*1024**2, 'cpu_seconds':5, 'file_bytes':65536}))
    worker = Path(ex.__file__).with_name('engine_worker.py')
    result = subprocess.run([python,str(worker),str(request)],stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
    assert result.returncode == 70
    assert not sentinel.exists() and not request.with_suffix('.receipt.json').exists()


@pytest.mark.skipif(sys.platform!='linux', reason='Linux kernel parent identity race guard')
def test_linux_wrong_parent_refuses_before_engine_launch(tmp_path):
    python = getattr(sys, '_base_executable', sys.executable)
    code = 'import os; from backend.execution_lifetime import bind_linux_parent; bind_linux_parent(os.getpid())'
    result = subprocess.run([python, '-c', code], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)
    assert result.returncode != 0 and b'Native owner already exited' in result.stderr


def test_native_stdin_is_eof_not_caller_lifeline(tmp_path):
    # A worker waiting for stdin must complete while the caller stays alive.
    receipt = run_probe(tmp_path, 'import sys; assert sys.stdin.buffer.read() == b""; print("EOF")')
    assert receipt['exit_code'] == 0
