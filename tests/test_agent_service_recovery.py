"""Fault-injected transport + real calculator/store. Not LLM intelligence evidence."""
import copy
import json
from fractions import Fraction

import httpx
import pytest

from backend import core
from backend.agent import Chat
from backend.local_model import LocalModelSettings
from test_api import create_project
from test_agent_calculations import plan, tool
from test_agent_batch_tools import claim


def configure(client, monkeypatch, mode):
    agent = client.app.state.agent
    if mode == 'local_model':
        monkeypatch.setenv('VRA_LOCAL_MODEL_TOKEN', 'isolated-recovery-test-token-only')
        gateway = agent.local_model
        gateway.save(LocalModelSettings(enabled=True))
    else:
        monkeypatch.setenv('DEEPSEEK_API_KEY', 'isolated-recovery-test-key-only')
        gateway = agent.gateway
        core.write_json(gateway.path, {'enabled': True, 'model': 'deepseek-flash'})
    return agent, gateway


def workflow(client, monkeypatch, *, mode='local_model', failures=(2,), status=503,
             headers=None, error=None, on_wait=None):
    agent, gateway = configure(client, monkeypatch, mode)
    pid = create_project(client)['project_id']
    seen = []
    successes = []
    waits = []
    def serve(request):
        seen.append(json.loads(request.content))
        if len(seen) in failures:
            if error:
                raise error('secret body must not escape', request=request)
            return httpx.Response(status, headers=headers or {}, text='private upstream error')
        if not successes:
            response = tool('calculation_prepare', {'plan_keys': ['wall']})
        else:
            response = claim(agent.store.list('thermal', pid)[0])
        successes.append(copy.deepcopy(response))
        return httpx.Response(200, json={'model': gateway.public()['model'],
            'choices': [{'finish_reason': 'tool_calls', 'message': response}]})
    original = gateway.complete
    monkeypatch.setattr(gateway, 'complete', lambda messages, tools, **response_options: original(messages, tools, transport=httpx.MockTransport(serve), **response_options))
    def wait(seconds):
        waits.append(seconds)
        return bool(on_wait(agent, gateway, pid)) if on_wait else False
    # Tests only remove real backoff time; production uses the cancel Event.
    monkeypatch.setattr(agent.domain.stop, 'wait', wait)
    task = agent.start(pid, Chat(message='Execute the declared wall and deliver its thermal result',
        mode=mode, allow_compute=True, calculation_plans=[plan('thermal', 'wall')]), background=False)
    return agent, pid, task, seen, successes, waits


@pytest.mark.parametrize('mode', ['local_model', 'provider'])
@pytest.mark.parametrize('failures', [(1,), (2,), (2, 3)])
def test_inference_outage_continues_complete_task_without_repeating_calculation(client, monkeypatch, mode, failures):
    agent, pid, task, seen, successes, waits = workflow(client, monkeypatch, mode=mode, failures=failures)
    assert task['status'] == 'succeeded', task.get('error')
    assert task['calculation_progress'][0]['state'] == 'verified'
    assert task['answer']['can_recommend'] is False
    assert len(agent.store.list('thermal', pid)) == 1
    writes = [e for e in task['events'] if e['tool'] == 'calculation_execute']
    assert len(writes) == 1 and writes[0]['status'] == 'succeeded'
    assert len(seen) == 2 + len(failures) and len(successes) == 2
    assert len(task['events']) <= 15
    assert task['provider_recovery_attempts'] == len(failures)
    assert len(waits) == len(failures)
    failed = [e for e in task['events'] if e['tool'] == 'llm.request' and e['status'] == 'failed']
    assert len(failed) == len(failures)
    assert all(e['provider_recovery']['tools_replayed'] is False for e in failed)
    actual = agent.store.list('thermal', pid)[0]['result']['total_resistance_m2k_w']
    expected = Fraction(17, 100) + Fraction(130, 1000) / Fraction(65, 100) + Fraction(6, 100) / (Fraction(30, 1000) * Fraction(5, 4))
    assert actual == pytest.approx(float(expected))
    assert 'private upstream error' not in json.dumps(task)


@pytest.mark.parametrize('error', [httpx.ConnectTimeout, httpx.ReadError, httpx.RemoteProtocolError])
def test_incomplete_transport_never_executes_partial_response(client, monkeypatch, error):
    agent, pid, task, seen, _, _ = workflow(client, monkeypatch, error=error)
    assert task['status'] == 'succeeded' and len(seen) == 3
    assert len(agent.store.list('thermal', pid)) == 1
    assert 'secret body' not in json.dumps(task)


@pytest.mark.parametrize('mode', ['provider', 'local_model'])
@pytest.mark.parametrize('status', [302, 400, 401, 403, 404, 500])
def test_permanent_http_failure_is_not_retried(client, monkeypatch, mode, status):
    agent, pid, task, seen, _, waits = workflow(client, monkeypatch, mode=mode, status=status)
    assert task['status'] == 'failed' and len(seen) == 2 and not waits
    assert task['answer'] is None and len(agent.store.list('thermal', pid)) == 1


@pytest.mark.parametrize('hint', ['6', '999999999999999999', '-1', 'not-a-date'])
def test_retry_after_outside_budget_is_not_ignored_or_shortened(client, monkeypatch, hint):
    _, _, task, seen, _, waits = workflow(client, monkeypatch, status=429, headers={'Retry-After': hint})
    assert task['status'] == 'failed' and len(seen) == 2 and not waits
    event = next(e for e in task['events'] if e.get('provider_recovery'))
    assert event['provider_recovery']['reason'] == 'server_delay_exceeds_budget'


def test_persistent_outage_exhausts_two_retries_without_new_calculation(client, monkeypatch):
    agent, pid, task, seen, _, waits = workflow(client, monkeypatch, failures=(2, 3, 4, 5))
    assert task['status'] == 'failed' and len(seen) == 4 and waits == [1, 2]
    assert task['answer'] is None and len(agent.store.list('thermal', pid)) == 1
    assert task['events'][-1]['provider_recovery']['reason'] == 'retry_limit'


def test_shutdown_during_backoff_stops_before_next_model_request(client, monkeypatch):
    _, _, task, seen, _, waits = workflow(client, monkeypatch, on_wait=lambda *_: True)
    assert task['status'] == 'failed' and len(seen) == 2 and len(waits) == 1
    assert task['events'][-1]['provider_recovery']['reason'] == 'cancelled'


def test_model_configuration_change_during_recovery_refuses_new_destination(client, monkeypatch):
    def change(agent, gateway, pid):
        gateway.save(LocalModelSettings(enabled=True, port=18774))
    _, _, task, seen, _, _ = workflow(client, monkeypatch, on_wait=change)
    assert task['status'] == 'failed' and len(seen) == 2
    assert 'configuration changed' in task['error']


def test_changed_source_during_outage_cannot_restore_old_values(client, monkeypatch):
    def change(agent, gateway, pid):
        project = agent.store.get('project', pid)
        project['building']['area_m2'] += 1
        agent.store.put('project', project, project['revision'])
    agent, pid, task, _, _, _ = workflow(client, monkeypatch, on_wait=change)
    assert len(agent.store.list('thermal', pid)) == 1
    assert task['answer'] is None or not any(a.get('verified') for a in task['answer'].get('artifacts', []))
    assert task['calculation_progress'][0]['state'] != 'verified'


def test_budget_and_http_date_delay_policy():
    from backend.model_recovery import ModelServiceUnavailable, decision, retry_delay
    error = ModelServiceUnavailable('http_503')
    assert decision(error, 0, 4, 5, 1)['reason'] == 'response_budget'
    assert decision(error, 0, 1, 14, 1)['reason'] == 'event_budget'
    assert retry_delay('Sun, 06 Nov 1994 08:49:37 GMT', now=784111775) == 2
    assert decision(ModelServiceUnavailable('http_429', '3'), 0, 0, 1, 1)['delay_seconds'] == 3
