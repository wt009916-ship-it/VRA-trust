"""Integrity must survive bounded concurrent reads, including late-batch errors."""
import os
from types import SimpleNamespace
import threading

import pytest

from backend import core, parser_runtime_cache as cache


def fixture_files(root):
    paths=[];identities={}
    for index in range(256):
        path=root/f'{index:04}.bin';path.write_bytes(bytes([index])*257)
        paths.append(path);identities[path.name]={'sha256':core.sha(path)}
    return paths,identities


@pytest.mark.parametrize('platform',['win32','linux'])
def test_verifier_reads_every_file_and_bounds_parallelism(tmp_path,monkeypatch,platform):
    paths,identities=fixture_files(tmp_path)
    monkeypatch.setattr(cache,'sys',SimpleNamespace(platform=platform))
    original=core.sha;seen=[];active=maximum=0;lock=threading.Lock()
    rendezvous=threading.Barrier(8) if platform=='win32' else None
    local=threading.local()
    def observed(path):
        nonlocal active,maximum
        with lock:active+=1;maximum=max(maximum,active)
        try:
            if rendezvous and not getattr(local,'entered',False):
                local.entered=True;rendezvous.wait(timeout=10)
            value=original(path)
            with lock:seen.append(path)
            return value
        finally:
            with lock:active-=1
    monkeypatch.setattr(core,'sha',observed)
    receipt=cache._verify_hashes(tmp_path,paths,identities)
    assert set(seen)==set(paths) and len(seen)==256 and active==0
    assert maximum==(8 if platform=='win32' else 1)
    assert receipt['workers']==maximum and receipt['files']==256
    assert not any(t.name.startswith('vra-runtime-verify') for t in threading.enumerate())


@pytest.mark.parametrize('index',[0,127,128,255])
def test_same_size_same_timestamp_corruption_in_any_batch_is_rejected(tmp_path,monkeypatch,index):
    paths,identities=fixture_files(tmp_path)
    monkeypatch.setattr(cache,'sys',SimpleNamespace(platform='win32'))
    target=paths[index];before=target.read_bytes();stamp=target.stat()
    target.write_bytes(bytes([index^255])*len(before))
    os.utime(target,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
    assert target.stat().st_size==stamp.st_size and target.stat().st_mtime_ns==stamp.st_mtime_ns
    with pytest.raises(core.ValidationError,match='identity mismatch'):
        cache._verify_hashes(tmp_path,paths,identities)
    assert not any(t.name.startswith('vra-runtime-verify') for t in threading.enumerate())
    target.write_bytes(before)
    assert cache._verify_hashes(tmp_path,paths,identities)['files']==256


def test_reader_error_joins_all_workers_and_recovers(tmp_path,monkeypatch):
    paths,identities=fixture_files(tmp_path)
    monkeypatch.setattr(cache,'sys',SimpleNamespace(platform='win32'))
    original=core.sha
    def unreadable(path):
        if path==paths[-1]:raise OSError('Synthetic read failure')
        return original(path)
    monkeypatch.setattr(core,'sha',unreadable)
    with pytest.raises(OSError,match='Synthetic read failure'):
        cache._verify_hashes(tmp_path,paths,identities)
    assert not any(t.name.startswith('vra-runtime-verify') for t in threading.enumerate())
    monkeypatch.setattr(core,'sha',original)
    assert cache._verify_hashes(tmp_path,paths,identities)['files']==256
