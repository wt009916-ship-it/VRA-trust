"""Fault injection checks lifecycle/queue truth, not engineering/model accuracy."""
import sqlite3
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from backend.agent import Chat
from backend import core
from backend.robustness import Search
from backend.store import Store
from backend.task_capacity import CapacityError
from test_api import create_project


@pytest.fixture
def search_control(client,monkeypatch):
    pid=create_project(client)['project_id'];service=client.app.state.robustness
    ids=['run_'+('a'*32),'run_'+('b'*32)]
    def view(rid):
        return {'project_id':pid,'status':'succeeded','scheme_id':'baseline' if rid==ids[0] else 'R1',
                'metrics':{'annual_energy_kwh':100 if rid==ids[0] else 80},'provenance':{}}
    monkeypatch.setattr(service.domain,'view',view)
    monkeypatch.setattr(service.domain,'compare',lambda _:None)
    monkeypatch.setattr(service,'materials',lambda _:[{'name':'test material'}])
    body=Search(run_ids=ids,axes=[{'material':'test material','values':[.1,.2],'source':'synthetic lifecycle fixture'}],budget=2)
    return service,pid,body


def test_search_db_insert_failure_does_not_leak_slot(search_control):
    service,pid,body=search_control
    with service.store.connect() as con:
        con.execute("CREATE TRIGGER reject_search BEFORE INSERT ON records WHEN NEW.kind='search' BEGIN SELECT RAISE(ABORT,'isolated'); END")
    with pytest.raises(sqlite3.IntegrityError):service.start(pid,body)
    acquired=service.capacity.acquire(blocking=False)
    assert acquired,'DB insert failure leaked search slot'
    service.capacity.release()
    assert service.store.list('search')==[]


@pytest.mark.parametrize('kind',['agent','search'])
@pytest.mark.parametrize('stage',['start','__init__'])
def test_thread_start_failure_is_failed_and_releases_slot(client,search_control,monkeypatch,kind,stage):
    service,pid,body=search_control
    if kind=='agent':service=client.app.state.agent;body=Chat(message='lifecycle probe')
    def fail(*args,**kwargs):raise RuntimeError('isolated thread creation failure')
    monkeypatch.setattr(threading.Thread,stage,fail)
    with pytest.raises(RuntimeError,match='isolated'):service.start(pid,body)
    record=service.store.list(kind,pid)[0]
    assert record['status']=='failed' and record.get('finished_at')
    slots=2 if kind=='agent' else 1
    for _ in range(slots):assert service.capacity.acquire(blocking=False)
    for _ in range(slots):service.capacity.release()


def test_search_final_write_failure_still_releases_slot(search_control):
    service,pid,body=search_control
    with service.store.connect() as con:
        con.execute("CREATE TRIGGER reject_revision BEFORE INSERT ON records WHEN NEW.kind='search' AND NEW.revision>1 BEGIN SELECT RAISE(ABORT,'isolated'); END")
    with pytest.raises(sqlite3.IntegrityError):service.start(pid,body,background=False)
    acquired=service.capacity.acquire(blocking=False)
    assert acquired,'Final persistence failure leaked search slot'
    service.capacity.release()
    assert service.store.list('search',pid)[0]['status']=='running'  # not false success


def test_concurrent_queue_admission_is_global_and_project_bounded(tmp_path):
    root=tmp_path/'queue';stores=[Store(root) for _ in range(12)]
    for store in stores:store.task_limits=replace(store.task_limits,runs=3,project_runs=2)
    projects=['project_'+'a'*32,'project_'+'b'*32];barrier=threading.Barrier(12)
    def submit(i):
        barrier.wait(timeout=15)
        try:
            stores[i].add_job({'run_id':'run_'+uuid.uuid4().hex,'project_id':projects[i%2]});return True
        except CapacityError:return False
    with ThreadPoolExecutor(max_workers=12) as pool:results=list(pool.map(submit,range(12)))
    assert sum(results)==3
    with stores[0].connect() as con:
        counts=con.execute('SELECT project_id,COUNT(*) FROM jobs GROUP BY project_id').fetchall()
        assert all(n<=2 for _,n in counts) and sum(n for _,n in counts)==3
    claimed=stores[0].claim_job();stores[0].finish(claimed['run_id'],'failed','test failure')
    stores[0].add_job({'run_id':'run_'+uuid.uuid4().hex,'project_id':claimed['project_id']})


def test_api_cancel_queue_csrf_capacity_reuse_and_late_cancel(client,tmp_path,monkeypatch):
    from test_api import reference,confirm
    pid=reference(client)['project_id'];confirm(client,pid)
    engine=tmp_path/'engine';engine.write_bytes(b'not executed for admission test')
    (tmp_path/'Energy+.idd').write_bytes(b'fixture')
    monkeypatch.setattr(core,'engine_path',lambda:engine)
    store=client.app.state.domain.store;store.task_limits=replace(store.task_limits,runs=2,project_runs=2)
    body={'project_id':pid,'scheme_id':'baseline'}
    first=client.post('/api/runs',json=body);second=client.post('/api/runs',json=body)
    assert first.status_code==second.status_code==202
    rejected=client.post('/api/runs',json=body);assert rejected.status_code==429 and rejected.json()['code']=='task_capacity'
    rid=first.json()['run_id'];url='/api/runs/'+rid+'/cancel'
    token=client.headers.pop('X-CSRF-Token');assert client.post(url).status_code==403
    client.headers['X-CSRF-Token']=token
    cancelled=client.post(url).json();assert cancelled['status']=='failed' and cancelled['metrics'] is None
    assert client.post('/api/runs',json=body).status_code==202
    running=store.claim_job();assert running
    response=client.post('/api/runs/'+running['run_id']+'/cancel').json()
    assert response['status']=='running' and store.cancel_requested(running['run_id'])
    store.finish(running['run_id'],'succeeded')
    assert store.job(running['run_id'])['status']=='failed'


def test_persistent_agent_slots_prevent_new_instance_bypass(client):
    from backend.agent import Agent
    from backend.domain import Domain
    pid=create_project(client)['project_id'];service=client.app.state.agent
    for _ in range(2):service.store.add_active_record('agent',{'agent_id':'agent_'+uuid.uuid4().hex,'project_id':pid,'status':'running'})
    other=Agent(Domain(Store(service.store.root)),service.gateway)
    with pytest.raises(CapacityError):other.start(pid,Chat(message='capacity probe'))
    for _ in range(2):assert other.capacity.acquire(blocking=False)
    for _ in range(2):other.capacity.release()
    service.recover()
    result=service.start(pid,Chat(message='inspect evidence'),background=False)
    assert result['status']=='succeeded' and result['answer']['can_simulate'] is False


def test_stopped_domain_rejects_without_record(client):
    pid=create_project(client)['project_id'];service=client.app.state.agent
    service.domain.stop.set()
    with pytest.raises(CapacityError):service.start(pid,Chat(message='do not start'))
    assert service.store.list('agent',pid)==[]


@pytest.mark.parametrize('value',['0','-1','257','true','2.5'])
def test_invalid_queue_configuration_refused(tmp_path,monkeypatch,value):
    monkeypatch.setenv('VRA_ACTIVE_RUNS',value)
    with pytest.raises(ValueError):Store(tmp_path/'bad')


def test_cancel_requires_same_project_owner_and_session(client):
    # Lifecycle-only record: no engine/model output is fabricated.
    pid=create_project(client)['project_id'];store=client.app.state.domain.store
    rid='run_'+uuid.uuid4().hex
    store.add_job({'run_id':rid,'project_id':pid})
    other=client.post('/api/auth/register',json={'username':'second_owner','display_name':'Other test owner','password':'Isolated-test-only-password-2026'}).json()
    client.headers['X-CSRF-Token']=other['csrf_token']
    assert client.post('/api/runs/'+rid+'/cancel').status_code==404
    assert store.job(rid)['status']=='queued'
    client.cookies.clear()
    assert client.post('/api/runs/'+rid+'/cancel').status_code==401
    assert store.job(rid)['status']=='queued'


def test_shutdown_waits_for_registered_task_and_releases_capacity(client,monkeypatch):
    service=client.app.state.agent;domain=service.domain;pid=create_project(client)['project_id']
    entered=threading.Event();finished=threading.Event()
    def controlled_execute(record,body):
        entered.set()
        assert domain.stop.wait(5)
        service.store.put('agent',{**record,'status':'failed','error':'controlled shutdown'},record['revision'])
        finished.set()
    monkeypatch.setattr(service,'execute',controlled_execute)
    result=service.start(pid,Chat(message='shutdown lifecycle fixture'))
    assert entered.wait(2)
    domain.stop.set();domain.join_tasks()
    assert finished.is_set() and not domain.tasks
    assert service.store.get('agent',result['agent_id'])['status']=='failed'
    for _ in range(2):assert service.capacity.acquire(blocking=False)
    for _ in range(2):service.capacity.release()
