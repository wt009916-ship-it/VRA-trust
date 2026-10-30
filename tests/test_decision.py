"""Contract and decision logic tests; synthetic metrics are not physical validation."""
import copy

import pytest
from pydantic import ValidationError

from backend import core
from backend.agent import Chat
from backend.decision import COMFORT, Constraints, Option, StudyCreate, assess, material_catalog, replace_material
from backend.materials import MaterialCard
from test_api import create_project


def source(client, pid, *, confirmed=True, status='ASSUMED'):
    ev = client.post(f'/api/projects/{pid}/evidence', json={
        'type': 'assumption', 'name': 'Explicit unit-test parameter assumptions',
        'source_locator': 'Synthetic test record', 'authority': 'Automated test', 'permission': 'Test only',
        'acquisition_method': 'Explicit synthetic scenario', 'responsible_person': 'Test', 'status': status}).json()
    if confirmed:
        ev = client.patch(f'/api/projects/{pid}/evidence/{ev["evidence_id"]}', json={
            'expected_revision': ev['revision'], 'review_state': 'confirmed',
            'responsible_person': 'Test', 'review_note': 'Synthetic assumptions only; not measured'}).json()
    return ev


def card_body(eid):
    return {'name': 'Synthetic insulation', 'conductivity_w_mk': .04, 'density_kg_m3': 30,
            'specific_heat_j_kgk': 1000, 'thermal_evidence_id': eid, 'source_locator': 'Test row 1',
            'test_conditions': 'Declared synthetic dry scenario', 'applicability': 'Reference opaque layer only',
            'review_state': 'confirmed', 'responsible_person': 'Test', 'review_note': 'Checked against the declared test assumptions'}


def test_draft_material_and_diagnosis_has_actionable_gaps(client):
    pid = create_project(client)['project_id']
    card = client.post(f'/api/projects/{pid}/materials', json={'name': 'Awaiting test', 'responsible_person': 'Test'}).json()
    assert card['can_simulate'] is False and card['source_nature'] == 'MISSING'
    diagnosis = client.get(f'/api/projects/{pid}/diagnosis').json()
    assert diagnosis['can_simulate'] is False
    assert any(t['task_key'] == 'material:' + card['material_id'] for t in diagnosis['tasks'])
    assert diagnosis['tasks'][0]['priority'] == 1
    assert all(t['action'] and t['target_view'] for t in diagnosis['tasks'])


def test_material_needs_reviewed_source_and_preserves_assumption(client):
    pid = create_project(client)['project_id']
    ev = source(client, pid, confirmed=False)
    path = f'/api/projects/{pid}/materials'
    assert client.post(path, json=card_body(ev['evidence_id'])).status_code == 409
    ev = source(client, pid)
    response = client.post(path, json=card_body(ev['evidence_id']))
    assert response.status_code == 201, response.text
    card = response.json()
    assert card['can_simulate'] and card['source_nature'] == 'ASSUMED'
    assert card['performance_claim_verified'] is False
    assert 'thermal_evidence_id_not_measured' in card['validation_gaps']


def test_material_source_revision_invalidates_without_rewriting_history(client):
    pid = create_project(client)['project_id']
    ev = source(client, pid)
    path = f'/api/projects/{pid}/materials'
    original = client.post(path, json=card_body(ev['evidence_id'])).json()
    client.patch(f'/api/projects/{pid}/evidence/{ev["evidence_id"]}', json={
        'expected_revision': ev['revision'], 'review_state': 'pending',
        'responsible_person': 'Test', 'review_note': 'Withdraw the parameter confirmation'})
    changed = client.get(path).json()[0]
    assert changed['status'] == 'STALE' and not changed['can_simulate']
    history = client.get(path + '/' + original['material_id'] + '/history').json()
    assert len(history) == 1 and history[0]['evidence_snapshot'] == original['evidence_snapshot']


def test_material_revision_and_project_isolation(client):
    pid = create_project(client)['project_id']
    other = create_project(client)['project_id']
    ev = source(client, pid)
    assert client.post(f'/api/projects/{other}/materials', json=card_body(ev['evidence_id'])).status_code == 409
    path = f'/api/projects/{pid}/materials'
    card = client.post(path, json=card_body(ev['evidence_id'])).json()
    update = {**card_body(ev['evidence_id']), 'expected_revision': 1, 'conductivity_w_mk': .05}
    assert client.put(path + '/' + card['material_id'], json=update).status_code == 200
    assert client.put(path + '/' + card['material_id'], json=update).status_code == 409
    assert client.get(f'/api/projects/{other}/materials/{card["material_id"]}/history').status_code == 409


@pytest.mark.parametrize('key,value', [('conductivity_w_mk', 0), ('density_kg_m3', -1), ('specific_heat_j_kgk', 50), ('density_kg_m3', 'NaN'), ('conductivity_w_mk', True)])
def test_material_units_ranges_and_nonfinite(key, value):
    with pytest.raises(ValidationError):
        MaterialCard.model_validate({**card_body('evidence_' + 'a' * 32), key: value})


def test_model_mutation_and_explicit_surface_mapping():
    model = 'Material,Layer,Rough,.1,.04,30,1000,.9,.7,.7; Material,Other,Smooth,.2,.2,900,1200; Construction,Wall,Layer,Other; BuildingSurface:Detailed,North,Wall,Wall,ZoneA,Outdoors;'
    catalog = material_catalog(model)
    assert catalog[0]['supported'] and catalog[0]['surfaces'][0]['name'] == 'North'
    changed, diff = replace_material(model, 'layer', card_body('x'), .08)
    from backend.robustness import objects
    before, after = objects(model), objects(changed)
    assert after[0][3:7] == ['0.08', '0.04', '30', '1000']
    assert before[0][:3] == after[0][:3] and before[0][7:] == after[0][7:]
    assert before[1:] == after[1:] and diff['object'] == 'layer'
    assert material_catalog(model + 'MaterialProperty:PhaseChange,Layer,0;')[0]['supported'] is False
    with pytest.raises(core.ValidationError):
        replace_material(model + 'Material,Layer,Rough,.1,.1,30,1000;', 'Layer', card_body('x'), .1)


def point(name, energy, cost, cooling=20, status='succeeded'):
    return {'option_id': name, 'name': name, 'status': status, 'cost_cny': cost,
            'metrics': {'annual_energy_kwh': energy, 'energy_by_carrier_kwh': {'Electricity': energy},
                        'comfort_hours': {COMFORT['cooling_unmet_h']: cooling, COMFORT['heating_unmet_h']: 10}} if status == 'succeeded' else None}


def assessment(points, **limits):
    return assess(points, 100, ['energy_kwh', 'cost_cny'], Constraints(**limits).model_dump(), core.get_profile('none'), 'US-CO')


def test_constraints_and_pareto_distinguish_energy_from_cost():
    value = assessment([point('baseline', 100, 0), point('A', 80, 10), point('B', 70, 20), point('C', 90, 15)])
    assert value['pareto_option_ids'] == ['baseline', 'A', 'B']
    assert value['rows'][3]['dominated_by'] == ['A']
    assert value['rows'][1]['energy_saving_pct'] == 20
    capped = assessment([point('baseline', 100, 0), point('A', 80, 10), point('B', 70, 20)], max_cost_cny=15, min_energy_saving_pct=10)
    assert capped['pareto_option_ids'] == ['A']
    assert capped['rows'][0]['status'] == capped['rows'][2]['status'] == 'EXCLUDED'


def test_missing_cost_and_comfort_are_unknown_not_zero_or_winners():
    absent = point('A', 60, None)
    incomplete = point('B', 70, 10)
    incomplete['metrics']['comfort_hours'] = {}
    value = assessment([absent, incomplete, point('C', 30, 2, status='failed')], max_cooling_unmet_h=30)
    assert value['pareto_option_ids'] == []
    assert [r['status'] for r in value['rows']] == ['INCOMPLETE', 'INCOMPLETE', 'FAILED']
    assert 'cooling_unmet_h' in value['rows'][1]['missing']
    assert value['rows'][0]['values']['cost_cny'] is None


def test_ties_remain_candidates_and_comfort_constraints_are_separate():
    value = assessment([point('A', 80, 10), point('B', 80.005, 10)], max_heating_unmet_h=5)
    assert value['pareto_option_ids'] == []
    assert value['rows'][0]['violations'][0]['actual'] == 10
    tied = assessment([point('A', 80, 10), point('B', 80.005, 10)])
    assert tied['pareto_option_ids'] == ['A', 'B']


def test_study_plan_rejects_unattributed_prices_and_duplicate_options():
    with pytest.raises(ValidationError):
        Option(option_id='A', name='A', material_id='x', thickness_m=.1, cost_cny=20)
    option = {'option_id': 'A', 'name': 'A', 'material_id': 'x', 'thickness_m': .1}
    with pytest.raises(ValidationError):
        StudyCreate(source_run_id='r', target_material='Layer', options=[option, option], budget=2, basis='Declared test')


def test_decision_routes_require_login_csrf_and_ownership(client):
    pid = create_project(client)['project_id']
    base = f'/api/projects/{pid}'
    csrf = client.headers.pop('X-CSRF-Token')
    assert client.post(base + '/materials', json={'name': 'A', 'responsible_person': 'B'}).status_code == 403
    client.headers['X-CSRF-Token'] = csrf
    login = client.post('/api/auth/register', json={'username': 'other_user', 'display_name': 'Other', 'password': 'Other-test-password!'}).json()
    client.headers['X-CSRF-Token'] = login['csrf_token']
    for route in ['/diagnosis', '/materials', '/studies']:
        assert client.get(base + route).status_code == 404
    client.cookies.clear()
    assert client.get(base + '/diagnosis').status_code == 401


def test_local_assistant_returns_real_diagnosis_and_enforces_plan_permission(client):
    pid = create_project(client)['project_id']
    agent = client.app.state.agent
    result = agent.start(pid, Chat(message='分析材料和补证优先级'), background=False)
    assert result['status'] == 'succeeded'
    assert result['answer']['diagnosis']['tasks']
    assert 'project_diagnose' in result['answer']['basis']
    assert agent.call(pid, 'material_study_create', {}, False)['status'] == 'ACTION_NOT_AUTHORIZED'


def test_provider_cannot_invent_material_study_plan(client, monkeypatch):
    pid = create_project(client)['project_id']
    agent = client.app.state.agent
    monkeypatch.setattr(agent.gateway, 'public', lambda: {'enabled': True, 'key_configured': True})
    monkeypatch.setattr(agent.gateway, 'complete', lambda *args: {'role': 'assistant', 'content': None,
        'tool_calls': [{'id': 'invented', 'function': {'name': 'material_study_create', 'arguments': '{"study":{}}'}}]})
    result = agent.start(pid, Chat(message='帮我找最优方案', mode='provider', allow_compute=True), background=False)
    assert result['status'] == 'failed'
    assert '用户提交' in result['error']
    assert client.get(f'/api/projects/{pid}/studies').json() == []


def test_cost_factor_assessment_does_not_modify_source_metrics():
    points = [point('A', 80, 10), point('B', 70, 20)]
    snapshot = copy.deepcopy(points)
    value = assess(points, 100, ['carbon_kg'], Constraints().model_dump(), {
        'profile_id': 'test', 'region': '*', 'scenario': True,
        'factors': {'Electricity': {'value': .5, 'unit': 'kgCO2/kWh', 'source': 'explicit unit test', 'factor_id': 'test'}}}, 'US-CO')
    assert value['rows'][0]['values']['carbon_kg'] == 40
    assert value['pareto_option_ids'] == ['B'] and points == snapshot


def test_new_failed_study_does_not_fall_back_to_older_candidate_set(client, monkeypatch):
    pid = create_project(client)['project_id']
    decisions = client.app.state.decisions
    for sid, status in [('study_' + 'a' * 32, 'succeeded'), ('study_' + 'b' * 32, 'failed')]:
        decisions.store.put('study', {'study_id': sid, 'project_id': pid, 'status': status, 'assessment': {'pareto_option_ids': ['A']} if status == 'succeeded' else None})
    monkeypatch.setattr(decisions, 'view', lambda project_id, study_id: decisions.store.get('study', study_id))
    value = decisions.diagnosis(pid)
    assert value['latest_study_status'] == 'failed'
    assert value['current_study_id'] is None and value['current_assessment'] is None


def test_numeric_constraints_cannot_be_booleans():
    with pytest.raises(ValidationError):
        Constraints(max_cost_cny=True)
    with pytest.raises(ValidationError):
        Option(option_id='A', name='A', material_id='x', thickness_m=True)


def test_human_report_includes_material_scope_and_handles_missing_metrics():
    from backend.decision_reports import decision_html, decision_pdf
    material = {**card_body('evidence_x'), 'material_id': 'material_x', 'revision': 1, 'batch': None, 'evidence_snapshot': []}
    value = assessment([point('A', 80, None)])
    value.update(evaluated_options=1, total_options=1, untested_options=[])
    study = {'study_id': 'study_x', 'source_run_id': 'run_x', 'target_material': 'Layer', 'basis': 'Synthetic test scope',
             'engine_calls': 0, 'assessment': value, 'material_snapshots': {'material_x': material},
             'options': [], 'cost_snapshots': {}, 'limitations': ['Explicit unit test, not physical output'], 'source_provenance': {}}
    report = {'project': {'name': '<untrusted project>'}, 'generated_at': 'test', 'certificate': {'status': value['status']},
              'study': study, 'diagnosis': {'tasks': []}}
    rendered = decision_html(report)
    assert '&lt;untrusted project&gt;' in rendered and '增量初始造价 CNY：未知' in rendered
    assert 'Synthetic insulation' in rendered and 'Declared synthetic dry scenario' in rendered
    assert decision_pdf(report).startswith(b'%PDF')
