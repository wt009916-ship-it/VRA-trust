import copy
import hashlib
import io
import json
import zipfile
from xml.etree import ElementTree as ET

from fastapi.testclient import TestClient

from backend.engineering_review import model_changes
from test_model_workbench import model_body, project, upload


def saved_snapshot(client):
    pid = project(client)
    body = model_body()
    body['rooms'][0]['conditioned'] = None
    body['rooms'][0]['storey_id'] = 'source_floor'
    body['rooms'][0]['storey_name'] = '<源楼层>'
    body['rooms'][0]['ifc_source'] = '3CzqQUTr1F2vH3uM7jN9iL'
    response = client.put(f'/api/projects/{pid}/model', json=body)
    assert response.status_code == 200, response.text
    url = f'/api/projects/{pid}/engineering-review'
    return pid, body, url, client.get(url).json()


def disposition(snapshot, finding, **extra):
    return {'snapshot_hash': snapshot['snapshot_hash'], 'finding_id': finding['finding_id'],
            'decision': 'needs_information', 'note': 'Controlled reviewer requests original source information.',
            'expected_revision': finding['review_revision'], **extra}


def test_assumptions_and_source_room_location_are_not_disguised_as_ready(client):
    pid, _, url, snap = saved_snapshot(client)
    finding = next(f for f in snap['findings'] if f['key'] == 'use:source_floor')
    assert finding['room_ids'] == ['R1']
    assert finding['ifc_global_ids'] == ['3CzqQUTr1F2vH3uM7jN9iL']
    assert snap['counts']['BLOCKER'] > 0
    assert snap['engineering_signature'] == 'UNSIGNED'
    before = client.get(f'/api/projects/{pid}/model/validate').json()
    rejected = client.post(url+'/dispositions', json=disposition(snap, finding, decision='accepted_scenario'))
    assert rejected.status_code == 409
    assumption = next(f for f in snap['findings'] if f['kind'] == 'ASSUMPTION')
    r = client.post(url+'/dispositions', json=disposition(snap, assumption, decision='accepted_scenario'))
    assert r.status_code == 201, r.text
    assert r.json()['actor'] == 'Test owner'
    collections = client.get('/api/admin/database').json()['collections']
    assert next(x['count'] for x in collections if x['id'] == 'reviews') == 1
    rows = client.get('/api/admin/database/collections/reviews?q=accepted_scenario').json()
    assert rows['total'] == 1 and rows['items'][0]['name'] == assumption['title']
    history = client.get('/api/admin/database/collections/reviews/'+r.json()['review_id']).json()['history']
    assert history[0]['snapshot_hash'] == snap['snapshot_hash']
    after = client.get(f'/api/projects/{pid}/model/validate').json()
    assert after['blockers'] == before['blockers'] and not after['can_publish']
    assert client.get(url).json()['snapshot_hash'] == snap['snapshot_hash']


def test_old_reviews_expire_and_conflicts_retain_history(client):
    pid, body, url, snap = saved_snapshot(client)
    finding = next(f for f in snap['findings'] if f['kind'] == 'ASSUMPTION')
    payload = disposition(snap, finding)
    assert client.post(url+'/dispositions', json=payload).status_code == 201
    assert client.post(url+'/dispositions', json=payload).status_code == 409
    body['expected_revision'] = 1
    body['rooms'][0]['name'] = 'Renamed room with stable source'
    r = client.put(f'/api/projects/{pid}/model', json=body)
    assert r.status_code == 200, r.text
    current = client.get(url).json()
    new = next(f for f in current['findings'] if f['finding_id'] == finding['finding_id'])
    assert new['review'] is None and new['prior_review_stale']
    assert new['review_revision'] == 1
    assert current['changes']['affected_room_ids'] == ['R1']
    assert current['changes']['categories']['display'] == 1
    assert client.post(url+'/dispositions', json=payload).status_code == 409
    assert client.post(url+'/dispositions', json=disposition(current, new)).status_code == 201
    records = client.get(url+'/findings/'+new['finding_id']+'/history').json()
    assert len(records) == 2 and records[0]['snapshot_hash'] == snap['snapshot_hash']


def test_source_tamper_invalidates_snapshot_even_without_model_revision(client):
    pid, _, url, snap = saved_snapshot(client)
    fid = upload(client, pid, 'review-source.csv', b'controlled original')
    source = client.app.state.domain.store.get('file', fid)
    model = client.app.state.modeling.get(pid)
    model['sources'] = [{k: source[k] for k in ('file_id', 'name', 'hash')}]
    client.app.state.domain.store.put('model', model, model['revision'])
    before = client.get(url).json()
    (client.app.state.domain.store.root/source['path']).write_bytes(b'tampered')
    after = client.get(url).json()
    assert before['snapshot_hash'] != after['snapshot_hash']
    assert any(f['key'] == 'source:'+fid and f['kind'] == 'BLOCKER' for f in after['findings'])
    assumption = next(f for f in before['findings'] if f['kind'] == 'ASSUMPTION')
    assert client.post(url+'/dispositions', json=disposition(before, assumption)).status_code == 409


def test_multiple_coverage_rows_share_one_unique_topic_without_losing_regions(client):
    pid, _, url, _ = saved_snapshot(client)
    fid = upload(client, pid, 'controlled-source.ifc', b'Controlled provenance fixture only')
    source = client.app.state.domain.store.get('file', fid)
    model = client.app.state.modeling.get(pid)
    model['sources'] = [{**{k: source[k] for k in ('file_id', 'name', 'hash')}, 'reconstruction_coverage': {'storeys': [
        {'storey': 'floorA', 'status': 'unbounded_ceiling_cell', 'area_m2': 2.},
        {'storey': 'floorA', 'status': 'candidate', 'excluded_subminimum_area_m2': .2}]}}]
    client.app.state.domain.store.put('model', model, model['revision'])
    snapshot = client.get(url).json()
    assert len({f['finding_id'] for f in snapshot['findings']}) == len(snapshot['findings'])
    coverage = [f for f in snapshot['findings'] if f['key'].startswith('coverage:')]
    assert len(coverage) == 1 and len(coverage[0]['basis']['coverage_rows']) == 2
    with zipfile.ZipFile(io.BytesIO(client.get(url+'/issues.bcfzip').content)) as archive:
        assert len(archive.namelist()) == len(set(archive.namelist()))


def test_rare_earth_material_registration_does_not_prove_measured_advantage(client):
    pid, _, url, before = saved_snapshot(client)
    r = client.post(f'/api/projects/{pid}/materials', json={'name': 'Controlled rare-earth candidate',
        'contains_rare_earth': True, 'responsible_person': 'Controlled registration only'})
    assert r.status_code == 201, r.text
    after = client.get(url).json()
    assert after['snapshot_hash'] != before['snapshot_hash']
    finding = next(f for f in after['findings'] if f['key'].startswith('material:'))
    assert finding['kind'] == 'EVIDENCE_GAP' and finding['basis']['contains_rare_earth']
    assert finding['basis']['validation_gaps']
    assert client.post(url+'/dispositions', json=disposition(after, finding, decision='accepted_scenario')).status_code == 409


def test_retired_evidence_source_is_not_a_current_blocker_unless_model_still_uses_it(client):
    pid, _, url, _ = saved_snapshot(client)
    fid = upload(client, pid, 'retired-bill.csv', b'Controlled retired source')
    r = client.post(f'/api/projects/{pid}/evidence', json={'type': 'bill', 'name': 'Retired bill', 'source_file': fid,
        'source_locator': 'Controlled obsolete source', 'authority': 'Test fixture', 'permission': 'Test',
        'acquisition_method': 'Controlled test file', 'responsible_person': 'Test reviewer', 'status': 'IMPORTED'})
    assert r.status_code == 201, r.text
    ev = r.json()
    r = client.patch(f'/api/projects/{pid}/evidence/'+ev['evidence_id'], json={'expected_revision': ev['revision'],
        'review_state': 'rejected', 'responsible_person': 'Test reviewer', 'review_note': 'Retired source, not applicable to current model'})
    assert r.status_code == 200, r.text
    source = client.app.state.domain.store.get('file', fid)
    (client.app.state.domain.store.root/source['path']).write_bytes(b'damaged retired file')
    snap = client.get(url).json()
    assert not any(f['key'] in {'source:'+fid, 'evidence-source:'+ev['evidence_id']} for f in snap['findings'])
    model = client.app.state.modeling.get(pid)
    model['sources'] = [{k: source[k] for k in ('file_id', 'name', 'hash')}]
    client.app.state.domain.store.put('model', model, model['revision'])
    snap = client.get(url).json()
    assert any(f['key'] == 'source:'+fid and f['kind'] == 'BLOCKER' for f in snap['findings'])


def test_review_permission_csrf_and_export_contents(client):
    pid, _, url, snap = saved_snapshot(client)
    app = client.app
    with TestClient(app) as other:
        r = other.post('/api/auth/register', json={'username': 'other_review_user', 'display_name': 'Other reviewer',
                                                'password': 'Controlled-review-password-2026'})
        assert r.status_code == 200
        other.headers['X-CSRF-Token'] = r.json()['csrf_token']
        for suffix in ['', '/report.html', '/issues.bcfzip', '/handoff.zip']:
            assert other.get(url+suffix).status_code == 404
        assert other.post(url+'/dispositions', json=disposition(snap, snap['findings'][0])).status_code == 404
    csrf = client.headers.pop('X-CSRF-Token')
    assert client.post(url+'/dispositions', json=disposition(snap, snap['findings'][0])).status_code == 403
    client.headers['X-CSRF-Token'] = csrf
    exported = client.get(url+'/handoff.zip')
    assert exported.status_code == 200
    with zipfile.ZipFile(io.BytesIO(exported.content)) as z:
        assert set(z.namelist()) == {'manifest.json', 'review.json', 'review.html', 'issues.bcfzip', 'comparison-inputs.json'}
        manifest = json.loads(z.read('manifest.json'))
        assert manifest['unsigned'] and not manifest['includes_source_originals']
        assert manifest['snapshot_hash'] == snap['snapshot_hash']
        for name, digest in manifest['files'].items():
            assert hashlib.sha256(z.read(name)).hexdigest() == digest
        markup = z.read('review.html').decode()
        assert '<源楼层>' not in markup and '&lt;源楼层&gt;' in markup
        with zipfile.ZipFile(io.BytesIO(z.read('issues.bcfzip'))) as bcf:
            assert ET.fromstring(bcf.read('bcf.version')).attrib['VersionId'] == '2.1'
            topics = [ET.fromstring(bcf.read(p)) for p in bcf.namelist() if p.endswith('/markup.bcf')]
            assert len(topics) == len(snap['findings'])
            assert all(t.find('Topic').attrib['TopicStatus'] == 'Open' for t in topics)
            assert any('3CzqQUTr1F2vH3uM7jN9iL' in t.findtext('Topic/Description') for t in topics)
            assert all(t.find('Viewpoints') is None for t in topics)


def test_whitespace_cannot_satisfy_review_note(client):
    _, _, url, snap = saved_snapshot(client)
    assert client.post(url+'/dispositions', json=disposition(snap, snap['findings'][0], note=' '*20)).status_code == 422


def test_comparison_contract_keeps_selected_evidence_role_and_revision(client, monkeypatch):
    pid, _, url, _ = saved_snapshot(client)
    selected = {'evidence_id': 'controlled_epw_evidence', 'revision': 3, 'source_file': 'controlled_file',
                'hash': 'a'*64, 'status': 'ASSUMED', 'review_state': 'confirmed', 'source_locator': 'Controlled selection contract'}
    monkeypatch.setattr(client.app.state.domain, 'gate', lambda _: {'can_simulate': False, 'blockers': [], 'selected_evidence': {'epw': selected}})
    contract = client.get(url+'/comparison-inputs.json').json()
    assert contract['registered_simulation_inputs'] == {'epw': selected}
    assert contract['room_ids'] == ['R1', 'R2']


def test_building_revision_invalidates_disposition_and_project_evidence_changes_are_visible(client):
    pid, _, url, snap = saved_snapshot(client)
    finding = next(f for f in snap['findings'] if f['kind'] == 'ASSUMPTION')
    assert client.post(url+'/dispositions', json=disposition(snap, finding)).status_code == 201
    project_record = client.app.state.domain.store.get('project', pid)
    project_record['building']['notes'] = 'New field information changes the project declaration'
    client.app.state.domain.store.put('project', project_record, project_record['revision'])
    updated = client.get(url).json()
    assert updated['snapshot_hash'] != snap['snapshot_hash']
    item = next(f for f in updated['findings'] if f['finding_id'] == finding['finding_id'])
    assert item['review'] is None and item['prior_review_stale']


def test_bcf_replaces_invalid_xml_control_characters_but_json_retains_original(client):
    _, _, url, snap = saved_snapshot(client)
    finding = next(f for f in snap['findings'] if f['kind'] == 'ASSUMPTION')
    note = 'Source note with invalid XML character: \x01 retained in JSON'
    assert client.post(url+'/dispositions', json=disposition(snap, finding, note=note)).status_code == 201
    with zipfile.ZipFile(io.BytesIO(client.get(url+'/handoff.zip').content)) as z:
        saved = json.loads(z.read('review.json'))
        assert next(f['review']['note'] for f in saved['findings'] if f['finding_id'] == finding['finding_id']) == note
        with zipfile.ZipFile(io.BytesIO(z.read('issues.bcfzip'))) as bcf:
            for name in bcf.namelist():
                ET.fromstring(bcf.read(name))


def test_read_token_can_export_but_cannot_record_disposition(client):
    pid, _, url, snap = saved_snapshot(client)
    r = client.post(f'/api/projects/{pid}/tokens', json={'name': 'Review export read-only', 'scopes': ['read'], 'days': 1})
    assert r.status_code == 201, r.text
    token = r.json()['token']
    headers = {'Authorization': 'Bearer '+token}
    assert client.get(url+'/handoff.zip', headers=headers).status_code == 200
    assert client.post(url+'/dispositions', json=disposition(snap, snap['findings'][0]), headers=headers).status_code == 403


def test_revision_diff_does_not_match_rooms_by_name_or_invent_partial_reuse():
    before = {**model_body(), 'revision': 1}
    after = copy.deepcopy(before)
    after['revision'] = 2
    after['rooms'][0]['id'] = 'NewSourceIdentity'
    after['thermal']['heating_c'] = 21
    value = model_changes(before, after)
    assert value['categories']['space_added'] == value['categories']['space_removed'] == 1
    assert value['categories']['thermal'] == 1
    heating = next(c for c in value['changes'] if c['category'] == 'thermal')
    assert heating['field'] == 'thermal.heating_c' and heating['before'] == 20 and heating['after'] == 21
    assert value['affected_room_ids'] == ['NewSourceIdentity', 'R1']


def test_equipment_parameter_diff_names_actual_zone_and_capacity():
    a = {**model_body(), 'revision': 1, 'equipment': [{'zone_id': 'R2', 'cooling_capacity_w': 5000.}]}
    b = copy.deepcopy(a)
    b.update(revision=2)
    b['equipment'][0]['cooling_capacity_w'] = 6000.
    changes = model_changes(a, b)['changes']
    assert changes == [{'category': 'equipment', 'field': 'equipment[R2].cooling_capacity_w',
                        'room_id': 'R2', 'before': 5000., 'after': 6000.}]
