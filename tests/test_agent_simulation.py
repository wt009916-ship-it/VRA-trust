"""Transport/authorization fixtures, not evidence of real model reasoning or native physics."""
from copy import deepcopy
import json

import pytest
from pydantic import ValidationError

from backend import agent_simulation as sizing, core
from backend.agent import Chat, ToolArgs
from test_api import create_project


def run_view(project_id='project_fixture'):
    # Deliberately large source receipt and distinctive rows expose accidental truncation/repetition.
    day = {'name': 'synthetic day', 'month': 7, 'day': 21,
           'locator': {'object': 'SizingPeriod:DesignDay', 'object_index': 3},
           'raw_fields': ['transport-only fixture' * 450]}
    receipt = {'status': 'calculated_model_scenario', 'policy_version': 'fixture',
        'parser_sha256': 'a' * 64, 'model_sha256': 'b' * 64, 'sql_sha256': 'c' * 64,
        'weather_sha256': 'd' * 64, 'site_comparison': 'declared_site_differs_from_weather',
        'site_applicability': 'requires_professional_review', 'tabular_crosscheck': 'matched_W_cells',
        'building_coincident_peak_W': None, 'limitations': ['Synthetic transport fixture, not native simulation'],
        'basis': {'design_days': [day]},
        'rows': [{'zone_name': f'zone {i}', 'calculated_sensible_load_W': 1300 + i,
                  'user_adjusted_sensible_load_W': 1400 + i, 'multipliers_already_applied': True,
                  'peak': {'design_day': 'SYNTHETIC DAY', 'date_time': f'7/21 {i:02}:00:00'},
                  'locator': {'table': 'ZoneSizes', 'row_id': i + 1, 'unit': 'W'}} for i in range(11)]}
    return {'run_id': 'run_' + 'a' * 32, 'project_id': project_id, 'status': 'succeeded',
            'metrics': {'annual_energy_kwh': 1234, 'zone_design_loads': receipt},
            'weather_quality': {'fields': {'untransmitted': 'weather-statistic' * 180}, 'status': 'valid',
                                'conditions': ['Do not conceal weather warning']}}


@pytest.mark.parametrize('tool', ['simulation_result', 'simulation_status', 'report_generate', 'certificate_generate', 'scheme_compare'])
def test_known_envelopes_preserve_raw_audit_and_mark_unread_details(tool):
    view = run_view()
    source = {'run': view} if tool in {'report_generate', 'certificate_generate'} else {'results': [view]} if tool == 'scheme_compare' else view
    original = deepcopy(source)
    projected = sizing.model_result(tool, source)
    result = projected.get('run', projected.get('results', [projected])[0])
    summary = result['metrics']['zone_design_loads']
    assert source == original and result['metrics']['annual_energy_kwh'] == 1234
    assert summary['row_count'] == 11 and summary['rows'] is None and summary['details_delivered'] is False
    assert summary['receipt_hash'] == core.hash_json(view['metrics']['zone_design_loads'])
    assert summary['detail_request']['arguments']['run_id'] == view['run_id']
    assert result['weather_quality'] == view['weather_quality']
    assert summary['building_coincident_peak_W'] is None


def test_pages_cover_each_original_row_once_with_bound_source_and_day():
    view = run_view(); original = deepcopy(view)
    receipt = view['metrics']['zone_design_loads']; digest = core.hash_json(receipt)
    found = []; offset = 0
    while offset is not None:
        part = sizing.page(view, offset, digest)
        found.extend(part['rows'])
        assert 1 <= len(part['rows']) <= 5 and part['source']['sql_sha256'] == receipt['sql_sha256']
        assert part['entire_receipt_delivered'] is False and part['building_coincident_peak_W'] is None
        assert part['design_days'][0]['name'] == 'synthetic day' and 'raw_fields' not in part['design_days'][0]
        assert sizing.model_result('simulation_result', part) == part
        offset = part['next_offset']
    assert found == receipt['rows'] and view == original
    last = sizing.page(view, 10, digest)
    assert last['next_offset'] is None and not last['entire_receipt_delivered']


@pytest.mark.parametrize('state', ['stale', 'failed', 'running'])
def test_invalid_run_never_releases_even_present_cached_loads(state):
    view = run_view(); view['status'] = state
    with pytest.raises(core.ValidationError, match='no valid sizing'):
        sizing.page(view, 0, core.hash_json(view['metrics']['zone_design_loads']))


def test_unavailable_changed_and_out_of_bounds_pages_are_not_empty_success():
    view = run_view(); receipt = view['metrics']['zone_design_loads']; digest = core.hash_json(receipt)
    with pytest.raises(core.ValidationError, match='exceeds'):
        sizing.page(view, 11, digest)
    receipt['rows'][0]['calculated_sensible_load_W'] += 1
    with pytest.raises(core.ValidationError, match='changed'):
        sizing.page(view, 0, digest)
    receipt.update(status='unavailable', rows=None, reason='Missing native table')
    assert 'detail_request' not in sizing.summary(receipt, view['run_id'])
    with pytest.raises(core.ValidationError, match='unavailable'):
        sizing.page(view, 0, core.hash_json(receipt))


@pytest.mark.parametrize('patch', [{'zone_offset': -1}, {'zone_offset': 10000}, {'zone_offset': True},
    {'zone_offset': '0'}, {'zone_offset': .5}, {'zone_hash': None}, {'zone_hash': '../file'}, {'run_id': None}])
def test_paging_arguments_are_strict_and_cannot_be_paths(patch):
    with pytest.raises(ValidationError):
        ToolArgs.model_validate({'run_id': 'run_' + 'a' * 32, 'zone_offset': 0, 'zone_hash': 'b' * 64, **patch})


def test_page_calls_check_project_ownership_before_read(client, monkeypatch):
    agent = client.app.state.agent; pid = create_project(client)['project_id']
    monkeypatch.setattr(agent.store, 'job', lambda _: {'project_id': 'foreign'})
    def forbidden(_):
        pytest.fail('Cross-project source read must never occur')
    monkeypatch.setattr(agent.domain, 'view', forbidden)
    with pytest.raises(core.ValidationError, match='Cross-project'):
        agent.call(pid, 'simulation_result', {'run_id': 'run_' + 'a' * 32, 'zone_offset': 0, 'zone_hash': 'b' * 64}, False)


def test_scripted_list_then_three_pages_stays_in_budget_and_keeps_full_audit(client, monkeypatch):
    agent = client.app.state.agent; pid = create_project(client)['project_id']; view = run_view(pid)
    receipt = view['metrics']['zone_design_loads']; digest = core.hash_json(receipt)
    views = [dict(view, run_id='run_' + f'{i:032x}') for i in range(6)]
    assert len(json.dumps(views, ensure_ascii=False)) > 64000
    monkeypatch.setattr(agent.store, 'jobs', lambda _: [{'run_id': v['run_id']} for v in views])
    monkeypatch.setattr(agent.store, 'job', lambda _: {'project_id': pid})
    monkeypatch.setattr(agent.domain, 'view', lambda rid: next(v for v in views if v['run_id'] == rid))
    monkeypatch.setattr(agent.gateway, 'public', lambda: {'enabled': True, 'key_configured': True})
    steps = iter([{}, *[{'run_id': views[0]['run_id'], 'zone_offset': offset, 'zone_hash': digest} for offset in (0, 5, 10)], None])
    payloads = []
    def complete(messages, tools):
        payloads.append(deepcopy(messages))
        assert len(json.dumps(messages, ensure_ascii=False)) < 64000
        args = next(steps)
        if args is None:
            return {'role': 'assistant', 'content': 'Protocol fixture only; not a real LLM completion.'}
        return {'role': 'assistant', 'tool_calls': [{'id': f'call{len(payloads)}', 'type': 'function',
            'function': {'name': 'simulation_result', 'arguments': json.dumps(args)}}]}
    monkeypatch.setattr(agent.gateway, 'complete', complete)
    task = agent.start(pid, Chat(message='Inspect sizing pages', mode='provider'), background=False)
    assert task['status'] == 'succeeded', task['error']
    assert task['answer']['task_completion'] == 'not_assessed'  # transport success is not professional delivery
    events = [e for e in task['events'] if e['tool'] == 'simulation_result']
    assert events[0]['result'] == views and events[0]['result_hash'] == core.hash_json(views)
    assert [r for e in events[1:] for r in e['result']['rows']] == receipt['rows']
    sent = json.loads(next(m['content'] for m in payloads[1] if m['role'] == 'tool'))
    assert sent[0]['weather_projection']['field_statistics_delivered'] is False
    assert sent[0]['weather_quality']['conditions'] == view['weather_quality']['conditions']
    assert all(v['metrics']['zone_design_loads']['rows'] is None for v in sent)


def test_initial_inspection_is_projected_and_current_result_rechecked(client, monkeypatch):
    agent = client.app.state.agent; pid = create_project(client)['project_id']; view = run_view(pid)
    monkeypatch.setattr(agent.store, 'jobs', lambda _: [{'run_id': view['run_id']}])
    monkeypatch.setattr(agent.store, 'job', lambda _: {'project_id': pid})
    monkeypatch.setattr(agent.domain, 'view', lambda _: deepcopy(view))
    monkeypatch.setattr(agent.gateway, 'public', lambda: {'enabled': True, 'key_configured': True})
    def complete(messages, tools):
        assert all(t['function']['name'] != 'professional_read_many' for t in tools)
        initial = json.loads(messages[4]['content'].split('：', 1)[1])
        run = next(v for v in initial if isinstance(v, dict) and v.get('run_id'))
        assert run['metrics']['zone_design_loads']['details_delivered'] is False
        return {'role': 'assistant', 'content': 'Protocol fixture summary'}
    monkeypatch.setattr(agent.gateway, 'complete', complete)
    task = agent.start(pid, Chat(message='Read current run', mode='provider', objective='inspect_results'), background=False)
    assert task['status'] == 'succeeded', task['error']
    events = [e for e in task['events'] if e['tool'] == 'simulation_result']
    assert len(events) == 2 and all(e['result'] == view for e in events)


@pytest.mark.parametrize('objective', ['inspect_results', 'inspect_evidence', 'inspect_thermal'])
def test_every_offered_schema_has_nonempty_enums_in_inspection_modes(client, monkeypatch, objective):
    agent = client.app.state.agent; pid = create_project(client)['project_id']
    monkeypatch.setattr(agent.gateway, 'public', lambda: {'enabled': True, 'key_configured': True})
    def inspect(node):
        if isinstance(node, dict):
            if 'enum' in node:
                assert node['enum'], 'llama.cpp rejects empty enum schemas before inference'
            for value in node.values(): inspect(value)
        elif isinstance(node, list):
            for value in node: inspect(value)
    def complete(messages, tools):
        inspect(tools)
        return {'role': 'assistant', 'content': 'Schema protocol fixture, no native or model claim'}
    monkeypatch.setattr(agent.gateway, 'complete', complete)
    task = agent.start(pid, Chat(message='Inspect current evidence', mode='provider', objective=objective), background=False)
    assert task['status'] == 'succeeded', task['error']
