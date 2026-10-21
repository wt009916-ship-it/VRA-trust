"""Failure-path acceptance; protocol fixtures are not model-quality benchmarks."""
from types import SimpleNamespace

import ifcopenshell
import pytest

from backend import core, model_import, model_export
from backend.agent import Chat
from backend.model_schema import ImportOptions, ModelDraft
from test_api import create_project
from test_model_workbench import model_body
from test_weather import reference_path


def uploaded(client, pid, name, content):
    r = client.post(f'/api/projects/{pid}/files', files={'file': (name, content)})
    assert r.status_code == 201, r.text
    return r.json()


def test_partial_ifc_keeps_all_diagnostics_and_blocks_adoption(client, tmp_path):
    source = tmp_path/'partial.ifc'
    source.write_text(model_export.ifc(ModelDraft.model_validate(model_body()).model_dump()), encoding='utf-8')
    doc = ifcopenshell.open(str(source))
    doc.by_type('IfcSpace')[1].Representation = None
    doc.write(str(source))
    pid = create_project(client)['project_id']
    file = uploaded(client, pid, source.name, source.read_bytes())
    base = f'/api/projects/{pid}/imports'
    assert client.post(base, json={'file_id': file['file_id']}).status_code == 409
    record = client.get(base).json()[0]
    d = record['diagnostics']
    assert (d['total'], d['extracted'], d['blocked']) == (2, 1, 1)
    assert len(d['spaces']) == 2 and d['spaces'][1]['code'] == 'MISSING_BODY'
    assert record['source']['hash'] == core.sha(source)
    assert not record.get('candidate')
    assert client.post(base+'/'+record['import_id']+'/review', json=model_body()).status_code == 409
    report_path = base+'/'+record['import_id']+'/report.json'
    report = client.get(report_path).json()
    assert report['import']['diagnostics'] == d and report['current_source_check']['valid']
    other = create_project(client)['project_id']
    assert client.get(report_path.replace(pid, other)).status_code == 404
    _, original = client.app.state.domain.file_record(pid, file['file_id'])
    original.write_bytes(b'changed by test')
    stale = client.get(report_path).json()
    assert not stale['current_source_check']['valid']
    assert stale['import'] == report['import']
    client.cookies.clear()
    assert client.get(report_path).status_code == 401


def test_ifc_without_spaces_is_actionable_failure(tmp_path):
    path = tmp_path/'empty.ifc'
    ifcopenshell.file(schema='IFC4').write(str(path))
    with pytest.raises(model_import.ImportDiagnosticError) as error:
        model_import.ifc(path, ImportOptions(file_id='test'))
    assert error.value.diagnostics['total'] == 0
    assert error.value.diagnostics['actions']


def test_upload_capacity_and_failed_registration_leave_no_file(client, monkeypatch):
    pid = create_project(client)['project_id']
    domain = client.app.state.domain
    assert client.get('/api/health').json()['upload_policy']['max_file_bytes'] == 64*1024*1024
    original_put = domain.store.put
    def fail_registration(kind, *args, **kwargs):
        if kind == 'file':
            raise RuntimeError('database unavailable fixture')
        return original_put(kind, *args, **kwargs)
    monkeypatch.setattr(domain.store, 'put', fail_registration)
    with pytest.raises(RuntimeError):
        domain.add_file(pid, 'sample.ifc', b'test')
    assert not list((domain.store.root/'files').iterdir())
    monkeypatch.setattr('backend.domain.shutil.disk_usage', lambda _: SimpleNamespace(free=64*1024*1024))
    with pytest.raises(core.ValidationError, match='存储空间不足'):
        domain.add_file(pid, 'sample.ifc', b'test')
    assert not list((domain.store.root/'files').iterdir())


@pytest.mark.parametrize('response,state', [('[]', 'invalid'), ('{"tool_calls": []}', 'invalid'),
                                          (None, 'invalid'), ('timeout', 'unavailable')])
def test_provider_failure_keeps_real_weather_and_permissions(client, monkeypatch, response, state):
    pid = create_project(client)['project_id']
    f = uploaded(client, pid, 'Golden.epw', reference_path().read_bytes())
    r = client.post(f'/api/projects/{pid}/weather/epw', json={'file_id': f['file_id']})
    assert r.status_code == 201
    weather = r.json()
    agent = client.app.state.agent
    monkeypatch.setattr(agent.gateway, 'public', lambda: dict(enabled=True, key_configured=True, provider='fixture', model='fixture'))
    def complete(messages, tools):
        assert {t['function']['name'] for t in tools} == {'weather_summary', 'project_get'}
        if response == 'timeout':
            raise core.ValidationError('timeout fixture')
        return {'role': 'assistant', 'content': response}
    monkeypatch.setattr(agent.gateway, 'complete', complete)
    result = agent.start(pid, Chat(message='核对天气', mode='provider', task='weather'), background=False)
    assert result['status'] == 'partial' and result['tool_status'] == 'succeeded'
    assert result['explanation_status'] == state and result['llm_commentary'] is None
    actual = result['answer']['weather'][0]
    assert actual['annual'] == weather['annual'] and actual['source_hash'] == f['hash']
    assert actual['quality']['records'] == 8760
    assert actual['annual']['temperature_c'] == 9.761
    assert result['answer']['can_simulate'] is False
    assert agent.store.jobs(pid) == []
    _, path = agent.domain.file_record(pid, f['file_id'])
    path.write_bytes(b'tampered fixture')
    stale = agent.start(pid, Chat(message='天气', task='weather'), background=False)
    assert stale['answer']['weather'][0]['invalid']
    assert 'annual' not in stale['answer']['weather'][0]


def test_weather_task_cannot_escape_tool_scope_even_with_compute_checked(client, monkeypatch):
    pid = create_project(client)['project_id']
    agent = client.app.state.agent
    monkeypatch.setattr(agent.gateway, 'public', lambda: dict(enabled=True, key_configured=True, provider='fixture', model='fixture'))
    monkeypatch.setattr(agent.gateway, 'complete', lambda *args: {'role': 'assistant', 'content': None,
        'tool_calls': [{'id': 'x', 'function': {'name': 'simulation_create', 'arguments': '{}'}}]})
    result = agent.start(pid, Chat(message='读取天气', task='weather', mode='provider', allow_compute=True), background=False)
    assert result['status'] == 'partial'
    assert '未开放' in result['explanation_error']
    assert not any(e['tool'] == 'simulation_create' for e in result['events'])
    assert agent.store.jobs(pid) == []
