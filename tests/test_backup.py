"""Real local archives, process exclusion, corrupt input and API recovery."""
import json
import os
import sqlite3
import subprocess
import sys
import threading
import zipfile
from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import backup, core
from backend.api import create_app
from backend.runtime_lock import RuntimeLease, runtime_operation
from backend.store import Store
from test_api import create_project
from test_cad import upload, dxf_bytes
from test_drawings import GOLD


class PrivateToken(str):
    def __repr__(self):
        return '<isolated session redacted>'


@pytest.fixture
def cold(tmp_path):
    root = tmp_path/'source'
    with TestClient(create_app(root, start_worker=False)) as client:
        auth = client.post('/api/auth/register', json={'username':'backup_owner','display_name':'Isolated backup test','password':'Backup-test-password-2026'}).json()
        client.headers['X-CSRF-Token'] = auth['csrf_token']
        pid = create_project(client)['project_id']
        fid = upload(client, pid, 'original.csv', b'unit,value\nkWh,123.45\n')
        token = PrivateToken(client.cookies.get('vra_session'))
    return root, pid, fid, token


def make(cold, tmp_path):
    archive = tmp_path/'backup.zip'
    result = backup.create_backup(cold[0], archive)
    return archive, result['archive_sha256']


def test_restore_preserves_originals_histories_ownership_revokes_sessions_and_private(cold, tmp_path):
    root, pid, fid, token = cold
    store = Store(root)
    original = store.get('project', pid)
    store.put('project', {**original, 'name':'Second revision'}, original['revision'])
    (root/'private').mkdir()
    (root/'private/provider.json').write_text('SECRET_SENTINEL_NOT_A_LIVE_KEY')
    (root/'exports').mkdir()
    (root/'exports/regenerable.zip').write_bytes(b'cache only')
    before = store.history('project', pid)
    archive, digest = make(cold, tmp_path)
    with zipfile.ZipFile(archive) as package:
        assert not any(n.startswith(('private/', 'exports/')) for n in package.namelist())
        assert b'SECRET_SENTINEL' not in archive.read_bytes()
    receipt = backup.restore_backup(archive, tmp_path/'restored', digest)
    assert receipt['revoked_sessions'] == 1 and not receipt['historical_engineering_hashes_rewritten']
    assert store.history('project', pid) == before
    with TestClient(create_app(tmp_path/'restored', start_worker=False)) as client:
        client.cookies.set('vra_session', token)
        assert client.get('/api/projects').status_code == 401
        auth = client.post('/api/auth/login', json={'username':'backup_owner','password':'Backup-test-password-2026'}).json()
        client.headers['X-CSRF-Token'] = auth['csrf_token']
        assert client.app.state.domain.store.history('project', pid) == before
        assert client.app.state.domain.file_record(pid, fid)[1].read_bytes() == b'unit,value\nkWh,123.45\n'
        assert client.get('/api/developer/provider').json()['key_configured'] is False
        client.post('/api/auth/register', json={'username':'other_owner','display_name':'Other','password':'Other-backup-pass-2026'})
        assert client.get('/api/projects/'+pid).status_code == 404
    assert backup.verify_backup(archive, digest)['checksums_valid']


def test_real_cad_ocr_preview_and_review_history_recover(cold, tmp_path, monkeypatch):
    root, pid, _, _ = cold
    with TestClient(create_app(root, start_worker=False)) as client:
        auth = client.post('/api/auth/login', json={'username':'backup_owner','password':'Backup-test-password-2026'}).json()
        client.headers['X-CSRF-Token'] = auth['csrf_token']
        fid = upload(client, pid, 'geometry.dxf', dxf_bytes())
        cad = client.post(f'/api/projects/{pid}/cad-inspections', json={'file_id':fid}).json()
        fid = upload(client, pid, 'clean.png', (GOLD/'clean.png').read_bytes())
        drawing = client.post(f'/api/projects/{pid}/drawings', json={'file_id':fid}).json()
        base = f"/api/projects/{pid}/drawings/{drawing['drawing_id']}"
        review = client.post(base+'/review', json={'expected_revision':1,'candidate_id':drawing['result']['candidates'][0]['candidate_id'],
                    'decision':'confirmed','basis':'Independent synthetic source transcribed for backup recovery test.'})
        assert review.status_code == 200, review.text
        history = client.get(base+'/history').json()
        stored_history = client.app.state.domain.store.history('drawing', drawing['drawing_id'])
        preview = client.get(base+'/preview.png').content
    archive, digest = make(cold, tmp_path)
    backup.restore_backup(archive, tmp_path/'restored', digest)
    with TestClient(create_app(tmp_path/'restored', start_worker=False)) as client:
        client.post('/api/auth/login', json={'username':'backup_owner','password':'Backup-test-password-2026'})
        assert client.get(base+'/history').json() == history
        assert client.get(base+'/preview.png').content == preview
        assert client.get(f"/api/projects/{pid}/cad-inspections/{cad['cad_id']}").json() == cad
        monkeypatch.setattr('backend.drawings.parser_hash', lambda: 'new-version-not-rewritten')
        assert client.get(base).json()['status'] == 'stale'
        assert client.get(base+'/preview.png').status_code == 409
        assert client.app.state.domain.store.history('drawing', drawing['drawing_id']) == stored_history


def test_pending_jobs_fail_without_resuming_and_append_task_history(cold, tmp_path):
    root, pid, _, _ = cold
    store = Store(root)
    for number, state in enumerate(('queued','running','failed')):
        rid = 'run_'+str(number)*32
        with closing(store.connect()) as con, con:
            con.execute('INSERT INTO jobs VALUES (?,?,?,?,NULL)', (rid,pid,state,json.dumps({'run_id':rid,'project_id':pid})))
    for kind in ('agent','search'):
        store.put(kind, {kind+'_id':kind+'_'+'a'*32,'project_id':pid,'status':'running','events':[]})
    archive, digest = make(cold, tmp_path)
    receipt = backup.restore_backup(archive, tmp_path/'restored', digest)
    assert receipt['pending_jobs_failed'] == 2 and len(receipt['appended_revisions']) == 2
    restored = Store(tmp_path/'restored')
    assert {x['status'] for x in restored.jobs(pid)} == {'failed'}
    assert store.job('run_'+'0'*32)['status'] == 'queued'
    for kind in ('agent','search'):
        history = restored.history(kind, kind+'_'+'a'*32)
        assert [x['status'] for x in history] == ['running','failed']
        assert len(store.history(kind,kind+'_'+'a'*32)) == 1


def test_active_service_and_maintenance_mutually_exclude(cold, tmp_path):
    root = cold[0]
    with TestClient(create_app(root, start_worker=False)):
        with pytest.raises(ValueError, match='busy'):
            backup.create_backup(root, tmp_path/'not-created.zip')
    assert not (tmp_path/'not-created.zip').exists()
    with RuntimeLease(root, 'maintenance'):
        with pytest.raises(ValueError, match='busy'):
            create_app(root, start_worker=False)
    make(cold, tmp_path)


def test_actual_process_lock_and_release_after_crash(cold, tmp_path):
    code = "import sys;from backend.runtime_lock import RuntimeLease;lease=RuntimeLease(sys.argv[1]);lease.__enter__();print('LOCKED',flush=True);sys.stdin.read()"
    child = subprocess.Popen([sys.executable,'-c',code,str(cold[0])],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
                             creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    try:
        assert child.stdout.readline().strip() == 'LOCKED'
        with pytest.raises(ValueError, match='busy'):
            make(cold, tmp_path)
    finally:
        child.kill();child.communicate(timeout=10)
    assert make(cold, tmp_path)[0].exists()


def test_restore_never_overwrites_existing_target_or_archive(cold, tmp_path):
    archive, digest = make(cold, tmp_path)
    before = archive.read_bytes()
    for target in (cold[0], tmp_path/'empty'):
        target.mkdir(exist_ok=True)
        with pytest.raises(ValueError, match='NEW'):
            backup.restore_backup(archive,target,digest)
    with pytest.raises(ValueError, match='exists'):
        backup.create_backup(cold[0],archive)
    assert archive.read_bytes() == before


def rewrite(archive, destination, transform):
    with zipfile.ZipFile(archive) as package:
        entries = [(x.filename,package.read(x.filename)) for x in package.infolist()]
    with zipfile.ZipFile(destination,'w') as package:
        for name, data in transform(entries):
            package.writestr(name,data)
    return core.sha(destination)


@pytest.mark.parametrize('name',['../outside','/outside','files/../../outside','files\\evil','files/C:evil','files/CON','files/name.','files//x','private/provider.json'])
def test_unsafe_members_rejected_before_creating_destination(cold, tmp_path, name):
    archive,_ = make(cold,tmp_path)
    bad=tmp_path/'bad.zip'
    digest=rewrite(archive,bad,lambda entries:entries+[(name,b'bad')])
    with pytest.raises(ValueError):backup.restore_backup(bad,tmp_path/'restored',digest)
    assert not (tmp_path/'restored').exists()


@pytest.mark.parametrize('mode',['truncated','wrong_digest','member_corrupt','manifest_missing','duplicate','case_alias','compressed','symlink','bad_schema'])
def test_corrupt_backups_fail_closed(cold,tmp_path,mode):
    archive,digest=make(cold,tmp_path);bad=tmp_path/'bad.zip'
    if mode=='truncated':
        bad.write_bytes(archive.read_bytes()[:80]);digest=core.sha(bad)
    elif mode=='wrong_digest':
        bad.write_bytes(archive.read_bytes());digest='0'*64
    elif mode=='member_corrupt':
        digest=rewrite(archive,bad,lambda entries:[(n,b'corrupt' if n.startswith('files/') else b) for n,b in entries])
    elif mode=='manifest_missing':
        digest=rewrite(archive,bad,lambda entries:[(n,b) for n,b in entries if n!='manifest.json'])
    elif mode in {'duplicate','case_alias'}:
        digest=rewrite(archive,bad,lambda entries:entries+[(entries[0][0].upper() if mode=='case_alias' else entries[0][0],entries[0][1])])
    elif mode=='compressed':
        with zipfile.ZipFile(bad,'w',compression=zipfile.ZIP_DEFLATED) as package:package.writestr('manifest.json',b'{}')
        digest=core.sha(bad)
    elif mode=='symlink':
        with zipfile.ZipFile(bad,'w') as package:
            info=zipfile.ZipInfo('files/link');info.create_system=3;info.external_attr=0o120777<<16
            package.writestr(info,'/outside');package.writestr('manifest.json','{}')
        digest=core.sha(bad)
    else:
        db=tmp_path/'bad.sqlite3'
        with zipfile.ZipFile(archive) as package:db.write_bytes(package.read('vra.sqlite3'))
        with closing(sqlite3.connect(db)) as con, con:con.execute('CREATE TRIGGER unwanted AFTER DELETE ON sessions BEGIN DELETE FROM records; END')
        def changed(entries):
            data=dict(entries);data['vra.sqlite3']=db.read_bytes();manifest=json.loads(data['manifest.json'])
            manifest['files']['vra.sqlite3']={'bytes':db.stat().st_size,'sha256':core.sha(db)}
            data['manifest.json']=json.dumps(manifest).encode();return data.items()
        digest=rewrite(archive,bad,changed)
    with pytest.raises((ValueError,zipfile.BadZipFile,KeyError)):
        backup.restore_backup(bad,tmp_path/'restored',digest)
    if (tmp_path/'restored').exists():
        assert (tmp_path/'restored/.restore-incomplete').exists()
        with pytest.raises(ValueError,match='incomplete'):create_app(tmp_path/'restored',start_worker=False)
    assert Store(cold[0]).get('project',cold[1])['project_id']==cold[1]


def test_source_mutation_missing_reference_and_budget_fail_without_valid_backup(cold,tmp_path,monkeypatch):
    root,pid,fid,_=cold;path=root/Store(root).get('file',fid)['path']
    old_write=zipfile.ZipFile.write
    def mutate(package,filename,*args,**kwargs):
        result=old_write(package,filename,*args,**kwargs)
        if Path(filename)==path:path.write_bytes(b'changed outside cooperating application')
        return result
    with monkeypatch.context() as m:
        m.setattr(zipfile.ZipFile,'write',mutate)
        with pytest.raises(ValueError,match='changed'):make(cold,tmp_path)
    with pytest.raises(ValueError):backup.verify_backup(tmp_path/'backup.zip',core.sha(tmp_path/'backup.zip'))
    with pytest.raises(ValueError,match='corrupt'):backup.create_backup(root,tmp_path/'corrupt-source.zip')
    monkeypatch.setattr(backup,'MAX_BYTES',5)
    with pytest.raises(ValueError,match='budget'):backup.create_backup(root,tmp_path/'budget.zip')


def test_unknown_files_and_linked_sources_are_not_silently_omitted(cold,tmp_path):
    root=cold[0];(root/'unknown.txt').write_text('not omitted')
    with pytest.raises(ValueError,match='Unknown'):make(cold,tmp_path)
    (root/'unknown.txt').unlink()
    original=root/Store(root).get('file',cold[2])['path']
    os.link(original,root/'files/hardlink.csv')
    with pytest.raises(ValueError,match='hard-linked'):make(cold,tmp_path)


def test_cli_returns_safe_summary_and_nonzero_rejection(cold,tmp_path):
    script=Path(__file__).resolve().parents[1]/'scripts/backup_runtime.py'
    cp=subprocess.run([sys.executable,str(script),'create','--source',str(cold[0]),'--archive',str(tmp_path/'cli.zip'),'--legacy-plaintext'],capture_output=True,text=True,timeout=20)
    assert cp.returncode==0,cp.stderr
    result=json.loads(cp.stdout);assert result['status']=='succeeded' and len(result['archive_sha256'])==64
    cp=subprocess.run([sys.executable,str(script),'restore','--archive',str(tmp_path/'cli.zip'),'--target',str(cold[0]),'--sha256',result['archive_sha256'],'--legacy-plaintext'],capture_output=True,text=True,timeout=20)
    assert cp.returncode==1 and json.loads(cp.stdout)['status']=='rejected'


def test_committed_wal_is_included_and_recovery_receipts_survive_second_backup(cold,tmp_path):
    root,pid,_,_=cold
    with closing(sqlite3.connect(root/'vra.sqlite3')) as con:
        con.execute('PRAGMA wal_autocheckpoint=0')
        con.execute("UPDATE records SET body=json_set(body,'$.name','Committed WAL value') WHERE kind='project' AND id=?", (pid,))
        con.commit()
        assert (root/'vra.sqlite3-wal').stat().st_size > 0
        archive,digest=make(cold,tmp_path)
        backup.restore_backup(archive,tmp_path/'restored',digest)
    assert Store(tmp_path/'restored').get('project',pid)['name']=='Committed WAL value'
    receipt=next((tmp_path/'restored/recovery').glob('*.json'))
    prior=receipt.read_bytes()
    second=tmp_path/'second.zip';meta=backup.create_backup(tmp_path/'restored',second)
    backup.restore_backup(second,tmp_path/'restored-again',meta['archive_sha256'])
    assert (tmp_path/'restored-again/recovery'/receipt.name).read_bytes()==prior
    assert len(list((tmp_path/'restored-again/recovery').glob('*.json')))==2


def test_background_operation_keeps_lease_after_http_lifespan_exits(cold,tmp_path):
    ready,release=threading.Event(),threading.Event()
    class Job:
        store=Store(cold[0])
        @runtime_operation
        def execute(self):
            ready.set()
            assert release.wait(15)
    job=Job()
    with TestClient(create_app(cold[0],start_worker=False)):
        thread=threading.Thread(target=job.execute)
        thread.start();assert ready.wait(5)
    try:
        with pytest.raises(ValueError,match='busy'):make(cold,tmp_path)
    finally:
        release.set();thread.join(5)
    assert not thread.is_alive()
    make(cold,tmp_path)


def test_partial_restore_is_unavailable_after_write_failure(cold,tmp_path,monkeypatch):
    archive,digest=make(cold,tmp_path)
    write=backup._copy_verified
    def fail(package,entries,target=None):
        write(package,entries,target)
        raise OSError('Deliberate isolated disk failure after copying files')
    monkeypatch.setattr(backup,'_copy_verified',fail)
    with pytest.raises(OSError):backup.restore_backup(archive,tmp_path/'partial',digest)
    assert (tmp_path/'partial/.restore-incomplete').exists()
    with pytest.raises(ValueError,match='incomplete'):create_app(tmp_path/'partial',start_worker=False)
    assert Store(cold[0]).get('project',cold[1])['project_id']==cold[1]


@pytest.mark.parametrize('operation',['verify','restore'])
def test_archive_changed_after_member_checks_cannot_publish(cold,tmp_path,monkeypatch,operation):
    archive,digest=make(cold,tmp_path)
    original=backup._copy_verified
    def change(package,entries,target=None):
        original(package,entries,target)
        with archive.open('ab') as stream:stream.write(b'external mutation after member verification')
    monkeypatch.setattr(backup,'_copy_verified',change)
    with pytest.raises(ValueError,match='hash/size'):
        if operation=='verify':backup.verify_backup(archive,digest)
        else:backup.restore_backup(archive,tmp_path/'partial',digest)
    if operation=='restore':assert (tmp_path/'partial/.restore-incomplete').exists()


def test_claimed_success_without_native_artifacts_is_not_recoverable(cold,tmp_path):
    root,pid,_,_=cold
    with closing(sqlite3.connect(root/'vra.sqlite3')) as con,con:
        con.execute('INSERT INTO jobs VALUES (?,?,?,?,NULL)', ('run_'+'d'*32,pid,'succeeded','{}'))
    with pytest.raises(ValueError,match='missing artifacts'):make(cold,tmp_path)
