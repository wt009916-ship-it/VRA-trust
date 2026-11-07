"""Current-state checks use genuine persisted parser output; no geometry fallback."""
import json
import uuid
from datetime import datetime
from fastapi.testclient import TestClient
from backend import core
from test_api import create_project
from test_auth import register
from test_cad import upload, dxf_bytes


def inspected(client):
    pid = create_project(client)['project_id']
    content = dxf_bytes()
    fid = upload(client, pid, 'current.dxf', content)
    base = f'/api/projects/{pid}'
    response = client.post(base+'/cad-inspections', json={'file_id': fid})
    assert response.status_code == 201, response.text
    return pid, base, response.json(), content


def states(client, base, ids):
    return client.post(base+'/cad-current-states', json={'cad_ids': ids})


def snapshot(store):
    with store.connect() as con:
        return [tuple(r) for r in con.execute('SELECT * FROM records ORDER BY kind,id,revision')]


def test_current_state_real_source_corruption_restoration_readonly_and_shared_checks(client, monkeypatch):
    pid, base, record, original = inspected(client)
    domain = client.app.state.domain
    store = domain.store
    second = store.get('cad', record['cad_id'])
    second = {k: v for k, v in second.items() if k not in {'revision', 'hash'}}
    second['cad_id'] = 'cad_'+uuid.uuid4().hex
    second['hash'] = core.hash_json(second)
    store.put('cad', second)  # same real source, two immutable inspection bindings
    ids = [record['cad_id'], second['cad_id']]
    before = snapshot(store)
    import backend.cad as cad
    parser, file_record = cad.parser_version, domain.file_record
    calls = {'parser': 0, 'source': 0}
    def counted_parser():
        calls['parser'] += 1
        return parser()
    def counted_file(*args):
        calls['source'] += 1
        return file_record(*args)
    monkeypatch.setattr(cad, 'parser_version', counted_parser)
    monkeypatch.setattr(domain, 'file_record', counted_file)
    response = states(client, base, ids)
    assert response.status_code == 200, response.text
    payload = response.json()
    datetime.fromisoformat(payload['checked_at'])
    assert calls == {'parser': 1, 'source': 1}
    assert all(s['status'] == 'parsed' and s['reasons'] == [] for s in payload['states'])
    assert payload['states'][0]['inspection_hash'] == record['hash']
    assert 'result' not in response.text and 'objects' not in response.text
    assert len(response.content) < 2000
    _, path = file_record(pid, record['source']['file_id'])
    try:
        path.write_bytes(b'corrupt isolated original')
        response = states(client, base, ids)
        assert all(s['status'] == 'stale' and s['reasons'] == ['source_unavailable'] for s in response.json()['states'])
        assert client.get(base+'/cad-inspections/'+ids[0]).json()['result'] is None
    finally:
        path.write_bytes(original)
    assert states(client, base, ids).json()['states'][0]['status'] == 'parsed'
    fresh = client.get(base+'/cad-inspections/'+ids[0]).json()
    assert fresh['result']['objects'][0]['length_m'] == 5
    assert snapshot(store) == before


def test_parser_changes_unavailability_and_new_source_binding_never_return_old_geometry(client, monkeypatch):
    pid, base, record, original = inspected(client)
    cid, fid = record['cad_id'], record['source']['file_id']
    import backend.cad as cad
    original_parser = cad.parser_version
    monkeypatch.setattr(cad, 'parser_version', lambda: 'changed')
    state = states(client, base, [cid]).json()['states'][0]
    assert state['status'] == 'stale' and state['reasons'] == ['parser_changed']
    assert client.get(base+'/cad-inspections/'+cid).json()['result'] is None
    def unavailable():
        raise ImportError('isolated test dependency unavailable')
    monkeypatch.setattr(cad, 'parser_version', unavailable)
    state = states(client, base, [cid]).json()['states'][0]
    assert state['status'] == 'unverified' and state['current_parser_hash'] is None
    assert client.get(base+'/cad-inspections/'+cid).json()['result'] is None
    monkeypatch.setattr(cad, 'parser_version', original_parser)
    domain = client.app.state.domain
    source, path = domain.file_record(pid, fid)
    replacement = original+b'\n'
    try:
        path.write_bytes(replacement)
        updated = {**source, 'hash': core.sha(path), 'size': len(replacement)}
        domain.store.put('file', updated, expected=source['revision'])
        state = states(client, base, [cid]).json()['states'][0]
        assert state['status'] == 'stale' and state['reasons'] == ['source_binding_changed']
        assert client.get(base+'/cad-inspections/'+cid).json()['result'] is None
    finally:
        path.write_bytes(original)


def test_current_states_scope_auth_csrf_bounds_and_record_integrity(client):
    pid, base, record, _ = inspected(client)
    cid = record['cad_id']
    other = create_project(client)['project_id']
    assert states(client, f'/api/projects/{other}', [cid]).status_code == 409
    assert states(client, base, ['cad_'+'f'*32]).status_code == 404
    for ids in ([], [cid, cid], ['invalid'], [123], ['cad_'+f'{i:032x}' for i in range(51)]):
        assert states(client, base, ids).status_code == 422
    token = client.headers.pop('X-CSRF-Token')
    assert states(client, base, [cid]).status_code == 403
    client.headers['X-CSRF-Token'] = token
    with TestClient(client.app) as outsider:
        assert states(outsider, base, [cid]).status_code == 401
        register(outsider, 'different_owner')
        assert states(outsider, base, [cid]).status_code == 404
    store = client.app.state.domain.store
    obj = store.get('cad', cid)
    obj['result']['counts']['LINE'] = 999
    with store.connect() as con:
        con.execute('UPDATE records SET body=? WHERE kind=? AND id=?', (json.dumps(obj), 'cad', cid))
    assert states(client, base, [cid]).status_code == 409
    assert client.get(base+'/cad-inspections/'+cid).status_code == 409
