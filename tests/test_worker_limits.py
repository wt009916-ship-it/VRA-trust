"""Exercise actual OS limits in child processes; the pytest process is never capped."""
import json
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path

import pytest
from backend import worker_limits
from test_api import create_project
from test_cad import upload,dxf_bytes
from test_drawings import GOLD,pdf_bytes

PROBE=Path(__file__).with_name('worker_limit_probe.py')


def probe(mode,*args,timeout=10):
    return subprocess.run([sys.executable,str(PROBE),mode,*map(str,args)],capture_output=True,text=True,
                          timeout=timeout,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))


def test_actual_kernel_limits_and_native_memory_denial():
    cp=probe('memory');assert cp.returncode==0,(cp.stdout,cp.stderr)
    rows=[json.loads(line) for line in cp.stdout.splitlines()]
    assert rows[0]['installed']['memory_bytes']==128*1024**2
    assert rows[1]['allocation_denied'] is True


def test_actual_cpu_budget_terminates_worker_without_parent_timeout():
    start=time.monotonic();cp=probe('cpu')
    assert cp.returncode!=0 and 'installed' in cp.stdout,(cp.stdout,cp.stderr)
    assert time.monotonic()-start<10
    # A clean next worker proves no parent-wide resource limit was installed.
    assert probe('normal').returncode==0


@pytest.mark.skipif(sys.platform!='win32',reason='Windows Job Object active-process limit; Linux explicitly not claimed')
def test_windows_job_denies_child_process_execution():
    cp=probe('child');assert cp.returncode==0,(cp.stdout,cp.stderr)
    assert 'child_denied' in cp.stdout


@pytest.mark.skipif(sys.platform!='win32',reason='Windows-only documented mapped-memory gap')
def test_windows_mapping_gap_is_explicit_not_claimed_as_full_memory_isolation():
    cp=probe('mapping_gap');assert cp.returncode==0,(cp.stdout,cp.stderr)
    rows=[json.loads(line) for line in cp.stdout.splitlines()]
    assert rows[0]['installed']['mapped_memory_bounded'] is False
    assert rows[1]['mapping_denied'] is False and rows[1]['known_gap'] is True


@pytest.mark.skipif(sys.platform!='linux',reason='Linux RLIMIT_FSIZE; Windows explicitly not claimed')
def test_linux_single_file_budget(tmp_path):
    path=tmp_path/'bounded.bin';cp=probe('file',path)
    assert cp.returncode==0,(cp.stdout,cp.stderr)
    assert 'file_growth_denied' in cp.stdout and path.stat().st_size<=64*1024**2


def test_install_failure_stops_before_parser(tmp_path):
    cp=probe('startup_failure',tmp_path/'receipt.json')
    assert cp.returncode==70 and not list(tmp_path.iterdir())


@pytest.mark.parametrize('memory,cpu',[(True,1),(1024,1),(5*1024**3,1),(128*1024**2,0),(128*1024**2,61),(128*1024**2,True)])
def test_bad_budget_cannot_change_parent_resources(memory,cpu):
    with pytest.raises(ValueError):worker_limits.apply_limits(memory,cpu)


def test_unknown_platform_fails_closed(monkeypatch):
    monkeypatch.setattr(sys,'platform','unsupported')
    with pytest.raises(RuntimeError,match='unsupported'):worker_limits.apply_limits(128*1024**2,1)


def test_receipt_missing_or_invalid_never_attests_limits(tmp_path):
    out=tmp_path/'result.json'
    with pytest.raises(ValueError,match='Missing'):worker_limits.receipt(out,'cad')
    for value in ({},{'kind':'cad','enforced':False},{'kind':'cad','enforced':True,'mechanism':'linux_rlimit','memory_bytes':True,'cpu_seconds':1}):
        out.with_suffix('.limits.json').write_text(json.dumps(value))
        with pytest.raises(ValueError,match='Invalid'):worker_limits.receipt(out,'cad')


@pytest.mark.parametrize('kind,filename,data,route,record_kind',[
    ('cad','source.dxf',dxf_bytes(),'cad-inspections','cad'),
    ('drawing','source.png',(GOLD/'clean.png').read_bytes(),'drawings','drawing'),
    ('standards','source.pdf',pdf_bytes(),'standards-preview','standard')],ids=['cad','drawing','standards'])
def test_success_output_without_limit_receipt_rejected_original_retained(client,monkeypatch,kind,filename,data,route,record_kind):
    pid=create_project(client)['project_id'];fid=upload(client,pid,filename,data)
    # Execute the real isolated parser, then remove the trusted receipt. A real
    # successful result is insufficient evidence of enforced resource policy.
    monkeypatch.setattr('backend.execution._receipt',lambda *args:{})
    for _ in range(2):
        r=client.post(f'/api/projects/{pid}/{route}',json={'file_id':fid})
        assert r.status_code==409 and 'resource enforcement' in r.text,r.text
    assert client.app.state.domain.store.list(record_kind,pid)==[]
    assert client.app.state.domain.file_record(pid,fid)[1].read_bytes()==data


@pytest.mark.parametrize('filename,data,route,record_kind',[
    ('source.dxf',dxf_bytes(),'cad-inspections','cad'),
    ('source.png',(GOLD/'clean.png').read_bytes(),'drawings','drawing'),
    ('source.pdf',pdf_bytes(),'standards-preview','standard')],ids=['cad','drawing','standards'])
def test_actual_cpu_kill_releases_api_capacity_without_success_record(client,monkeypatch,filename,data,route,record_kind):
    pid=create_project(client)['project_id'];fid=upload(client,pid,filename,data)
    from backend import execution
    original_run=execution.supervise
    def killed_worker(command,work,logs,policy,timeout,**kwargs):
        # Run a real capped CPU process instead of the parser for this isolated
        # request; no fabricated successful process or result is returned.
        return original_run([command[0],'-I','-B','-c','while True:pass'],work,logs,
                            replace(policy,cpu_seconds=1),timeout,**kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(execution,'supervise',killed_worker)
        r=client.post(f'/api/projects/{pid}/{route}',json={'file_id':fid})
    assert r.status_code==409,r.text
    assert client.app.state.domain.store.list(record_kind,pid)==[]
    assert client.app.state.domain.file_record(pid,fid)[1].read_bytes()==data
    r=client.post(f'/api/projects/{pid}/{route}',json={'file_id':fid})
    assert r.status_code in (200,201),r.text
    result=r.json().get('result',r.json())
    assert result['resource_limits']['enforced'] is True
