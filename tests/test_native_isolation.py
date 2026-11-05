"""OS boundary probes use synthetic files and loopback positive controls only."""
import json
import os
from pathlib import Path
import shutil
import socket
import sys
import time
from dataclasses import replace

import pytest

from backend import execution as ex
from backend.native_environment import environment


def test_native_environment_drops_secrets_and_loader_overrides(tmp_path,monkeypatch):
    for name in ['OPENAI_API_KEY','VRA_CANARY_SECRET','PYTHONPATH','PYTHONHOME','LD_PRELOAD','PATH','HTTP_PROXY','AWS_SECRET_ACCESS_KEY']:
        monkeypatch.setenv(name,'synthetic-test-only')
    env=environment(tmp_path)
    assert 'synthetic-test-only' not in env.values()
    assert env['TEMP']==str(tmp_path.resolve()) and env['OMP_NUM_THREADS']=='2'


WINDOWS=pytest.mark.skipif(sys.platform!='win32',reason='Windows LPAC kernel boundary')


def stage_python(scope):
    """Only the test's disposable, public stdlib copy gets inherited LPAC read ACL."""
    base=Path(sys.base_prefix);runtime=scope['root']/'python';runtime.mkdir()
    for path in base.iterdir():
        if path.is_file() and path.suffix in {'.exe','.dll','.txt'}:shutil.copy2(path,runtime/path.name)
    for name in ['Lib','DLLs']:
        shutil.copytree(base/name,runtime/name,ignore=shutil.ignore_patterns('site-packages','__pycache__','test','idlelib','tkinter','turtledemo'))
    return runtime/'python.exe'


def run(scope,python,code,tmp_path,**kwargs):
    control=tmp_path/'control';control.mkdir();logs=tmp_path/'logs';logs.mkdir()
    return ex.supervise([python,'-I','-B','-c',code],control,logs,
        kwargs.pop('policy',replace(ex.Policy(),memory_bytes=512*ex.MIB,cpu_seconds=8)),kwargs.pop('timeout',8),
        output=scope['work'],isolation={'sid':scope['sid'],'work':str(scope['work'])},extra_output_roots=[scope['profile_root']],**kwargs)


@WINDOWS
def test_lpac_files_network_environment_and_process_boundary(tmp_path,monkeypatch):
    from backend.native_windows import staging
    from tests.test_execution import assert_stopped
    outside=tmp_path/'private.txt';outside.write_text('synthetic-canary')
    monkeypatch.setenv('VRA_CANARY_SECRET','synthetic-canary')
    listeners={}
    try:
        for label,family,kind,address in [('tcp4',socket.AF_INET,socket.SOCK_STREAM,'127.0.0.1'),
             ('udp4',socket.AF_INET,socket.SOCK_DGRAM,'127.0.0.1'),('tcp6',socket.AF_INET6,socket.SOCK_STREAM,'::1'),
             ('udp6',socket.AF_INET6,socket.SOCK_DGRAM,'::1')]:
            server=socket.socket(family,kind);listeners[label]=server
            server.bind((address,0));server.settimeout(.2)
            if kind==socket.SOCK_STREAM:server.listen(2)
            with socket.socket(family,kind) as control:
                control.settimeout(1)
                if kind==socket.SOCK_STREAM:
                    control.connect(server.getsockname());client,_=server.accept();client.close()
                else:
                    control.sendto(b'positive-control',server.getsockname());assert server.recv(100)==b'positive-control'
        with staging() as scope,staging() as other:
            python=stage_python(scope)
            allowed=scope['root']/'input.txt';allowed.write_text('original-public-input')
            other_file=other['work']/'other.txt';other_file.write_text('different-job')
            args={'outside':str(outside),'allowed':str(allowed),'runtime':str(python),
                  'other':str(other_file),'control':str(tmp_path/'control/engine-request.json'),
                  'ports':{label:server.getsockname()[1] for label,server in listeners.items()}}
            code='args='+repr(args)+'\n'+'''
import json,os,socket,subprocess,sys
from pathlib import Path
r={}
for name,path,mode in [('outside_read',args['outside'],'r'),('outside_write',args['outside'],'w'),
 ('other_job',args['other'],'r'),('input_read',args['allowed'],'r'),('input_write',args['allowed'],'w'),
 ('runtime_write',args['runtime'],'a'),('control_read',args['control'],'r'),('control_write',args['control'],'w'),
 ('output_write','allowed-output.txt','w')]:
    try:
        with open(path,mode) as f:
            if mode=='r':f.read()
            else:f.write('child')
        r[name]='allowed'
    except OSError as exc:r[name]=exc.errno
for label,family,kind,host in [('tcp4',socket.AF_INET,socket.SOCK_STREAM,'127.0.0.1'),
 ('udp4',socket.AF_INET,socket.SOCK_DGRAM,'127.0.0.1'),('tcp6',socket.AF_INET6,socket.SOCK_STREAM,'::1'),
 ('udp6',socket.AF_INET6,socket.SOCK_DGRAM,'::1')]:
    try:
        with socket.socket(family,kind) as client:
            client.settimeout(.5)
            if kind==socket.SOCK_STREAM:client.connect((host,args['ports'][label]))
            else:client.sendto(b'isolated-probe',(host,args['ports'][label]))
        r[label]='allowed'
    except OSError as exc:r[label]=exc.errno
try:
    child=subprocess.Popen([sys.executable,'-c','pass']);child.wait();r['spawn']='allowed'
except OSError:r['spawn']='denied'
r['secret_present']='VRA_CANARY_SECRET' in os.environ
Path('observations.json').write_text(json.dumps(r))
'''
            receipt=run(scope,python,code,tmp_path)
            observed=json.loads((scope['work']/'observations.json').read_text())
            assert observed=={'outside_read':13,'outside_write':13,'other_job':13,'input_read':'allowed',
                'input_write':13,'runtime_write':13,'control_read':13,'control_write':13,
                'output_write':'allowed','tcp4':13,'udp4':13,'tcp6':13,'udp6':13,
                'spawn':'denied','secret_present':False}
            assert receipt['filesystem_network_sandbox'] is True
            assert receipt['isolation']['capabilities']==['registryRead']
            assert_stopped(receipt['engine_pid']);assert_stopped(receipt['supervisor_pid'])
            assert allowed.read_text()=='original-public-input' and other_file.read_text()=='different-job'
            root=scope['root'];profile_root=scope['profile_root']
        assert not root.exists() and not profile_root.exists() and outside.read_text()=='synthetic-canary'
        for label,server in listeners.items():
            with pytest.raises(TimeoutError):
                if label.startswith('tcp'):
                    client,_=server.accept();client.close()
                else:server.recv(100)
    finally:
        for server in listeners.values():server.close()


@WINDOWS
@pytest.mark.parametrize('mode',['cancel','timeout','exit'])
def test_lpac_failure_cleanup_and_recovery(tmp_path,mode):
    from backend.native_windows import staging
    from tests.test_execution import assert_stopped
    with staging() as scope:
        python=stage_python(scope);started=time.monotonic()
        with pytest.raises(ex.ExecutionError) as failure:
            run(scope,python,'raise SystemExit(7)' if mode=='exit' else 'import time;time.sleep(20)',tmp_path,
                timeout=1 if mode=='timeout' else 8,
                cancel_check=(lambda:time.monotonic()-started>1) if mode=='cancel' else None)
        receipt=failure.value.receipt
        assert receipt['calls_executed']==1
        assert_stopped(receipt['engine_pid']);assert_stopped(receipt['supervisor_pid'])
        root=scope['root'];profile_root=scope['profile_root']
    assert not root.exists() and not profile_root.exists()
    recovery=tmp_path/'recovery';recovery.mkdir()
    with staging() as scope:
        python=stage_python(scope)
        assert run(scope,python,'print("recovered")',recovery)['exit_code']==0


@WINDOWS
def test_missing_lpac_receipt_never_passes(tmp_path,monkeypatch):
    from backend.native_windows import staging
    original=ex._receipt
    monkeypatch.setattr(ex,'_receipt',lambda *args:{**original(*args),'isolation':{}})
    with staging() as scope:
        python=stage_python(scope)
        with pytest.raises(ex.ExecutionError,match='receipt'):
            run(scope,python,'print(1)',tmp_path)


@WINDOWS
def test_staging_copies_hardlink_bytes_and_rejects_oversize(tmp_path):
    from backend.native_windows import staging,copy_file
    source=tmp_path/'source';source.write_bytes(b'original')
    linked=tmp_path/'hardlink';os.link(source,linked)
    with staging() as scope:
        target=scope['root']/'copy';copy_file(linked,target,8)
        assert not os.path.samefile(source,target)
        target.write_bytes(b'changed-by-parent')
        assert source.read_bytes()==b'original'
        with pytest.raises(ValueError,match='oversized'):copy_file(source,scope['root']/'too-big',7)


@WINDOWS
def test_profile_storage_is_included_in_output_budget(tmp_path):
    from backend.native_windows import staging
    with staging() as scope:
        python=stage_python(scope)
        target=scope['profile_root']/'AC/Temp/profile-overflow'
        code='from pathlib import Path; import time; Path('+repr(str(target))+').write_bytes(b"x"*1048576); time.sleep(20)'
        with pytest.raises(ex.ExecutionError,match='budget') as failure:
            run(scope,python,code,tmp_path,policy=replace(ex.Policy(),output_bytes=65536,memory_bytes=512*ex.MIB,cpu_seconds=8))
        assert failure.value.receipt['calls_executed']==1
        assert target.stat().st_size==1048576 and list(scope['work'].iterdir())==[]
        profile_root=scope['profile_root']
    assert not profile_root.exists()


@WINDOWS
def test_lpac_access_controls_reject_unrestricted_token():
    import ctypes as c
    from ctypes import wintypes as w
    from backend.native_windows import api,verify_lpac_access,checked
    from backend.private_storage import _sid,_windows
    apis=api();k,a,_,_=apis;token=w.HANDLE()
    checked(a.OpenProcessToken(k.GetCurrentProcess(),8|2,c.byref(token)))
    try:
        with pytest.raises(RuntimeError,match='controls failed'):verify_lpac_access(token,_sid(_windows()),apis)
    finally:k.CloseHandle(token)


def test_failed_isolation_is_not_retried_without_boundary(tmp_path,monkeypatch):
    from backend import core
    from contextlib import contextmanager
    @contextmanager
    def broken(*args,**kwargs):
        raise OSError('synthetic sandbox unavailable')
        yield  # pragma: no cover
    calls=[]
    monkeypatch.setattr(core,'native_workspace',broken)
    monkeypatch.setattr(core,'engine_path',lambda:Path(__file__))
    monkeypatch.setattr(ex,'supervise',lambda *a,**k:calls.append(a))
    result=core.run_simulation('reference_5zone','baseline','none',tmp_path/'run')
    assert result['status']=='failed' and result['metrics'] is None and calls==[]
    assert 'sandbox unavailable' in result['error']['message']
