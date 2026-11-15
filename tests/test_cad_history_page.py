"""Real stored parser output, bounded page membership and current-source checks."""
import uuid
import pytest
from backend import core
from backend.cad_history import page
from test_cad_current import inspected, snapshot as records_snapshot


def clone(store, record, n, pid=None):
    ids=[]
    for _ in range(n):
        obj={k:v for k,v in record.items() if k not in {'revision','hash'}}
        obj['cad_id']='cad_'+uuid.uuid4().hex
        if pid:obj['project_id']=pid
        obj['hash']=core.hash_json(obj)
        store.put('cad',obj);ids.append(obj['cad_id'])
    return ids


def test_real_cad_paging_bounds_snapshot_new_records_and_source_withdrawal(client, monkeypatch):
    pid,base,record,original=inspected(client)
    store=client.app.state.domain.store
    raw=store.get('cad',record['cad_id'])
    ids=[record['cad_id'],*clone(store,raw,44)]
    other='project_'+uuid.uuid4().hex
    clone(store,raw,2,pid=other)
    before=records_snapshot(store)
    import backend.cad as module
    calls=[];view=module.Cad.view
    def counted(self,pid,cid):
        calls.append(cid);return view(self,pid,cid)
    monkeypatch.setattr(module.Cad,'view',counted)
    r=client.get(base+'/cad-inspection-page').json()
    assert len(r['records'])==20 and calls==list(reversed(ids))[:20]
    assert all(x['result']['objects'][0]['length_m']==5 for x in r['records'])
    assert records_snapshot(store)==before
    seen=[x['cad_id'] for x in r['records']]
    added=clone(store,raw,1)[0]
    first=r
    while r['next_before'] is not None:
        calls.clear()
        response=client.get(base+'/cad-inspection-page',params={'snapshot':r['snapshot'],'before':r['next_before']})
        assert response.status_code==200
        r=response.json();assert len(calls)==len(r['records'])<=20
        seen.extend(x['cad_id'] for x in r['records'])
    assert seen==list(reversed(ids)) and added not in seen
    assert client.get(base+'/cad-inspection-page').json()['records'][0]['cad_id']==added
    # Snapshot freezes membership, never the validity of quantities.
    _,path=client.app.state.domain.file_record(pid,record['source']['file_id'])
    try:
        path.write_bytes(b'corrupt isolated source')
        oldpage=client.get(base+'/cad-inspection-page',params={'snapshot':first['snapshot']}).json()
        assert all(x['status']=='stale' and x['result'] is None for x in oldpage['records'])
    finally:path.write_bytes(original)


def test_page_query_limits_auth_empty_and_legacy_contract(client):
    from test_api import create_project
    pid=create_project(client)['project_id'];base=f'/api/projects/{pid}'
    assert client.get(base+'/cad-inspection-page').json()=={'records':[],'snapshot':0,'next_before':None,'limit':20,'membership':'snapshot_order_current_source_validation'}
    assert client.get(base+'/cad-inspections').json()==[]
    for params in [{'limit':0},{'limit':21},{'limit':'x'},{'before':-1},{'snapshot':2**53},{'snapshot':-1}]:
        assert client.get(base+'/cad-inspection-page',params=params).status_code==422
    assert client.get(base+'/cad-inspection-page?before=1').status_code in {400,409,422}
    from fastapi.testclient import TestClient
    from test_auth import register
    with TestClient(client.app) as outsider:
        assert outsider.get(base+'/cad-inspection-page').status_code==401
        register(outsider,'different_owner')
        assert outsider.get(base+'/cad-inspection-page').status_code==404


def test_large_catalog_reads_only_one_page_and_keeps_latest_snapshot_revision(client,monkeypatch):
    pid,base,record,_=inspected(client);store=client.app.state.domain.store
    raw=store.get('cad',record['cad_id']);ids=clone(store,raw,1000)
    import backend.cad as module
    calls=[];view=module.Cad.view
    def counted(self,pid,cid):calls.append(cid);return view(self,pid,cid)
    monkeypatch.setattr(module.Cad,'view',counted)
    response=client.get(base+'/cad-inspection-page')
    assert response.status_code==200
    r=response.json();assert len(calls)==20 and len(r['records'])==20
    assert [x['cad_id'] for x in r['records']]==list(reversed(ids))[:20]
    # Append a revision after freezing; it cannot move into another snapshot page.
    latest=store.get('cad',ids[0]);store.put('cad',latest,expected=latest['revision'])
    seen=[x['cad_id'] for x in r['records']]
    while r['next_before'] is not None:
        r=client.get(base+'/cad-inspection-page',params={'snapshot':r['snapshot'],'before':r['next_before']}).json()
        seen.extend(x['cad_id'] for x in r['records'])
    assert len(seen)==len(set(seen))==1001
    assert seen==list(reversed([record['cad_id'],*ids]))


@pytest.mark.parametrize('kwargs',[{'limit':True},{'limit':21},{'snapshot':True},{'before':1},{'snapshot':-1}])
def test_direct_page_contract_rejects_invalid_bounds(kwargs):
    with pytest.raises(core.ValidationError):page(None,'project_unused',**kwargs)
