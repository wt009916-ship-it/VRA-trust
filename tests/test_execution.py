"""Real bounded child processes; probes are not EnergyPlus accuracy evidence."""
import json
import os
import sys
import threading
import time
from dataclasses import replace

import pytest
from pathlib import Path

from backend import execution as ex


def assert_stopped(pid):
    assert type(pid) is int and pid>0
    if sys.platform=='win32':
        import ctypes as c
        from ctypes import wintypes as w
        kernel=c.WinDLL('kernel32',use_last_error=True)
        kernel.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];kernel.OpenProcess.restype=w.HANDLE
        kernel.WaitForSingleObject.argtypes=[w.HANDLE,w.DWORD];kernel.WaitForSingleObject.restype=w.DWORD
        kernel.CloseHandle.argtypes=[w.HANDLE];kernel.CloseHandle.restype=w.BOOL
        handle=kernel.OpenProcess(0x100000,False,pid)
        if not handle:
            assert c.get_last_error()==87  # PID no longer exists
            return
        try:assert kernel.WaitForSingleObject(handle,2000)==0
        finally:kernel.CloseHandle(handle)
    else:
        try:os.kill(pid,0)
        except ProcessLookupError:return
        assert Path('/proc',str(pid),'stat').read_text().split(') ',1)[1].startswith('Z ')


def run_probe(tmp_path, code, *, policy=None, timeout=8, cancel=None):
    work=tmp_path/'work';work.mkdir()
    logs=tmp_path/'logs';logs.mkdir()
    output=work/'output';output.mkdir()
    # Windows venv redirector would add a third process; probe the real Python.
    python=getattr(sys,'_base_executable',sys.executable)
    return ex.supervise([python,'-c',code],work,logs,policy or replace(ex.Policy(),memory_bytes=256*ex.MIB,cpu_seconds=5),
                        timeout,output=output,cancel_check=cancel)


def test_native_success_receipt_and_archive(tmp_path):
    receipt=run_probe(tmp_path,"from pathlib import Path; Path('output/result').write_text('actual child'); print('completed')")
    assert receipt['calls_executed']==1 and receipt['exit_code']==0
    assert_stopped(receipt['supervisor_pid']);assert_stopped(receipt['engine_pid'])
    assert receipt['filesystem_network_sandbox'] is False
    assert (tmp_path/'logs/stdout.log').read_text().strip()=='completed'
    ex.archive_output(tmp_path/'work/output',tmp_path/'archive',ex.Policy())
    assert (tmp_path/'archive/result').read_text()=='actual child'


@pytest.mark.parametrize('mode',['timeout','cancel','log','output','files','exit','memory','cpu'])
def test_native_failure_has_no_success_and_recovers(tmp_path,mode):
    policy=replace(ex.Policy(),memory_bytes=256*ex.MIB,cpu_seconds=1 if mode=='cpu' else 5,log_bytes=4096,output_bytes=65536,output_files=3)
    code={
        'timeout':'import time; time.sleep(20)',
        'cancel':'import time; time.sleep(20)',
        'log':"import sys; sys.stdout.write('x'*1000000); sys.stdout.flush()",
        'output':"from pathlib import Path; Path('output/big').write_bytes(b'x'*1000000)",
        'files':"from pathlib import Path; [Path('output/'+str(i)).write_text('x') for i in range(10)]",
        'exit':'raise SystemExit(7)',
        'memory':"data=bytearray(512*1024**2)",
        'cpu':'while True: pass',
    }[mode]
    start=time.monotonic()
    with pytest.raises(ex.ExecutionError) as failure:
        run_probe(tmp_path,code,policy=policy,timeout=.8 if mode=='timeout' else 8,
                  cancel=(lambda:time.monotonic()-start>1) if mode=='cancel' else None)
    assert time.monotonic()-start<12
    if mode=='cpu':assert 'timeout' not in str(failure.value).lower()
    if mode=='memory':assert 'MemoryError' in (tmp_path/'logs/stderr.log').read_text()
    assert failure.value.receipt['calls_executed'] in (1,None)
    if failure.value.receipt.get('engine_pid'):assert_stopped(failure.value.receipt['engine_pid'])
    if failure.value.receipt.get('supervisor_pid'):assert_stopped(failure.value.receipt['supervisor_pid'])
    assert (tmp_path/'logs/stdout.log').stat().st_size<=4096
    again=tmp_path/'recovery';again.mkdir()
    assert run_probe(again,'print(42)')['exit_code']==0


def test_archive_admission_retains_old_artifacts(tmp_path):
    old=tmp_path/'old';old.write_bytes(b'original')
    policy=replace(ex.Policy(),archive_bytes=16)
    with pytest.raises(ex.ExecutionError,match='capacity'):
        with ex.archive_slot(tmp_path,[tmp_path],policy):pytest.fail('admitted')
    assert old.read_bytes()==b'original'


def test_archive_lane_wait_can_cancel(tmp_path):
    errors=[];entered=threading.Event()
    def contender():
        entered.set()
        try:
            with ex.archive_slot(tmp_path,[tmp_path],ex.Policy(),lambda:True):pytest.fail('admitted')
        except ex.ExecutionError as exc:errors.append(str(exc))
    with ex.archive_slot(tmp_path,[tmp_path],ex.Policy()):
        thread=threading.Thread(target=contender);thread.start();assert entered.wait(2);thread.join(3)
        assert not thread.is_alive()
    assert len(errors)==1 and 'cancelled' in errors[0]


def test_missing_or_wrong_receipt_is_unknown(tmp_path):
    path=tmp_path/'receipt.json'
    assert ex._receipt(path,'nonce')['calls_executed'] is None
    path.write_text(json.dumps({'state':'finished','engine_pid':123,'nonce':'wrong'}))
    assert ex._receipt(path,'nonce')['calls_executed'] is None


def test_output_copy_refuses_overflow(tmp_path):
    source=tmp_path/'source';source.mkdir();(source/'original').write_bytes(b'12345')
    with pytest.raises(ex.ExecutionError):ex.archive_output(source,tmp_path/'dest',replace(ex.Policy(),output_bytes=4))
    assert not (tmp_path/'dest').exists() and (source/'original').read_bytes()==b'12345'


def test_completed_child_without_valid_policy_receipt_rejected(tmp_path,monkeypatch):
    original=ex._receipt
    def corrupt(path,nonce):return {**original(path,nonce),'memory_bytes':None}
    monkeypatch.setattr(ex,'_receipt',corrupt)
    with pytest.raises(ex.ExecutionError,match='receipt'):run_probe(tmp_path,'print(42)')


def test_child_process_limit_or_group_cleanup(tmp_path):
    code="import subprocess,sys,time; from pathlib import Path; p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(20)']); Path('child.pid').write_text(str(p.pid)); time.sleep(20)"
    with pytest.raises(ex.ExecutionError) as failure:run_probe(tmp_path,code,timeout=2)
    assert failure.value.receipt['calls_executed']==1
    assert_stopped(failure.value.receipt['engine_pid'])
    assert_stopped(failure.value.receipt['supervisor_pid'])
    child=tmp_path/'work/child.pid'
    if sys.platform=='linux':assert_stopped(int(child.read_text()))
    else:assert not child.exists()  # third process cannot enter the job


def test_existing_run_evidence_is_never_overwritten(tmp_path):
    from backend import core
    original=tmp_path/'manifest.json';original.write_bytes(b'preserved old evidence')
    with pytest.raises(core.ValidationError,match='already contains'):
        core.run_simulation('reference_5zone','baseline','reference_scenario',tmp_path)
    assert original.read_bytes()==b'preserved old evidence'
    assert not (tmp_path/'result.json').exists()
