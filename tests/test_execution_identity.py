"""Linux group cleanup retains the actual session leader until the signal."""
import os
import json
import signal
import subprocess
import sys
import time

import pytest

from backend import execution as ex
from tests.test_execution import run_probe

pytestmark=pytest.mark.skipif(sys.platform!='linux',reason='Linux waitid/WNOWAIT process-group identity')


@pytest.mark.parametrize('mode',['complete','timeout','cancel'])
def test_group_is_signaled_before_its_leader_can_be_reused(tmp_path,monkeypatch,mode):
    original=os.killpg;events=[]
    def signal_owned(group,sig):
        # Fail the test BEFORE forwarding if no longer our unreaped child.
        state=os.waitid(os.P_PID,group,os.WEXITED|os.WNOHANG|os.WNOWAIT)
        assert sig==signal.SIGKILL
        assert state is None or state.si_pid==group
        events.append({'group':group,'exited':state is not None})
        original(group,sig)
    monkeypatch.setattr(ex.os,'killpg',signal_owned)
    start=time.monotonic()
    if mode=='complete':
        result=run_probe(tmp_path,'print("real completed task")')
        assert result['exit_code']==0 and events[0]['exited']
    else:
        with pytest.raises(ex.ExecutionError,match='cancelled' if mode=='cancel' else 'timeout'):
            run_probe(tmp_path,'import time; time.sleep(15)',timeout=1,
                      cancel=(lambda:time.monotonic()-start>.5) if mode=='cancel' else None)
        assert not events[0]['exited']
    assert len(events)==1
    with pytest.raises(ChildProcessError):os.waitid(os.P_PID,events[0]['group'],os.WEXITED|os.WNOHANG|os.WNOWAIT)


@pytest.mark.parametrize('reaper',['popen','external'])
def test_reaped_child_refuses_any_group_signal(tmp_path,monkeypatch,reaper):
    process=subprocess.Popen([sys.executable,'-c','pass'],start_new_session=True)
    if reaper=='popen':assert process.wait(timeout=5)==0
    else:
        pid,status=os.waitpid(process.pid,0)
        assert pid==process.pid and os.waitstatus_to_exitcode(status)==0 and process.returncode is None
    def forbidden(*args):pytest.fail('Signal attempted after child identity was released')
    monkeypatch.setattr(ex.os,'killpg',forbidden)
    try:
        with pytest.raises(ex.ExecutionError,match='reaped|ownership lost'):ex._stop(process)
    finally:process.returncode=0  # the fixture already performed the real wait


def test_completion_observer_does_not_reap_child(tmp_path):
    process=subprocess.Popen([sys.executable,'-c','pass'],start_new_session=True)
    try:
        deadline=time.monotonic()+5
        while not ex._finished(process) and time.monotonic()<deadline:time.sleep(.01)
        assert ex._finished(process) and process.returncode is None
        assert ex._finished(process) and os.waitid(os.P_PID,process.pid,os.WEXITED|os.WNOWAIT).si_pid==process.pid
    finally:ex._stop(process)
    assert process.returncode==0


@pytest.mark.parametrize('disposition',['ignore','custom','no_child_wait'])
def test_nondefault_sigchld_refuses_before_native_launch(tmp_path,disposition):
    # The disposition changes only in this separate test process, not pytest.
    code='''
import ctypes as c,json,os,signal,subprocess,sys
from pathlib import Path
from backend import execution as ex
from tests.test_execution import run_probe
if sys.argv[2]=='no_child_wait':
    number={'x86_64':13,'aarch64':134}[os.uname().machine]
    libc=c.CDLL(None,use_errno=True);libc.syscall.restype=c.c_long
    action=(c.c_ulong*4)();action[1]=2
    assert libc.syscall(c.c_long(number),c.c_int(signal.SIGCHLD),c.byref(action),c.c_void_p(),c.c_size_t(8))==0
    assert signal.getsignal(signal.SIGCHLD)==signal.SIG_DFL  # Python alone misses this.
    child=subprocess.Popen([sys.executable,'-c','pass'])
    try:os.waitpid(child.pid,0)
    except ChildProcessError:child.returncode=0
    else:raise AssertionError('Kernel auto-reaping was not exercised')
else:signal.signal(signal.SIGCHLD,signal.SIG_IGN if sys.argv[2]=='ignore' else lambda *args:None)
try:
    run_probe(Path(sys.argv[1]),'from pathlib import Path; Path("launched").touch()')
except ex.ExecutionError as error:
    assert 'SIGCHLD' in str(error) and error.receipt['calls_executed']==0
    print(json.dumps({'refused_before_launch':True}))
else:raise AssertionError('Nondefault reaper allowed')
'''
    result=subprocess.run([sys.executable,'-c',code,str(tmp_path),disposition],capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stderr
    assert json.loads(result.stdout)=={'refused_before_launch':True}
    assert not (tmp_path/'work/launched').exists()
