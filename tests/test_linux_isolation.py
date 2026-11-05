"""Real unprivileged Linux kernel probes; Windows/old kernels are explicit skips."""
import ctypes
from dataclasses import replace
import errno
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import pytest

from backend import execution as ex

pytestmark=pytest.mark.skipif(sys.platform!='linux',reason='Linux Landlock/seccomp boundary')


@pytest.fixture(autouse=True)
def supported_kernel():
    if sys.platform!='linux':return
    if os.geteuid()==0:pytest.skip('Real isolation probes require a non-root test account')
    libc=ctypes.CDLL(None,use_errno=True);libc.syscall.restype=ctypes.c_long
    abi=libc.syscall(444,0,0,1)
    if abi<6:pytest.skip('Landlock ABI 6+ unavailable; product must reject isolated execution')


def run_probe(tmp_path,code,*,read_paths=(),policy=None,timeout=8,cancel=None):
    work=tmp_path/'output';work.mkdir()
    control=tmp_path/'control';control.mkdir()
    logs=tmp_path/'logs';logs.mkdir()
    # Use the stdlib interpreter, not a copied venv executable which tries to
    # open a private pyvenv.cfg outside the deliberately granted runtime paths.
    python=Path(getattr(sys,'_base_executable',sys.executable)).resolve()
    # setup-python/pyenv may keep the standard library outside /usr/lib.
    libraries=[Path(sys.base_prefix)/'lib']
    spec={'mechanism':'linux_landlock_seccomp','work':str(work),
          'read_paths':list(map(str,[*read_paths,*libraries])),'execute_paths':[str(python)]}
    return ex.supervise([python,'-I','-B','-c',code],control,logs,
        policy or replace(ex.Policy(),memory_bytes=256*ex.MIB,cpu_seconds=5),timeout,
        output=work,isolation=spec,cancel_check=cancel)


def test_real_files_network_fds_threads_and_process_boundary(tmp_path,monkeypatch):
    from tests.test_execution import assert_stopped
    allowed=tmp_path/'input';allowed.write_text('read-only-reference')
    outside=tmp_path/'outside';outside.write_text('synthetic-private-canary')
    assert outside.read_text()=='synthetic-private-canary'
    control=subprocess.run([sys.executable,'-c','print("ordinary-process-control")'],capture_output=True,text=True,timeout=5,check=True)
    assert control.stdout.strip()=='ordinary-process-control'
    monkeypatch.setenv('VRA_CANARY_SECRET','synthetic-environment-value')
    listeners={};retained=None;source_fd=os.open(outside,os.O_RDONLY)
    try:
        for candidate in range(180,220):
            try:os.fstat(candidate)
            except OSError as error:
                if error.errno==errno.EBADF:
                    os.dup2(source_fd,candidate,inheritable=True);retained=candidate;break
        assert retained is not None
        for label,family,kind,host in [('tcp4',socket.AF_INET,socket.SOCK_STREAM,'127.0.0.1'),
             ('udp4',socket.AF_INET,socket.SOCK_DGRAM,'127.0.0.1'),('tcp6',socket.AF_INET6,socket.SOCK_STREAM,'::1'),
             ('udp6',socket.AF_INET6,socket.SOCK_DGRAM,'::1')]:
            server=socket.socket(family,kind);listeners[label]=server;server.bind((host,0));server.settimeout(.2)
            if kind==socket.SOCK_STREAM:server.listen(2)
            with socket.socket(family,kind) as client:
                client.settimeout(1)
                if kind==socket.SOCK_STREAM:
                    client.connect(server.getsockname());connection,_=server.accept();connection.close()
                else:client.sendto(b'positive-control',server.getsockname());assert server.recv(100)==b'positive-control'
        args={'input':str(allowed),'outside':str(outside),'control':str(tmp_path/'control/engine-request.json'),
              'fd':retained,'ports':{key:value.getsockname()[1] for key,value in listeners.items()}}
        code='args='+repr(args)+'\n'+'''
import os,json,socket,subprocess,sys,threading
from pathlib import Path
r={}
def attempt(name,fn):
 try:fn();r[name]='allowed'
 except OSError as exc:r[name]=exc.errno
attempt('input_read',lambda:Path(args['input']).read_text())
attempt('outside_read',lambda:Path(args['outside']).read_text())
attempt('outside_write',lambda:Path(args['outside']).write_text('bad'))
attempt('input_write',lambda:Path(args['input']).write_text('bad'))
attempt('control_read',lambda:Path(args['control']).read_bytes())
attempt('control_write',lambda:Path(args['control']).write_text('bad'))
attempt('output_write',lambda:Path('actual-output').write_text('result'))
attempt('chmod',lambda:os.chmod(args['outside'],0o777))
attempt('hardlink',lambda:os.link(args['outside'],'linked'))
attempt('symlink',lambda:os.symlink(args['outside'],'linked'))
attempt('inherited_fd',lambda:os.read(args['fd'],100))
attempt('setsid',os.setsid)
attempt('spawn',lambda:subprocess.run([sys.executable,'-c','pass'],check=True))
attempt('replace_with_shell',lambda:os.execve('/bin/sh',['sh','-c','exit 99'],{}))
for name,family,kind,host in [('tcp4',socket.AF_INET,socket.SOCK_STREAM,'127.0.0.1'),
 ('udp4',socket.AF_INET,socket.SOCK_DGRAM,'127.0.0.1'),('tcp6',socket.AF_INET6,socket.SOCK_STREAM,'::1'),
 ('udp6',socket.AF_INET6,socket.SOCK_DGRAM,'::1')]:
 def send():
  with socket.socket(family,kind) as client:
   client.settimeout(.5)
   if kind==socket.SOCK_STREAM:client.connect((host,args['ports'][name]))
   else:client.sendto(b'isolated-probe',(host,args['ports'][name]))
 attempt(name,send)
values=[]
threads=[threading.Thread(target=lambda:values.append(sum(range(10000)))) for _ in range(8)]
for t in threads:t.start()
for t in threads:t.join(2)
r['thread_results']=values
r['secret_present']='VRA_CANARY_SECRET' in os.environ
r['known_path_metadata_visible']=Path(args['outside']).stat().st_size
Path('observations.json').write_text(json.dumps(r))
'''
        receipt=run_probe(tmp_path,code,read_paths=[allowed])
        observed=json.loads((tmp_path/'output/observations.json').read_text())
        assert observed=={'input_read':'allowed','outside_read':13,'outside_write':13,'input_write':13,
            'control_read':13,'control_write':13,'output_write':'allowed','chmod':1,'hardlink':1,'symlink':1,
            'inherited_fd':9,'setsid':1,'spawn':1,'replace_with_shell':13,'tcp4':1,'udp4':1,'tcp6':1,'udp6':1,
            'thread_results':[49995000]*8,'secret_present':False,'known_path_metadata_visible':len('synthetic-private-canary')}
        assert receipt['filesystem_network_sandbox'] is True
        assert receipt['isolation']['uid']==os.getuid() and receipt['isolation']['enforced_before_exec'] is True
        assert_stopped(receipt['supervisor_pid']);assert_stopped(receipt['engine_pid'])
        assert outside.read_text()=='synthetic-private-canary' and allowed.read_text()=='read-only-reference'
        for label,server in listeners.items():
            with pytest.raises(TimeoutError):
                if label.startswith('tcp'):connection,_=server.accept();connection.close()
                else:server.recv(100)
    finally:
        if retained is not None:os.close(retained)
        os.close(source_fd)
        for server in listeners.values():server.close()


@pytest.mark.parametrize('mode',['timeout','cancel','memory','cpu','output','exit'])
def test_isolated_failure_stops_and_recovers(tmp_path,mode):
    from tests.test_execution import assert_stopped
    policy=replace(ex.Policy(),memory_bytes=256*ex.MIB,cpu_seconds=1 if mode=='cpu' else 5,output_bytes=65536)
    code={'timeout':'import time;time.sleep(20)','cancel':'import time;time.sleep(20)',
          'memory':'x=bytearray(512*1024**2)','cpu':'while True:pass',
          'output':"from pathlib import Path;import time;Path('large').write_bytes(b'x'*1048576);time.sleep(20)",
          'exit':'raise SystemExit(7)'}[mode]
    started=time.monotonic()
    with pytest.raises(ex.ExecutionError) as error:
        run_probe(tmp_path,code,policy=policy,timeout=.8 if mode=='timeout' else 8,
                  cancel=(lambda:time.monotonic()-started>1) if mode=='cancel' else None)
    receipt=error.value.receipt
    assert receipt['calls_executed']==1 and receipt['filesystem_network_sandbox'] is True
    assert_stopped(receipt['engine_pid']);assert_stopped(receipt['supervisor_pid'])
    if mode=='cpu':assert 'timeout' not in str(error.value).lower()
    if mode=='memory':assert 'MemoryError' in (tmp_path/'logs/stderr.log').read_text()
    recovery=tmp_path/'recovery';recovery.mkdir()
    assert run_probe(recovery,'print("recovered")')['exit_code']==0


def test_invalid_grant_fails_before_exec_without_fallback(tmp_path):
    with pytest.raises(ex.ExecutionError) as error:
        run_probe(tmp_path,'print("must-not-execute")',read_paths=[tmp_path/'missing-input'])
    assert error.value.receipt['calls_executed']==0
    assert (tmp_path/'logs/stdout.log').read_bytes()==b''


def test_missing_isolation_handshake_is_rejected(tmp_path,monkeypatch):
    original=ex._receipt
    monkeypatch.setattr(ex,'_receipt',lambda *args:{**original(*args),'isolation':{}})
    with pytest.raises(ex.ExecutionError,match='receipt'):run_probe(tmp_path,'print(1)')
