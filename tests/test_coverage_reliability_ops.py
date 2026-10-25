"""Geometry integrity, real persistence, and adversarial tool protocol controls."""
import json
import zipfile

import pytest
from pydantic import ValidationError
from shapely.geometry import Polygon

from backend import core, model_export, model_import
from backend.agent import Chat
from backend.api import create_app
from backend.model_geometry import floor_area, geometry, thermal_geometry_model
from backend.model_schema import ImportOptions, ModelDraft, Room
from backend.runtime_backup import restore_snapshot
from test_model_workbench import model_body, project, upload, drawing_bytes


def courtyard():
    return Room(id='Court', name='Synthetic courtyard ring', polygon=[(0.,0.),(10.,0.),(10.,10.),(0.,10.)],
                holes=[[(3.,3.),(7.,3.),(7.,7.),(3.,7.)]], height_m=3.).model_dump()


def test_holes_preserve_net_area_volume_and_ifc_roundtrip(tmp_path):
    room = courtyard()
    assert floor_area(room) == pytest.approx(84)
    assert sum(Polygon(s['polygon']).area*s['height_m'] for s in room['segments']) == pytest.approx(252)
    hole = Polygon(room['holes'][0])
    assert all(Polygon(s['polygon']).intersection(hole).area < 1e-9 for s in room['segments'])
    body = {**model_body(), 'rooms': [room]}
    model = ModelDraft.model_validate(body).model_dump()
    assert geometry(model)
    model['thermal']['geometry_tolerance_m'] = .01
    normalized, _ = thermal_geometry_model(model)
    assert Polygon(normalized['rooms'][0]['polygon'], normalized['rooms'][0]['holes']).area == 84
    path = tmp_path/'courtyard.ifc'
    path.write_text(model_export.ifc(model), encoding='utf-8')
    candidate = model_import.ifc(path, ImportOptions(file_id='unused'))
    assert len(candidate['rooms']) == 1 and len(candidate['rooms'][0]['holes']) == 1
    assert floor_area(candidate['rooms'][0]) == pytest.approx(84)
    raw = {**room, 'holes': [[(20.,20.),(21.,20.),(21.,21.),(20.,21.)]], 'segments': []}
    with pytest.raises(ValidationError, match='孔洞'):
        Room.model_validate(raw)
    # Tampering with a decomposition must not refill the source hole.
    with pytest.raises(ValidationError, match='最低分段'):
        Room.model_validate({**room, 'segments': [{k: room[k] for k in ('polygon','elevation_m','height_m')}]})


def test_nested_vector_contours_are_kept_as_review_candidates():
    p = Polygon([(0,0),(10,0),(10,10),(0,10)], [[(3,3),(7,3),(7,7),(3,7)]])
    rooms = model_import._candidates([p], ImportOptions(file_id='unused'), 'Synthetic nested DXF')
    assert len(rooms) == 1 and floor_area(rooms[0]) == 84


def test_ifc_scope_inventory_and_owned_endpoint(client):
    import ifcopenshell
    pid, other = project(client), project(client)
    raw = model_export.ifc(ModelDraft.model_validate(model_body()).model_dump())
    document = ifcopenshell.file.from_string(raw)
    inventory = model_import.storey_inventory(document)
    assert inventory['total_spaces'] == 2 and len(inventory['storeys']) == 1
    fid = upload(client, pid, 'scoped.ifc', raw.encode())
    path = f'/api/projects/{pid}/files/{fid}/ifc-storeys'
    assert client.get(path).json() == inventory
    assert client.get(f'/api/projects/{other}/files/{fid}/ifc-storeys').status_code == 409
    selected = inventory['storeys'][0]['id']
    task = client.post(f'/api/projects/{pid}/imports', json={'file_id': fid, 'ifc_storey_ids': [selected], 'ifc_origin_m':inventory['suggested_origin_m']})
    assert task.status_code == 201, task.text
    assert task.json()['candidate']['diagnostics']['scope'] == 'selected_storeys'
    assert 'origin_m=' in task.json()['candidate']['rooms'][0]['source_locator']
    assert client.post(f'/api/projects/{pid}/imports', json={'file_id': fid, 'ifc_storey_ids': ['missing']}).status_code == 409


def test_multi_intent_plan_survives_read_failure_and_reload(client, monkeypatch):
    pid = project(client)
    agent = client.app.state.agent
    body = Chat(message='核对天气、模型、仿真、材料和资料来源')
    result = agent.start(pid, body, background=False)
    assert result['status'] == 'succeeded'
    assert result['resolved_tasks'] == ['weather','model','simulation','materials','evidence']
    assert len(result['answer']['task_results']) == 5
    assert sum(e['tool']=='evidence_validate' for e in result['events']) == 1
    assert not client.app.state.domain.store.jobs(pid)
    assert client.get(f'/api/projects/{pid}/agent').json()[0]['agent_id'] == result['agent_id']
    def broken(_):
        raise core.ValidationError('Controlled weather source failure')
    monkeypatch.setattr(client.app.state.weather, 'list', broken)
    result = agent.start(pid, body, background=False)
    assert result['status'] == 'partial'
    assert result['answer']['task_results'][0]['status'] == 'partial'
    assert all(r['status']=='succeeded' for r in result['answer']['task_results'][1:])


def setup_provider(agent, monkeypatch, replies):
    monkeypatch.setattr(agent.gateway, 'public', lambda: {'enabled': True, 'key_configured': True, 'provider': 'controlled protocol', 'model': 'fixture'})
    iterator = iter(replies)
    monkeypatch.setattr(agent.gateway, 'complete', lambda *a, **k: next(iterator))


def tool(name, arguments, identifier='call1'):
    return {'role': 'assistant', 'content': None, 'tool_calls': [{'id': identifier, 'type': 'function',
        'function': {'name': name, 'arguments': arguments}}]}


def test_tool_protocol_bounded_repair_and_mutation_dedup(client, monkeypatch):
    pid = project(client)
    agent = client.app.state.agent
    replies = [tool('simulation_create', '{'), tool('simulation_create', '{}', 'call2'),
               tool('simulation_create', '{"scheme_id":"baseline"}', 'call3'),
               {'role': 'assistant', 'content': '工具核查已结束，缺失证据不能补造。'}]
    setup_provider(agent, monkeypatch, replies)
    original = agent.call
    submissions = []
    def controlled(pid, name, args, allowed):
        if name == 'simulation_create':
            submissions.append(args)
            return {'status': 'queued', 'run_id': 'protocol-only-no-engine-executed'}
        return original(pid, name, args, allowed)
    monkeypatch.setattr(agent, 'call', controlled)
    # No keyword resolves diagnose, whose tool list intentionally does not allow writes.
    result = agent.start(pid, Chat(message='检查天气和模型', mode='provider', allow_compute=True), background=False)
    assert result['status'] == 'succeeded', result
    assert len(submissions) == 1
    assert any(e.get('reused_event') is not None for e in result['events'])
    assert any(e['tool']=='protocol.validation' for e in result['events'])
    assert not client.app.state.domain.store.jobs(pid)
    setup_provider(agent, monkeypatch, [tool('simulation_create', '{}')])
    result = agent.start(pid, Chat(message='检查天气和模型', mode='provider', allow_compute=False), background=False)
    assert result['status'] == 'partial' and len(submissions) == 1
    assert '未开放' in result['explanation_error']


def test_runtime_snapshot_restore_and_admin_guards(client, tmp_path):
    pid = project(client)
    fid = upload(client, pid, 'original.dxf', drawing_bytes())
    task = client.post(f'/api/projects/{pid}/imports', json={'file_id': fid}).json()
    root = client.app.state.domain.store.root
    assert (root/'model-workflows.sqlite3').is_file()
    url = '/api/admin/runtime/backups'
    body = {'current_password': 'Test-only-long-pass-2026'}
    assert client.post(url, json=body, headers={'X-CSRF-Token':''}).status_code == 403
    assert client.post(url, json={'current_password':'Wrong-password-value!'}).status_code == 403
    response = client.post(url, json=body)
    assert response.status_code == 201, response.text
    meta = response.json()
    archive = root/'runtime-snapshots'/(meta['id']+'.zip')
    target = tmp_path/'restored'
    report = restore_snapshot(archive, target)
    assert report['passed'] and report['uploaded_files_checked'] == 1
    assert (target/'model-workflows.sqlite3').is_file()
    assert report['database']['users'] == 1
    # Original account, file and interrupted review workflow remain usable in a new app.
    from fastapi.testclient import TestClient
    with TestClient(create_app(target, start_worker=False)) as restored:
        login = restored.post('/api/auth/login', json={'username':'test_owner', 'password':body['current_password']})
        assert login.status_code == 200
        restored.headers['X-CSRF-Token'] = login.json()['csrf_token']
        assert restored.get(f'/api/projects/{pid}/files/{fid}').content == client.get(f'/api/projects/{pid}/files/{fid}').content
        record = restored.get(f'/api/projects/{pid}/imports').json()[0]
        assert record['import_id'] == task['import_id'] and record['status'] == 'awaiting_review'
        review = restored.post(f'/api/projects/{pid}/imports/{task["import_id"]}/review', json=model_body())
        assert review.status_code == 200, review.text
    assert client.get(f'/api/projects/{pid}/model').json() is None
    with pytest.raises(core.ValidationError, match='新目录'):
        restore_snapshot(archive, target)
    assert client.post(url+'/'+meta['id']+'/verify', json=body).json()['passed']
    download = client.get(url+'/'+meta['id']+'/download')
    assert download.status_code == 200 and download.content[:2] == b'PK'
    assert client.get(url).json()[0]['last_verification']['passed']
    # Active task refusal and maintenance cleanup.
    client.app.state.domain.store.put('agent', {'agent_id':'agent_'+'a'*32, 'project_id':pid,'status':'running'})
    assert client.post(url, json=body).status_code == 409
    assert client.get('/api/health').json()['maintenance'] is False


def test_restore_rejects_tamper_and_traversal(client, tmp_path):
    from backend.runtime_backup import create_snapshot
    archive = tmp_path/'snapshot.zip'
    create_snapshot(client.app.state.domain.store, archive)
    for mode in ('hash', 'traversal'):
        target = tmp_path/(mode+'.zip')
        with zipfile.ZipFile(archive) as source, zipfile.ZipFile(target, 'w') as out:
            manifest = json.loads(source.read('manifest.json'))
            if mode == 'hash':
                manifest['files'][0]['sha256'] = '0'*64
            else:
                old = manifest['files'][0]['path']
                manifest['files'][0]['path'] = '../outside.sqlite3'
            for info in source.infolist():
                if info.filename == 'manifest.json':
                    continue
                name = 'payload/../outside.sqlite3' if mode=='traversal' and info.filename=='payload/'+old else info.filename
                out.writestr(name, source.read(info))
            out.writestr('manifest.json', json.dumps(manifest))
        with pytest.raises(core.ValidationError):
            restore_snapshot(target, tmp_path/('bad_'+mode))
    assert not (tmp_path/'outside.sqlite3').exists()
    with pytest.raises(core.ValidationError, match='恢复尚未'):
        create_app(tmp_path/'bad_hash')


def test_failed_task_creation_releases_capacity_and_file_text_stays_local(client, monkeypatch):
    from backend.agent import provider_context
    pid = project(client)
    agent = client.app.state.agent
    original = agent.store.put
    def broken(kind, *args, **kwargs):
        if kind == 'agent':
            raise core.ValidationError('Controlled database write refusal')
        return original(kind, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(agent.store, 'put', broken)
        for _ in range(3):
            with pytest.raises(core.ValidationError, match='database write refusal'):
                agent.start(pid, Chat(message='核对天气'), background=False)
    assert agent.start(pid, Chat(message='核对天气'), background=False)['status']=='succeeded'
    raw = {'candidate': {'metadata': {'text':'Private PDF text', 'page':1},
                         'raw_text':'Private OCR', 'lines':[{'text':'Private source line'}]},
           'source_hash':'preserved-hash'}
    context = provider_context(raw)
    assert 'Private' not in json.dumps(context)
    assert context['source_hash']=='preserved-hash' and raw['candidate']['raw_text']=='Private OCR'


def test_maintenance_blocks_new_api_requests_and_releases(client):
    ops = client.app.state.operations
    with ops.snapshot(client.app.state.domain.store):
        assert client.get('/api/projects').status_code == 503
        assert client.get('/api/health').json()['maintenance'] is True
    assert client.get('/api/projects').status_code == 200


def test_orphan_recovery_is_explicit_and_does_not_reassign_owned_projects(client):
    from backend.schema import ProjectCreate
    store = client.app.state.domain.store
    owned = project(client)
    orphan = client.app.state.domain.create_project(ProjectCreate(name='Legacy unowned building',
        building={'use':'office','location':'Test','region':'TEST','area_m2':80.}))
    pid = orphan['project_id']
    assert client.get('/api/admin/database').json()['unowned_projects']==1
    assert client.get('/api/projects/'+pid).status_code==404
    url='/api/admin/database/recover-unowned'
    assert client.post(url,json={'current_password':'Wrong-password-value!'}).status_code==403
    body={'current_password':'Test-only-long-pass-2026'}
    assert client.post(url,json=body,headers={'X-CSRF-Token':''}).status_code==403
    with store.connect() as con:
        old_owner=con.execute('SELECT user_id FROM project_owners WHERE project_id=?',(owned,)).fetchone()[0]
    assert client.post(url,json=body).json()['recovered']==1
    assert client.get('/api/projects/'+pid).status_code==200
    with store.connect() as con:
        assert con.execute('SELECT user_id FROM project_owners WHERE project_id=?',(owned,)).fetchone()[0]==old_owner
    assert client.post(url,json=body).json()['recovered']==0
    assert store.get('project',pid)==orphan


def test_current_password_reauth_accepts_legacy_length_without_weak_new_passwords(client):
    from backend.auth import password_hash
    store=client.app.state.domain.store
    with store.connect() as con:
        row=con.execute('SELECT id,salt FROM users ORDER BY rowid LIMIT 1').fetchone()
        con.execute('UPDATE users SET password_hash=? WHERE id=?',(password_hash('7654321',row['salt']),row['id']))
    login=client.post('/api/auth/login',json={'username':'test_owner','password':'7654321'})
    assert login.status_code==200
    client.headers['X-CSRF-Token']=login.json()['csrf_token']
    # Current-password verification must accept existing credentials; new accounts still reject weak ones.
    assert client.post('/api/admin/database/backups',json={'current_password':'7654321'}).status_code==201
    assert client.post('/api/admin/users',json={'username':'weak_new','display_name':'Rejected',
        'current_password':'7654321','password':'7654321'}).status_code==422
