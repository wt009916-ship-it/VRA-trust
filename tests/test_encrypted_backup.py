"""Authenticated encryption interoperability and native private-file protection."""
import hashlib
import json
import os
import secrets
import subprocess
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi.testclient import TestClient

from backend import backup, core, encrypted_backup as secure, private_storage
from backend.api import create_app
from test_backup import cold as shared_cold

cold = shared_cold  # Register the same isolated fixture in this test module.


class Secret(bytes):
    def __repr__(self):return '<isolated encryption passphrase redacted>'


@pytest.fixture
def password():return Secret(secrets.token_urlsafe(32).encode())


def test_streaming_envelope_independent_one_shot_and_hashlib_scrypt(tmp_path,password):
    data=b'independent encryption boundary\x00'+os.urandom(2*secure.CHUNK+17)
    source=tmp_path/'plain';source.write_bytes(data)
    archive=tmp_path/'encrypted.vraenc';meta=secure.encrypt_file(source,archive,password)
    raw=archive.read_bytes();header=raw[:secure.HEADER.size]
    magic,salt,nonce,length=secure.HEADER.unpack(header)
    assert magic==secure.MAGIC and length==len(data)
    # Independent one-shot framing check and CPython/OpenSSL key derivation API.
    key=hashlib.scrypt(password,salt=salt,n=131072,r=8,p=1,maxmem=256*1024**2,dklen=32)
    assert AESGCM(key).decrypt(nonce,raw[secure.HEADER.size:],header)==data
    second=tmp_path/'second.vraenc';secure.encrypt_file(source,second,password)
    assert second.read_bytes()!=raw and data[:30] not in raw
    assert meta['storage_protection']['verified']
    with secure.decrypted_archive(archive,password,meta['archive_sha256'],tmp_path) as (plain,digest):
        assert plain.read_bytes()==data and digest==core.sha(source)
        assert private_storage.verify_private(plain)['verified']
    assert not list(tmp_path.glob('vra-private-*'))


def test_independently_created_authenticated_envelope_is_readable(tmp_path,password):
    data=b'independently framed test input';salt=os.urandom(16);nonce=os.urandom(12)
    header=secure.HEADER.pack(secure.MAGIC,salt,nonce,len(data))
    key=hashlib.scrypt(password,salt=salt,n=131072,r=8,p=1,maxmem=256*1024**2,dklen=32)
    archive=tmp_path/'independent.vraenc';archive.write_bytes(header+AESGCM(key).encrypt(nonce,data,header))
    with secure.decrypted_archive(archive,password,core.sha(archive),tmp_path) as (plain,_):assert plain.read_bytes()==data


def test_encrypted_application_backup_restores_login_original_and_private_root(cold,tmp_path,password):
    root,pid,fid,token=cold
    archive=tmp_path/'backup.vraenc';result=secure.create_encrypted(root,archive,password)
    assert result['encrypted'] and secure.verify_encrypted(archive,password,result['archive_sha256'])['authenticated']
    assert b'original.csv' not in archive.read_bytes() and b'password_hash' not in archive.read_bytes()
    receipt=secure.restore_encrypted(archive,tmp_path/'restored',password,result['archive_sha256'])
    assert receipt['encrypted_archive_sha256']==result['archive_sha256'] and receipt['storage_protection']['verified']
    stored=json.loads(next((tmp_path/'restored/recovery').glob('*.json')).read_text(encoding='utf-8'))
    assert stored==receipt
    with TestClient(create_app(tmp_path/'restored',start_worker=False)) as client:
        client.cookies.set('vra_session',token)
        assert client.get('/api/projects').status_code==401
        assert client.post('/api/auth/login',json={'username':'backup_owner','password':'Backup-test-password-2026'}).status_code==200
        assert client.app.state.domain.file_record(pid,fid)[1].read_bytes()==b'unit,value\nkWh,123.45\n'
    assert not list(tmp_path.glob('vra-private-*'))


@pytest.mark.parametrize('mutation',['password','salt','nonce','ciphertext','tag','length','version','truncate','append','hash'])
def test_wrong_key_and_tampering_never_parse_or_create_destination(cold,tmp_path,password,monkeypatch,mutation):
    archive=tmp_path/'backup.vraenc';meta=secure.create_encrypted(cold[0],archive,password)
    raw=bytearray(archive.read_bytes());key=password
    if mutation=='password':key=Secret(b'wrong-independent-passphrase-2026')
    elif mutation=='truncate':raw=raw[:-1]
    elif mutation=='append':raw+=b'!'
    elif mutation not in {'hash'}:
        index={'salt':8,'nonce':24,'ciphertext':secure.HEADER.size+11,'tag':len(raw)-1,'length':secure.HEADER.size-1,'version':0}[mutation]
        raw[index]^=1
    archive.write_bytes(raw)
    digest='0'*64 if mutation=='hash' else core.sha(archive)
    monkeypatch.setattr(backup,'restore_backup',lambda *a,**k:pytest.fail('Unauthenticated data reached ZIP/SQLite restore'))
    with pytest.raises(ValueError):secure.restore_encrypted(archive,tmp_path/'restored',key,digest)
    assert not (tmp_path/'restored').exists() and not list(tmp_path.glob('vra-private-*'))
    assert meta['encrypted']


@pytest.mark.parametrize('password',[b'',b'short',b'x'*1025,b'x'*16+b'\n',b'x'*16+b'\x00','not bytes',None])
def test_invalid_password_rejected_before_output(tmp_path,password):
    source=tmp_path/'data';source.write_bytes(b'payload')
    with pytest.raises(ValueError):secure.encrypt_file(source,tmp_path/'archive',password)
    assert not (tmp_path/'archive').exists()


def test_plaintext_never_silently_accepted_and_existing_targets_retained(cold,tmp_path,password):
    legacy=tmp_path/'legacy.zip';meta=backup.create_backup(cold[0],legacy)
    with pytest.raises(ValueError):secure.verify_encrypted(legacy,password,meta['archive_sha256'])
    encrypted=tmp_path/'encrypted';value=secure.create_encrypted(cold[0],encrypted,password)
    before=encrypted.read_bytes()
    with pytest.raises(ValueError):secure.create_encrypted(cold[0],encrypted,password)
    with pytest.raises(ValueError):secure.restore_encrypted(encrypted,cold[0],password,value['archive_sha256'])
    assert encrypted.read_bytes()==before


def test_permission_failure_before_plaintext_and_cleanup(cold,tmp_path,password,monkeypatch):
    def fail(*args,**kwargs):raise ValueError('deliberate permission verification failure')
    monkeypatch.setattr(private_storage,'verify_private',fail)
    with pytest.raises(ValueError,match='permission'):secure.create_encrypted(cold[0],tmp_path/'archive',password)
    assert not (tmp_path/'archive').exists()
    assert not [p for folder in tmp_path.glob('vra-private-*') for p in folder.rglob('*') if p.is_file()]


def test_cli_defaults_encrypted_and_password_never_in_output_or_argv(cold,tmp_path,password):
    script=Path(__file__).resolve().parents[1]/'scripts/backup_runtime.py'
    archive=tmp_path/'cli.vraenc'
    args=[sys.executable,str(script),'create','--source',str(cold[0]),'--archive',str(archive),'--password-stdin']
    cp=subprocess.run(args,input=password+b'\n',capture_output=True,timeout=30)
    assert cp.returncode==0,cp.stderr.decode(errors='replace')
    assert password not in cp.stdout+cp.stderr and password.decode() not in ' '.join(args)
    result=json.loads(cp.stdout);assert result['encrypted']
    args=[sys.executable,str(script),'verify','--archive',str(archive),'--sha256',result['archive_sha256'],'--password-stdin']
    cp=subprocess.run(args,input=b'an incorrect backup password\n',capture_output=True,timeout=30)
    assert cp.returncode==1 and b'an incorrect backup password' not in cp.stdout+cp.stderr
    assert json.loads(cp.stdout)['status']=='rejected'
    cp=subprocess.run(args,input=password+b'\n',capture_output=True,timeout=30)
    assert cp.returncode==0 and json.loads(cp.stdout)['authenticated']
    args=[sys.executable,str(script),'restore','--archive',str(archive),'--sha256',result['archive_sha256'],'--target',str(tmp_path/'cli-restored'),'--password-stdin']
    cp=subprocess.run(args,input=password+b'\n',capture_output=True,timeout=30)
    assert cp.returncode==0 and json.loads(cp.stdout)['encrypted']
    assert password not in cp.stdout+cp.stderr


@pytest.mark.skipif(sys.platform!='win32',reason='Native Windows restricted-token ACL probe')
def test_windows_kernel_denies_restricted_reader_with_readable_control(tmp_path):
    import ctypes as c
    directory=private_storage.private_mkdir(tmp_path/'protected')
    private=directory/'private.bin'
    with private_storage.private_open(private) as stream:stream.write(b'private probe')
    # Non-sensitive control file deliberately permits Everyone READ only, to prove
    # the restricted process can read an allowed file and is not simply broken.
    api=private_storage._windows();_,_,adv,kernel=api
    sid=private_storage._sid(api);descriptor=c.c_void_p()
    sddl=f'O:{sid}D:P(A;;FA;;;{sid})(A;;FR;;;WD)'
    assert adv.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl,1,c.byref(descriptor),None)
    from ctypes import wintypes as w
    class Attr(c.Structure):_fields_=[('length',w.DWORD),('descriptor',c.c_void_p),('inherit',w.BOOL)]
    attr=Attr(c.sizeof(Attr),descriptor,False);control=directory/'control.bin'
    try:
        handle=kernel.CreateFileW(private_storage._win_path(control),0xC0000000,1,c.byref(attr),1,0x80,None)
        assert handle!=c.c_void_p(-1).value
        import msvcrt
        with os.fdopen(msvcrt.open_osfhandle(handle,os.O_RDWR|os.O_BINARY),'wb') as stream:stream.write(b'public probe')
    finally:kernel.LocalFree(descriptor)
    probe=Path(__file__).with_name('backup_access_probe.py')
    cp=subprocess.run([sys.executable,str(probe),str(private),str(control)],capture_output=True,text=True,timeout=15,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    assert cp.returncode==0,(cp.stdout,cp.stderr)
    result=json.loads(cp.stdout);assert result['control_read_allowed'] and result['private_read_denied']


@pytest.mark.skipif(sys.platform!='linux',reason='POSIX owner/mode enforcement')
def test_linux_permissions_and_broad_mode_rejected(tmp_path):
    directory=private_storage.private_mkdir(tmp_path/'private')
    path=directory/'data'
    with private_storage.private_open(path) as stream:stream.write(b'private probe')
    assert private_storage.verify_private(directory,True)['mode']=='0o700'
    assert private_storage.verify_private(path)['mode']=='0o600'
    path.chmod(0o644)
    with pytest.raises(ValueError):private_storage.verify_private(path)


@pytest.mark.parametrize('failure',['confirmation','echo_fallback'])
def test_cli_interactive_password_failure_has_no_fallback_or_secret_output(tmp_path,monkeypatch,capsys,failure):
    from scripts import backup_runtime as cli
    values=iter([secrets.token_urlsafe(32),secrets.token_urlsafe(32)])
    def prompt(*args):
        if failure=='echo_fallback':raise cli.getpass.GetPassWarning('No protected terminal')
        return next(values)
    monkeypatch.setattr(cli.getpass,'getpass',prompt)
    monkeypatch.setattr(sys,'argv',['backup_runtime.py','create','--source',str(tmp_path/'source'),'--archive',str(tmp_path/'new.vraenc')])
    assert cli.main()==1
    result=json.loads(capsys.readouterr().out)
    assert result['status']=='rejected' and not (tmp_path/'new.vraenc').exists()


@pytest.mark.skipif(sys.platform!='linux',reason='Linux fchmod failure descriptor cleanup')
def test_linux_permission_setup_failure_closes_descriptor(tmp_path,monkeypatch):
    descriptors=[]
    def fail(fd,mode):
        descriptors.append(fd)
        raise OSError('Deliberate isolated fchmod failure')
    monkeypatch.setattr(os,'fchmod',fail)
    with pytest.raises(OSError):private_storage.private_open(tmp_path/'empty')
    assert len(descriptors)==1
    with pytest.raises(OSError):os.fstat(descriptors[0])
    assert (tmp_path/'empty').stat().st_size==0
