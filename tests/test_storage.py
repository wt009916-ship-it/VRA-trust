import json
import os
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from backend import core, storage
from backend.api import create_app
from backend.auth import Auth
from backend.backup import create_backup, restore_backup
from backend.domain import Domain
from backend.schema import ProjectCreate
from backend.store import Store


def project(domain):
    return domain.create_project(ProjectCreate(name='quota test',building={'use':'office','location':'synthetic','region':'test','area_m2':100.0}))['project_id']


@pytest.fixture
def setup(tmp_path):
    domain=Domain(Store(tmp_path/'data'))
    domain.storage.limits=storage.Limits(single_bytes=20,project_bytes=30,total_bytes=50,project_files=3,total_files=5,reserve_bytes=1)
    return domain,project(domain)


def unchanged(domain, count, size):
    records=domain.store.list('file')
    assert len(records)==count
    paths=list((domain.store.root/'files').glob('*'))
    assert len(paths)==count and sum(p.stat().st_size for p in paths)==size
    for r in records:assert core.sha(domain.store.root/r['path'])==r['hash']


@pytest.mark.parametrize('field,first,second,code',[
    ('single_bytes',20,21,'file_size_limit'),
    ('project_bytes',20,11,'source_project_bytes_limit'),
    ('project_files',1,1,'source_project_files_limit'),
    ('total_bytes',20,11,'source_total_bytes_limit'),
    ('total_files',1,1,'source_total_files_limit'),
])
def test_exact_limit_and_one_over(setup,field,first,second,code):
    domain,pid=setup
    changes={field: 1 if field.endswith('files') else 30 if field.endswith('bytes') and field!='single_bytes' else 20}
    domain.storage.limits=replace(domain.storage.limits,**changes)
    domain.add_file(pid,'first.csv',b'a'*first)
    if field in {'total_bytes','total_files'}:pid=project(domain)
    if field.endswith('bytes') and field!='single_bytes':
        domain.add_file(pid,'exact.csv',b'b'*10)
        before=(2,30);second=1
    else:before=(1,first)
    with pytest.raises(storage.StorageError) as exc:domain.add_file(pid,'over.csv',b'x'*second)
    assert exc.value.code==code
    unchanged(domain,*before)


def test_runtime_global_limit_prevents_new_project_bypass(setup):
    domain,pid=setup
    domain.storage.limits=replace(domain.storage.limits,total_bytes=21)
    domain.add_file(pid,'a.csv',b'a'*20)
    other=project(domain)
    domain.add_file(other,'b.csv',b'b')
    with pytest.raises(storage.StorageError,match='共享'):domain.add_file(project(domain),'c.csv',b'c')
    used=domain.storage.usage(other)
    assert used['project_bytes']==1 and used['project_files']==1
    assert not used['shared_capacity_available']
    assert not {'total_bytes','total_files','orphan_files'} & used.keys()
    unchanged(domain,2,21)


def test_real_concurrent_separate_store_instances_serialize_admission(setup):
    domain,pid=setup
    domain.storage.limits=replace(domain.storage.limits,project_bytes=30,project_files=20,total_files=20)
    participants=[]
    for _ in range(12):
        other=Domain(Store(domain.store.root));other.storage.limits=domain.storage.limits;participants.append(other)
    barrier=threading.Barrier(len(participants))
    def upload(item):
        barrier.wait(timeout=15)
        try:item.add_file(pid,'competing.csv',b'0123456789');return 'accepted'
        except storage.StorageError as exc:return exc.code
    with ThreadPoolExecutor(max_workers=len(participants)) as pool:results=list(pool.map(upload,participants))
    assert results.count('accepted')==3 and results.count('source_project_bytes_limit')==9
    unchanged(domain,3,30)


def test_orphan_is_charged_and_not_deleted_on_restart(setup):
    domain,pid=setup
    folder=domain.store.root/'files';folder.mkdir()
    orphan=folder/'crash-original.csv';orphan.write_bytes(b'o'*50)
    restarted=Domain(Store(domain.store.root));restarted.storage.limits=domain.storage.limits
    with pytest.raises(storage.StorageError) as exc:restarted.add_file(pid,'new.csv',b'n')
    assert exc.value.code=='source_total_bytes_limit'
    assert orphan.read_bytes()==b'o'*50 and restarted.store.list('file')==[]


@pytest.mark.parametrize('damage',['missing','size','metadata','directory'])
def test_corrupt_existing_inventory_refuses_new_upload(setup,damage):
    domain,pid=setup
    original=domain.add_file(pid,'old.csv',b'original')
    path=domain.store.root/original['path']
    if damage=='missing':path.unlink()
    elif damage=='size':path.write_bytes(b'changed length')
    elif damage=='directory':(path.parent/'unexpected').mkdir()
    else:
        with domain.store.connect() as con:
            obj={**original,'size':True};con.execute("UPDATE records SET body=? WHERE kind='file'",(json.dumps(obj),))
    before=domain.store.list('file')
    with pytest.raises(storage.StorageError) as exc:domain.add_file(pid,'new.csv',b'n')
    assert exc.value.code=='storage_integrity' and domain.store.list('file')==before


@pytest.mark.skipif(os.name=='nt',reason='Linux symlink; Windows reparse covered by maintenance path tests')
def test_linked_original_directory_is_not_followed(setup,tmp_path):
    domain,pid=setup
    outside=tmp_path/'outside';outside.mkdir()
    (domain.store.root/'files').symlink_to(outside,target_is_directory=True)
    with pytest.raises(storage.StorageError) as exc:domain.add_file(pid,'new.csv',b'n')
    assert exc.value.code=='storage_integrity' and list(outside.iterdir())==[]


def test_scan_budget_fail_closed_preserves_files(setup,monkeypatch):
    domain,pid=setup
    folder=domain.store.root/'files';folder.mkdir()
    for i in range(3):(folder/str(i)).write_bytes(b'x')
    monkeypatch.setattr(storage,'SCAN_LIMIT',2)
    with pytest.raises(storage.StorageError) as exc:domain.add_file(pid,'new.csv',b'n')
    assert exc.value.code=='storage_scan_limit' and len(list(folder.iterdir()))==3


def test_flush_failure_removes_only_new_file(setup,monkeypatch):
    domain,pid=setup
    domain.add_file(pid,'old.csv',b'old')
    def fail(_):raise OSError('isolated flush failure')
    with monkeypatch.context() as patch:
        patch.setattr(storage.os,'fsync',fail)
        with pytest.raises(storage.StorageError) as exc:domain.add_file(pid,'new.csv',b'new')
    assert exc.value.code=='storage_write_failed'
    unchanged(domain,1,3)
    domain.add_file(pid,'retry.csv',b'retry');unchanged(domain,2,8)


def test_actual_sqlite_insert_failure_rolls_back_file(setup):
    domain,pid=setup
    domain.add_file(pid,'old.csv',b'old')
    with domain.store.connect() as con:
        con.execute("CREATE TRIGGER reject_file BEFORE INSERT ON records WHEN NEW.kind='file' BEGIN SELECT RAISE(ABORT,'deliberate rejection'); END")
    with pytest.raises(storage.StorageError) as exc:domain.add_file(pid,'new.csv',b'new')
    assert exc.value.code=='storage_write_failed';unchanged(domain,1,3)
    with domain.store.connect() as con:con.execute('DROP TRIGGER reject_file')
    domain.add_file(pid,'retry.csv',b'retry');unchanged(domain,2,8)


def test_commit_success_then_reported_failure_preserves_committed_file(setup,monkeypatch):
    domain,pid=setup
    class Uncertain(sqlite3.Connection):
        def commit(self):
            super().commit()
            raise sqlite3.OperationalError('isolated post-commit failure')
    def connect():
        con=sqlite3.connect(domain.store.db,factory=Uncertain);con.row_factory=sqlite3.Row;return con
    monkeypatch.setattr(domain.store,'connect',connect)
    with pytest.raises(storage.StorageError):domain.add_file(pid,'committed.csv',b'committed')
    unchanged(domain,1,9)


def test_exclusive_create_collision_never_overwrites_old_file(setup,monkeypatch):
    domain,pid=setup
    domain.add_file(pid,'old.csv',b'old')
    old=domain.store.list('file')[0]
    class Fixed:hex=old['file_id'][5:]
    monkeypatch.setattr(storage.uuid,'uuid4',lambda:Fixed())
    with pytest.raises(storage.StorageError):domain.add_file(pid,'new.csv',b'new')
    unchanged(domain,1,3)


def test_disk_reserve_precheck_only(setup,monkeypatch):
    domain,pid=setup
    usage=storage.shutil.disk_usage(domain.store.root)
    monkeypatch.setattr(storage.shutil,'disk_usage',lambda _:usage._replace(free=4))
    domain.storage.limits=replace(domain.storage.limits,reserve_bytes=3)
    domain.add_file(pid,'exact.csv',b'a')
    with pytest.raises(storage.StorageError) as exc:domain.add_file(pid,'over.csv',b'ab')
    assert exc.value.code=='storage_reserve';unchanged(domain,1,1)


def test_reduced_limit_preserves_old_source_and_history(setup):
    domain,pid=setup
    original=domain.add_file(pid,'old.csv',b'old')
    domain.storage.limits=replace(domain.storage.limits,project_bytes=1)
    with pytest.raises(storage.StorageError):domain.add_file(pid,'new.csv',b'n')
    assert domain.file_record(pid,original['file_id'])[1].read_bytes()==b'old'
    assert domain.store.history('file',original['file_id'])==[original]


@pytest.mark.parametrize('value',['0','-1','1.5','NaN','true',' 2','999999999999999999'])
def test_invalid_configuration_fails_before_serving(tmp_path,monkeypatch,value):
    monkeypatch.setenv('VRA_SOURCE_TOTAL_MB',value)
    with pytest.raises(ValueError):create_app(tmp_path/'invalid',start_worker=False)


def test_backup_restore_recounts_originals(setup,tmp_path):
    domain,pid=setup;Auth(domain.store)
    domain.add_file(pid,'old.csv',b'old')
    archive=tmp_path/'snapshot.zip';info=create_backup(domain.store.root,archive)
    target=tmp_path/'restored';restore_backup(archive,target,info['archive_sha256'])
    restored=Domain(Store(target));restored.storage.limits=replace(domain.storage.limits,project_bytes=3)
    assert restored.storage.usage(pid)['project_bytes']==3
    with pytest.raises(storage.StorageError):restored.add_file(pid,'new.csv',b'n')
    unchanged(restored,1,3)


def test_authenticated_usage_and_upload_limit_do_not_expose_other_project(client):
    from test_api import create_project
    pid=create_project(client)['project_id'];domain=client.app.state.domain
    domain.storage.limits=replace(domain.storage.limits,project_files=1)
    base='/api/projects/'+pid
    assert client.post(base+'/files',files={'file':('a.csv',b'a')}).status_code==201
    response=client.post(base+'/files',files={'file':('b.csv',b'b')})
    assert response.status_code==507 and response.json()['code']=='source_project_files_limit'
    result=client.get(base+'/storage').json()
    assert result['project_bytes']==1 and 'total_bytes' not in result
    with TestClient(client.app) as stranger:
        assert stranger.get(base+'/storage').status_code==401
        login=stranger.post('/api/auth/register',json={'username':'storage_other','display_name':'other','password':'Test-only-long-pass-2026'}).json()
        stranger.headers['X-CSRF-Token']=login['csrf_token']
        assert stranger.get(base+'/storage').status_code==404
        assert stranger.post(base+'/files',files={'file':('b.csv',b'b')}).status_code==404


@pytest.mark.parametrize('failure',['quota','evidence','ownership'])
def test_reference_import_atomic_project_files_evidence_and_owner(client,failure):
    domain=client.app.state.domain
    if failure=='quota':domain.storage.limits=replace(domain.storage.limits,project_bytes=1)
    else:
        sql=("CREATE TRIGGER reject_evidence BEFORE INSERT ON records WHEN NEW.kind='evidence' BEGIN SELECT RAISE(ABORT,'deliberate'); END" if failure=='evidence'
             else "CREATE TRIGGER reject_owner BEFORE INSERT ON project_owners BEGIN SELECT RAISE(ABORT,'deliberate'); END")
        with domain.store.connect() as con:con.execute(sql)
    assert client.post('/api/reference-projects').status_code==507
    assert domain.store.list('project')==[] and domain.store.list('evidence')==[]
    unchanged(domain,0,0)
    with domain.store.connect() as con:assert con.execute('SELECT COUNT(*) FROM project_owners').fetchone()[0]==0
    if failure=='quota':domain.storage.limits=storage.Limits()
    else:
        with domain.store.connect() as con:con.execute('DROP TRIGGER '+('reject_evidence' if failure=='evidence' else 'reject_owner'))
    response=client.post('/api/reference-projects');assert response.status_code==201
    pid=response.json()['project_id']
    assert client.get('/api/projects/'+pid).status_code==200
    assert len(domain.store.list('file'))==4 and len(domain.store.list('evidence',pid))==4
    assert client.get('/api/projects/'+pid+'/gate').json()['can_simulate'] is False


def test_store_put_in_requires_transaction(setup):
    domain,pid=setup
    with domain.store.connect() as con:
        with pytest.raises(RuntimeError):domain.store.put_in(con,'project',domain.store.get('project',pid),1)
