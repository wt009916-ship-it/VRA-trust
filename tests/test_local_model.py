"""Protocol fault tests only. Real model evidence is recorded separately."""
import copy
import json

import httpx
import pytest

from backend import core
from backend.agent import Chat, ToolArgs, TOOL_FIELDS
from backend.local_model import LocalModelSettings
from test_api import create_project


TOKEN = 'isolated-test-token-not-a-real-service-key'


def configured(client, monkeypatch):
    monkeypatch.setenv('VRA_LOCAL_MODEL_TOKEN', TOKEN)
    gateway = client.app.state.agent.local_model
    gateway.save(LocalModelSettings(enabled=True))
    return gateway


def reply():
    return {'model': 'vra-qwen3-4b', 'choices': [{'finish_reason': 'stop',
            'message': {'role': 'assistant', 'content': '仅解释', 'reasoning_content': 'hidden'}}]}


def test_local_gateway_fixed_destination_and_minimal_response(client, monkeypatch):
    gateway = configured(client, monkeypatch)
    seen = []
    def serve(request):
        seen.append(request)
        return httpx.Response(200, json=reply())
    answer = gateway.complete([{'role': 'user', 'content': 'check'}], [], transport=httpx.MockTransport(serve))
    assert str(seen[0].url) == 'http://127.0.0.1:18773/v1/chat/completions'
    assert seen[0].headers['Authorization'] == 'Bearer ' + TOKEN
    assert json.loads(seen[0].content)['chat_template_kwargs'] == {'enable_thinking': False}
    assert answer == {'role': 'assistant', 'content': '仅解释'}
    assert TOKEN not in json.dumps(gateway.public()) + gateway.path.read_text()
    assert gateway.public()['connection_verified'] is False
    assert client.get('/api/health').json()['capabilities']['llm_tools'] is True
    assert client.get('/api/health').json()['capabilities']['llm_connection_verified'] is False


@pytest.mark.parametrize('body', [[], {}, {'choices': []}, {'model': 'wrong'},
    {'model': 'vra-qwen3-4b', 'choices': [None]},
    {'model': 'vra-qwen3-4b', 'choices': [{'finish_reason': 'length', 'message': {'tool_calls': []}}]}])
def test_malformed_and_truncated_responses_refuse(client, monkeypatch, body):
    gateway = configured(client, monkeypatch)
    with pytest.raises(core.ValidationError, match='响应不完整'):
        gateway.complete([], [], transport=httpx.MockTransport(lambda _: httpx.Response(200, json=body)))


@pytest.mark.parametrize('status', [302, 401, 500])
def test_error_bodies_and_redirects_not_exposed_or_followed(client, monkeypatch, status):
    gateway = configured(client, monkeypatch); seen = []
    def serve(request):
        seen.append(request)
        return httpx.Response(status, headers={'Location': 'https://example.invalid/'}, text=TOKEN)
    with pytest.raises(core.ValidationError) as error:
        gateway.complete([], [], transport=httpx.MockTransport(serve))
    assert len(seen) == 1 and TOKEN not in str(error.value)


def test_limits_and_missing_token_refuse_without_cloud_fallback(client, monkeypatch):
    gateway = configured(client, monkeypatch); seen = []
    def serve(request):
        seen.append(request)
        return httpx.Response(200, content=b'x' * (1024 * 1024 + 1))
    with pytest.raises(core.ValidationError):
        gateway.complete([], [], transport=httpx.MockTransport(serve))
    assert len(seen) == 1
    with pytest.raises(core.ValidationError):
        gateway.complete([{'role': 'user', 'content': 'x' * 200000}], [], transport=httpx.MockTransport(serve))
    assert len(seen) == 1
    monkeypatch.delenv('VRA_LOCAL_MODEL_TOKEN')
    with pytest.raises(core.ValidationError, match='尚未启用'):
        gateway.complete([], [], transport=httpx.MockTransport(serve))
    pid = create_project(client)['project_id']
    assert client.post(f'/api/projects/{pid}/agent/chat', json={'message': 'run', 'mode': 'local_model'}).status_code == 409
    assert client.app.state.agent.store.list('agent', pid) == []


@pytest.mark.parametrize('changes', [{'port': 80}, {'port': True}, {'port': '18773'}, {'port': 65536},
                                   {'model': '../escape'}, {'endpoint': 'https://outside.invalid'}])
def test_local_config_cannot_choose_remote_url_or_invalid_port(client, changes):
    assert client.put('/api/developer/local-model', json={'enabled': True, **changes}).status_code == 422


def test_local_configuration_requires_admin_and_csrf(client):
    assert client.get('/api/developer/local-model').status_code == 200
    csrf = client.headers.pop('X-CSRF-Token')
    assert client.put('/api/developer/local-model', json={'enabled': True}).status_code == 403
    client.headers['X-CSRF-Token'] = csrf
    session = client.post('/api/auth/register', json={'username': 'local_model_member', 'display_name': 'member',
                          'password': 'Isolated-member-pass-2026'}).json()
    client.headers['X-CSRF-Token'] = session['csrf_token']
    assert client.get('/api/developer/local-model').status_code == 403
    assert client.put('/api/developer/local-model', json={'enabled': True}).status_code == 403
    assert client.post('/api/developer/local-model/test').status_code == 403


def test_local_agent_uses_real_registry_and_preserves_authorization(client, monkeypatch):
    gateway = configured(client, monkeypatch); agent = client.app.state.agent
    pid = create_project(client)['project_id']
    calls = iter([
        {'role': 'assistant', 'tool_calls': [{'id': 't1', 'type': 'function', 'function': {'name': 'evidence_validate', 'arguments': '{}'}}]},
        {'role': 'assistant', 'content': '虚构已认证，不得进入正式指标'},
        {'role': 'assistant', 'tool_calls': [{'id': 't2', 'type': 'function', 'function': {'name': 'simulation_create', 'arguments': '{}'}}]},
    ])
    monkeypatch.setattr(gateway, 'complete', lambda messages, tools: next(calls))
    def no_cloud(*args, **kwargs):
        pytest.fail('Local model must never fall back to cloud')
    monkeypatch.setattr(agent.gateway, 'complete', no_cloud)
    result = agent.start(pid, Chat(message='check', mode='local_model', objective='inspect_evidence'), background=False)
    assert result['status'] == 'succeeded' and result['answer']['can_recommend'] is False
    assert result['answer']['execution_scope'] == 'bounded_local_model_tools'
    assert len([e for e in result['events'] if e['tool'] == 'evidence_validate']) == 2
    assert all(e['arguments']['provider'] == 'local_model' for e in result['events'] if e['tool'] == 'llm.request')
    refused = agent.start(pid, Chat(message='compute without permission', mode='local_model'), background=False)
    assert refused['status'] == 'failed' and '未授权' in refused['error']
    assert agent.store.jobs(pid) == []


def test_tool_schema_preserves_all_reachable_constraints_without_duplicate_defs(client):
    source = ToolArgs.model_json_schema(); agent = client.app.state.agent
    tools = agent.tools(); before = copy.deepcopy(tools)
    for tool in tools:
        name = tool['function']['name']; schema = tool['function']['parameters']
        assert schema['additionalProperties'] is False
        # Only field display titles are omitted; every constraint and reachable definition is unchanged.
        assert schema['properties'] == {k:{a:b for a,b in source['properties'][k].items() if a!='title'} for k in TOOL_FIELDS[name]}
        references = set()
        def walk(node):
            if isinstance(node, dict):
                if '$ref' in node:
                    key = node['$ref'].removeprefix('#/$defs/')
                    assert schema['$defs'][key] == source['$defs'][key]
                    if key not in references:
                        references.add(key); walk(schema['$defs'][key])
                for value in node.values(): walk(value)
            elif isinstance(node, list):
                for value in node: walk(value)
        walk(schema['properties'])
        assert set(schema.get('$defs', {})) == references
    assert len(json.dumps(tools, ensure_ascii=False)) < 20000
    assert agent.tools() == before


def test_date_tool_arguments_are_canonical_json_and_missing_runs_not_invented(client, monkeypatch):
    gateway = configured(client, monkeypatch); agent = client.app.state.agent
    pid = create_project(client)['project_id']
    replies = iter([
        {'role': 'assistant', 'tool_calls': [{'id': 'q1', 'type': 'function', 'function': {
            'name': 'standards_search', 'arguments': json.dumps({'standards_query': {'text': 'NONEXIST', 'as_of': '2026-01-01'}})}}]},
        {'role': 'assistant', 'content': 'No matching source'}])
    monkeypatch.setattr(gateway, 'complete', lambda messages, tools: next(replies))
    result = agent.start(pid, Chat(message='Query missing standard', mode='local_model'), background=False)
    assert result['status'] == 'succeeded'
    event = next(e for e in result['events'] if e['tool'] == 'standards_search')
    assert event['status'] == 'succeeded' and event['arguments']['standards_query']['as_of'] == '2026-01-01'
    assert agent.call(pid, 'simulation_list', {}, False) == []
    with pytest.raises(ValueError):
        ToolArgs(run_id=pid)
