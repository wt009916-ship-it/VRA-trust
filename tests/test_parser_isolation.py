"""Real parser entry-point boundaries, with synthetic canaries and loopback only."""
import hashlib
import json
import socket
import sys

import pytest

from backend import core, execution, parser_runtime as runtime, parser_runtime_cache as cache
from test_drawings import pdf_bytes
from tests.test_execution import assert_stopped


def test_actual_parser_scope_denies_private_files_network_and_runtime_writes(tmp_path,monkeypatch):
    original=tmp_path/'original.pdf';original.write_bytes(pdf_bytes())
    outside=tmp_path/'private';outside.write_text('synthetic-private-value')
    digest=hashlib.sha256(original.read_bytes()).hexdigest()
    monkeypatch.setenv('VRA_CANARY_SECRET','synthetic-not-a-real-key')
    servers={}
    try:
        for label,family,kind,host in [('tcp4',socket.AF_INET,socket.SOCK_STREAM,'127.0.0.1'),
             ('udp4',socket.AF_INET,socket.SOCK_DGRAM,'127.0.0.1'),('tcp6',socket.AF_INET6,socket.SOCK_STREAM,'::1'),
             ('udp6',socket.AF_INET6,socket.SOCK_DGRAM,'::1')]:
            server=socket.socket(family,kind);servers[label]=server;server.bind((host,0));server.settimeout(.15)
            if kind==socket.SOCK_STREAM:server.listen(2)
            with socket.socket(family,kind) as positive:
                positive.settimeout(1)
                if kind==socket.SOCK_STREAM:
                    positive.connect(server.getsockname());connection,_=server.accept();connection.close()
                else:positive.sendto(b'positive',server.getsockname());assert server.recv(20)==b'positive'
        native=execution.supervise
        with runtime._workspace() as foreign:
            other=foreign['work']/'other-task';other.write_text('other-private-value')
            def probe(command,control,logs,policy,timeout,**kwargs):
                work=kwargs['output'];staged=work.parent/'input.pdf'
                library=cache._entries['standards']['root']/'code/parser_worker.py'
                args={'original':str(original),'outside':str(outside),'other':str(other),'input':str(staged),
                      'control':str(control/'engine-request.json'),'library':str(library),
                      'ports':{name:s.getsockname()[1] for name,s in servers.items()}}
                code='args='+repr(args)+'\n'+'''
import json,os,socket,subprocess,sys
from pathlib import Path
values={}
def attempt(name,fn):
 try:fn();values[name]='allowed'
 except OSError:values[name]='denied'
for key in ['original','outside','other','control']:
 attempt(key+'_read',lambda key=key:Path(args[key]).read_bytes())
 attempt(key+'_write',lambda key=key:Path(args[key]).write_bytes(b'bad'))
attempt('input_read',lambda:Path(args['input']).read_bytes())
attempt('input_write',lambda:Path(args['input']).write_bytes(b'bad'))
attempt('runtime_read',lambda:Path(args['library']).read_bytes())
attempt('runtime_write',lambda:Path(args['library']).write_bytes(b'bad'))
attempt('output_write',lambda:Path('own').write_text('allowed'))
attempt('spawn',lambda:subprocess.run([sys.executable,'-c','pass'],check=True))
for label,family,kind,host in [('tcp4',socket.AF_INET,socket.SOCK_STREAM,'127.0.0.1'),
 ('udp4',socket.AF_INET,socket.SOCK_DGRAM,'127.0.0.1'),('tcp6',socket.AF_INET6,socket.SOCK_STREAM,'::1'),
 ('udp6',socket.AF_INET6,socket.SOCK_DGRAM,'::1')]:
 def send():
  with socket.socket(family,kind) as s:
   s.settimeout(.3)
   if kind==socket.SOCK_STREAM:s.connect((host,args['ports'][label]))
   else:s.sendto(b'denied-probe',(host,args['ports'][label]))
 attempt(label,send)
values['secret_present']='VRA_CANARY_SECRET' in os.environ
Path('observations.json').write_text(json.dumps(values))
'''
                return native([command[0],'-I','-B','-S','-c',code],control,logs,policy,timeout,**kwargs)
            monkeypatch.setattr(execution,'supervise',probe)
            with runtime.run('standards',original) as scope:
                work=scope['work'];observed=json.loads((work/'observations.json').read_text())
                expected={k+'_'+op:'denied' for k in ['original','outside','other','control'] for op in ['read','write']}
                expected.update(input_read='allowed',input_write='denied',runtime_read='allowed',runtime_write='denied',
                                output_write='allowed',spawn='denied',tcp4='denied',udp4='denied',tcp6='denied',udp6='denied',secret_present=False)
                assert observed==expected
                receipt=scope['resource_limits']['execution_receipt'];assert receipt['filesystem_network_sandbox'] is True
                assert_stopped(receipt['supervisor_pid']);assert_stopped(receipt['engine_pid'])
            assert not work.parent.exists()
            assert other.read_text()=='other-private-value'
        assert hashlib.sha256(original.read_bytes()).hexdigest()==digest and outside.read_text()=='synthetic-private-value'
        for label,server in servers.items():
            with pytest.raises(TimeoutError):
                if label.startswith('tcp'):connection,_=server.accept();connection.close()
                else:server.recv(100)
    finally:
        for server in servers.values():server.close()


def test_cached_public_runtime_tamper_rejected_before_new_parser(tmp_path):
    source=tmp_path/'input.pdf';source.write_bytes(pdf_bytes())
    with runtime.run('standards',source) as first:identity=first['resource_limits']['runtime_hash']
    entry=cache._entries['standards'];file=entry['root']/'code/parser_worker.py';data=file.read_bytes()
    mode=file.stat().st_mode
    try:
        file.chmod(0o600);file.write_bytes(data+b'\n# synthetic corruption\n')
        with pytest.raises(core.ValidationError,match='cache identity mismatch'):
            with runtime.run('standards',source):pytest.fail('Tampered runtime executed')
    finally:file.write_bytes(data);file.chmod(mode)
    with runtime.run('standards',source) as recovered:
        assert recovered['resource_limits']['runtime_hash']==identity
        assert recovered['resource_limits']['runtime_cache_hit'] is True
    assert not (entry['root']/'input.pdf').exists()


def test_shared_staging_capacity_is_released_after_failure(tmp_path):
    source=tmp_path/'input.pdf';source.write_bytes(pdf_bytes())
    assert runtime._capacity.acquire(False) and runtime._capacity.acquire(False)
    try:
        with pytest.raises(core.ValidationError,match='busy'):
            with runtime.run('standards',source):pytest.fail('Capacity limit bypassed')
    finally:runtime._capacity.release();runtime._capacity.release()
    with pytest.raises(core.ValidationError,match='input/runtime changed'):
        with runtime.run('standards',tmp_path/'absent.pdf'):pass
    with runtime.run('standards',source) as recovered:assert recovered['resource_limits']['enforced'] is True


@pytest.mark.parametrize('kind,route',[('cad','cad-inspections'),('drawing','drawings'),('standards','standards-preview')])
def test_missing_dependency_is_api_refusal_not_internal_server_error(client,monkeypatch,kind,route):
    from importlib.metadata import PackageNotFoundError
    from test_api import create_project
    from test_cad import upload,dxf_bytes
    from test_drawings import GOLD
    name,data={'cad':('source.dxf',dxf_bytes()),'drawing':('source.png',(GOLD/'clean.png').read_bytes()),
               'standards':('source.pdf',pdf_bytes())}[kind]
    pid=create_project(client)['project_id'];fid=upload(client,pid,name,data)
    def unavailable(name):raise PackageNotFoundError('synthetic-missing-dependency')
    monkeypatch.setattr(runtime,'distribution',unavailable)
    result=client.post(f'/api/projects/{pid}/{route}',json={'file_id':fid})
    assert result.status_code==409
    assert client.app.state.domain.file_record(pid,fid)[1].read_bytes()==data


@pytest.mark.skipif(sys.platform!='linux',reason='Linux symlink negative control')
def test_runtime_dependency_link_rejected(tmp_path,monkeypatch):
    real=tmp_path/'real.py';real.write_text('public')
    (tmp_path/'alias.py').symlink_to(real)
    class Distribution:
        files=['alias.py']
        def locate_file(self,name):return tmp_path/name
    monkeypatch.setattr(runtime,'dependencies',lambda _: {'synthetic':Distribution()})
    with pytest.raises(ValueError,match='Linked'):runtime.plan('standards')
