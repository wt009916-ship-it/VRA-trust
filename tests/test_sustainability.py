"""Synthetic contract cases; not material experiments or verified CCER projects."""
import copy

import pytest
from pydantic import ValidationError

from backend.sustainability import CHECKS, CreditScreen, Estimate, Selection, catalog
from test_api import create_project
from test_decision import source


def estimate(eid, **changes):
    return {'name': 'Synthetic equivalent-scope quote', 'quantity': 100.0, 'unit': 'm2',
            'unit_price_cny': 80.0, 'quote_evidence_id': eid, 'gwp_per_unit': 2.0,
            'gwp_unit': 'm2', 'gwp_boundary': 'A1-A3', 'gwp_evidence_id': eid,
            'source_locator': 'Synthetic document table 1', 'service_life_years': 10, **changes}


def test_catalog_has_traceable_sources_and_no_guessed_prices():
    data = catalog()
    assert len(data['entries']) >= 8
    assert data['price_cny'] is None and data['epd_factors'] is None
    assert len({e['id'] for e in data['entries']}) == len(data['entries'])
    assert all(e['url'].startswith('https://') and e['gaps'] and e['locator'] for e in data['entries'])
    assert next(e for e in data['entries'] if e['id'] == 'la2o3-phase')['maturity'] == 'out_of_building_scope'


def test_expanded_sources_separate_metadata_full_text_and_product_evidence():
    data = catalog(include_discovery=True)
    assert len(data['entries']) >= 40
    dois = [e['doi'].casefold() for e in data['entries'] if e.get('doi')]
    assert len(dois) == len(set(dois))
    records = data['discovery']['records']
    assert data['collection_stats']['metadata_records'] == len(records)
    assert data['collection_stats']['product_epds_obtained'] == 0
    assert data['collection_stats']['engineering_quotes_obtained'] == 0
    assert all('abstract' not in r and 'body' not in r for r in records)
    assert all(o['can_autofill_product_factor'] is False for e in data['entries'] for o in e.get('observations', []))
    cooling = next(e for e in data['entries'] if e['id'] == 'y-hollow-2024')
    assert {o['nature'] for o in cooling['observations']} == {'measured', 'calculated'}
    assert next(e for e in data['entries'] if e['id'] == 'ce-cement-negative')['application'] == 'research'
    assert 'CC BY-NC' in next(e for e in data['entries'] if e['id'] == 'eu-cage-lsc')['license_notice']
    assert 'discovery' not in catalog()  # avoid flooding the model with an unreviewed pool


def test_chemical_abbreviation_not_matched_inside_unrelated_english_word(client):
    pid = create_project(client)['project_id']
    result = client.post(f'/api/projects/{pid}/sustainability/selections', json={
        'intent': 'office retrofit budget for facade', 'budget_cny': 20000.}).json()['result']
    assert all('Ce' not in e['matched_terms'] for e in result['candidates'])
    excluded = next(e for e in result['candidates'] if e['id'] == 'lab6-csp-excluded')
    assert excluded['selection_state'] == 'RESEARCH_ONLY'
    assert len(client.get(f'/api/projects/{pid}/material-research').json()['discovery']['records']) >= 100


def test_budget_and_embodied_units_and_replacement_boundary(client):
    pid = create_project(client)['project_id']
    eid = source(client, pid, status='DOCUMENTED')['evidence_id']
    body = {'intent': '西晒窗户改造保留采光', 'budget_cny': 8000.0, 'horizon_years': 20,
            'application': 'glazing', 'estimates': [estimate(eid)]}
    r = client.post(f'/api/projects/{pid}/sustainability/selections', json=body)
    assert r.status_code == 201, r.text
    result = r.json()['result']
    row = result['estimates'][0]
    assert row['initial_cost_cny'] == 8000 and row['within_budget'] is True
    assert row['initial_embodied_kgco2e'] == 200
    assert row['replacement_cycles'] == 2 and row['horizon_material_kgco2e'] == 400
    assert row['annual_operating_saving_kgco2'] is None
    assert result['issued_credits_t'] is None
    assert all(e['application'] == 'glazing' for e in result['candidates'])
    assert '窗' in result['candidates'][0]['matched_terms']


def test_unknown_cost_and_life_never_become_zero(client):
    pid = create_project(client)['project_id']
    body = {'intent': '外墙材料兼顾碳排与维护', 'budget_cny': 100.0, 'estimates': [
        {'name': 'Unknown quote', 'quantity': 2.0, 'unit': 'kg', 'source_locator': 'Explicit unknown input'}]}
    row = client.post(f'/api/projects/{pid}/sustainability/selections', json=body).json()['result']['estimates'][0]
    assert row['initial_cost_cny'] is None and row['within_budget'] is None
    assert row['horizon_material_kgco2e'] is None


@pytest.mark.parametrize('changes', [{'gwp_unit': 'kg'}, {'gwp_boundary': None}, {'gwp_evidence_id': None},
                                   {'quote_evidence_id': None}, {'quantity': -1.0}, {'gwp_per_unit': float('nan')}])
def test_invalid_economic_and_carbon_inputs(changes):
    with pytest.raises(ValidationError):
        Estimate.model_validate(estimate('evidence_'+'a'*32, **changes))


def test_source_assumption_is_rejected_and_revision_stales_report(client):
    pid = create_project(client)['project_id']
    assumption = source(client, pid)
    body = {'intent': '比较稀土外墙材料预算', 'budget_cny': 9000.0, 'estimates': [estimate(assumption['evidence_id'])]}
    assert client.post(f'/api/projects/{pid}/sustainability/selections', json=body).status_code == 409
    ev = source(client, pid, status='DOCUMENTED')
    body['estimates'] = [estimate(ev['evidence_id'])]
    record = client.post(f'/api/projects/{pid}/sustainability/selections', json=body).json()
    assert client.get(f'/api/projects/{pid}/sustainability/{record["sustainability_id"]}').json()['current']
    response = client.patch(f'/api/projects/{pid}/evidence/{ev["evidence_id"]}', json={
        'expected_revision': ev['revision'], 'review_state': 'confirmed',
        'responsible_person': 'Test', 'review_note': 'Changed synthetic document review'})
    assert response.status_code == 200
    stale = client.get(f'/api/projects/{pid}/sustainability/{record["sustainability_id"]}').json()
    assert stale['current'] is False and stale['result'] is None
    assert client.app.state.domain.store.get('sustainability', record['sustainability_id'])['result'] == record['result']


def complete_screen(eid):
    declaration = {'satisfied': True, 'evidence_id': eid, 'locator': 'Synthetic test page 1'}
    return {'checks': {key: copy.deepcopy(declaration) for key in CHECKS}, 'monthly_hours': [160.0]*24,
            'hours_evidence_id': eid, 'measures': [{'code': '1', 'coverage': .8, 'evidence_id': eid,
                                                    'performance': declaration}]}


def test_credit_readiness_never_issues_even_all_checks_declared(client):
    pid = create_project(client)['project_id']
    eid = source(client, pid, status='DOCUMENTED')['evidence_id']
    path = f'/api/projects/{pid}/sustainability/credit-screens'
    assert client.post(path, json={}).json()['result']['status'] == 'NEEDS_EVIDENCE'
    body = complete_screen(eid)
    body.update(hypothetical_tonnes=10.0, prices_cny_per_t=[50.0, 100.0], development_cost_cny=1000.0, monitoring_cost_cny=200.0)
    result = client.post(path, json=body).json()['result']
    assert result['status'] == 'READY_FOR_PROFESSIONAL_REVIEW'
    assert result['issued_credits_t'] is None and result['eligible_credits_t'] is None
    assert result['economic_scenarios'][0]['hypothetical_net_cny'] == -700
    assert result['credit_revenue_in_base_case'] is False
    body['checks']['not_pilot_ets']['satisfied'] = False
    assert client.post(path, json=body).json()['result']['status'] == 'BLOCKED'


@pytest.mark.parametrize('code,ratio,expected', [('1', .79, 'FAIL'), ('1', .8, 'DECLARED_PASS'),
                                              ('7', .65, 'FAIL'), ('7', .66, 'DECLARED_PASS')])
def test_actual_methodology_area_and_capacity_thresholds(client, code, ratio, expected):
    pid = create_project(client)['project_id']
    eid = source(client, pid, status='DOCUMENTED')['evidence_id']
    body = complete_screen(eid)
    body['measures'][0].update(code=code, coverage=ratio)
    result = client.post(f'/api/projects/{pid}/sustainability/credit-screens', json=body).json()['result']
    assert result['measures'][0]['state'] == expected


def test_school_exemption_and_continuous_month_count(client):
    pid = create_project(client)['project_id']
    eid = source(client, pid, status='DOCUMENTED')['evidence_id']
    path = f'/api/projects/{pid}/sustainability/credit-screens'
    body = complete_screen(eid)
    body['monthly_hours'][0] = 0.0
    assert client.post(path, json=body).json()['result']['status'] == 'BLOCKED'
    body['school_kind'] = 'primary_secondary_kindergarten'
    assert client.post(path, json=body).json()['result']['status'] == 'READY_FOR_PROFESSIONAL_REVIEW'
    body['monthly_hours'] = body['monthly_hours'][:12]
    assert client.post(path, json=body).json()['result']['status'] == 'NEEDS_EVIDENCE'


def test_all_api_paths_enforce_project_ownership_and_csrf(client):
    pid = create_project(client)['project_id']
    ev = source(client, pid, status='DOCUMENTED')
    record = client.post(f'/api/projects/{pid}/sustainability/credit-screens', json=complete_screen(ev['evidence_id'])).json()
    client.post('/api/auth/logout')
    assert client.get(f'/api/projects/{pid}/material-research').status_code == 401
    reg = client.post('/api/auth/register', json={'username':'other_material_owner','display_name':'Other',
        'password':'Other-test-only-pass-2026'}).json()
    client.headers['X-CSRF-Token'] = reg['csrf_token']
    for suffix in ['material-research', 'sustainability', 'sustainability/'+record['sustainability_id']]:
        assert client.get(f'/api/projects/{pid}/'+suffix).status_code == 404
    own = create_project(client)['project_id']
    assert client.get(f'/api/projects/{own}/sustainability/{record["sustainability_id"]}').status_code == 409
    client.headers.pop('X-CSRF-Token')
    assert client.post(f'/api/projects/{own}/sustainability/credit-screens', json={}).status_code == 403


def test_credit_schema_rejects_fabricated_checks_and_nonfinite():
    for body in [{'checks': {'invented': {'satisfied':True}}}, {'hypothetical_tonnes':float('inf')},
                 {'monthly_hours':[-1.0]}, {'prices_cny_per_t':[-10.0]}]:
        with pytest.raises(ValidationError):
            CreditScreen.model_validate(body)
    with pytest.raises(ValidationError):
        Selection.model_validate({'intent':'合法性待核验', 'budget_cny':float('nan')})


def test_agent_reads_project_sustainability_without_computation(client):
    pid = create_project(client)['project_id']
    agent = client.app.state.agent
    tools = {t['function']['name'] for t in agent.tools('materials', allow_compute=False)}
    assert {'material_research', 'sustainability_reports'} <= tools
    assert 'material_study_create' not in tools
    knowledge = agent.call(pid, 'material_research', {}, False)
    assert knowledge['methodology']['id'] == 'CCER-06-001-V01'
    client.post(f'/api/projects/{pid}/sustainability/credit-screens', json={})
    result = agent.call(pid, 'sustainability_reports', {}, False)
    assert len(result) == 1 and result[0]['result']['issued_credits_t'] is None


def test_agent_can_retrieve_sources_beyond_initial_context_cap(client):
    pid = create_project(client)['project_id']
    agent = client.app.state.agent
    first = agent.call(pid, 'material_research', {}, False)
    assert len(first['entries']) == 5 and first['has_more']
    found = agent.call(pid, 'material_research', {'query':'Y2O3', 'limit':5}, False)
    assert {e['id'] for e in found['entries']} >= {'y-hollow-2024', 'y-hollow-2023', 'y-fdtd-2024'}
    assert all(e['id'] != 'lab6-review' for e in found['entries'])
    missing = agent.call(pid, 'material_research', {'query':'nonexistent-exact-product-123'}, False)
    assert missing['entries'] == [] and missing['total_matches'] == 0
