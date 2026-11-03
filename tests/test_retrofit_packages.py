"""Deterministic procurement arithmetic and refusal contracts; not field validation."""
import copy
from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from backend.retrofit_packages import CHECKS, COSTS, PackageComparison
from test_api import create_project
from test_decision import source


def body(eid):
    def amount(value):
        return {'total_cny': value, 'evidence_id': eid, 'locator': 'Synthetic quote page 1'}

    def item(sid, multiplier):
        return {'scope_id': sid, 'product': 'Synthetic control product', 'version': 'batch-v1',
                'costs': {k: amount(v * multiplier) for k, v in zip(COSTS, [100., 20., 0., 10., 0.], strict=True)},
                'checks': {k: {'satisfied': True, 'evidence_id': eid, 'locator': 'Synthetic report clause 2'} for k in CHECKS},
                'annual_maintenance': amount(3. * multiplier), 'replacement': amount(50. * multiplier),
                'service_life_years': 10, 'gwp_per_unit': 2. if sid == 'wall' else 3., 'gwp_unit': 'm2',
                'gwp_evidence_id': eid, 'gwp_locator': 'Synthetic A1-A3 table 3'}
    return {'name': 'Synthetic full package', 'budget_cny': 390., 'horizon_years': 20, 'discount_rate': 0.,
            'carbon_boundary': 'A1-A3', 'scopes': [
                {'scope_id': 'wall', 'name': 'Wall', 'quantity': 100., 'unit': 'm2',
                 'requirements': 'Synthetic equal function and coverage', 'evidence_id': eid, 'locator': 'Synthetic BoQ rows 1-10'},
                {'scope_id': 'roof', 'name': 'Roof', 'quantity': 10., 'unit': 'm2',
                 'requirements': 'Synthetic waterproofing requirement', 'evidence_id': eid, 'locator': 'Synthetic BoQ row 11'}],
            'packages': [{'package_id': 'control', 'name': 'Conventional control', 'items': [item('wall', 1), item('roof', 2)]}]}


def setup(client):
    pid = create_project(client)['project_id']
    ev = source(client, pid, status='DOCUMENTED')
    return pid, ev, f'/api/projects/{pid}/sustainability'


def test_full_scope_cost_cashflow_and_carbon_manual_oracle(client):
    pid, ev, path = setup(client)
    data = body(ev['evidence_id'])
    r = client.post(path+'/packages', json=data)
    assert r.status_code == 201, r.text
    row = r.json()['result']['rows'][0]
    assert row['initial_cost_cny'] == 390 and row['within_budget'] is True
    assert row['initial_material_kgco2e'] == 230
    assert row['discounted_declared_outlay_cny'] == 720  # 390 + 20*9 + 150 at year 10
    assert {f['year'] for f in row['cashflows'] if f['category'] == 'replacement'} == {10}
    assert row['state'] == 'READY_FOR_ENGINEER_REVIEW'
    assert row['engineering_gaps'] == row['cost_gaps'] == row['cashflow_gaps'] == row['carbon_gaps'] == []
    data['discount_rate'] = .05
    discounted = client.post(path+'/packages/preview', json=data).json()['rows'][0]['discounted_declared_outlay_cny']
    oracle = 390 + 9 * (1 - 1.05 ** -20) / .05 + 150 / 1.05 ** 10
    assert discounted == pytest.approx(oracle)
    assert len(client.get(path).json()) == 1  # preview never persists
    assert client.get(path+'/'+r.json()['sustainability_id']).json()['current']


@pytest.mark.parametrize('missing', list(COSTS))
def test_any_omitted_mandatory_cost_never_appears_within_budget(client, missing):
    _, ev, path = setup(client)
    data = body(ev['evidence_id'])
    data['packages'][0]['items'][0]['costs'].pop(missing)
    row = client.post(path+'/packages/preview', json=data).json()['rows'][0]
    assert row['initial_cost_cny'] is None and row['within_budget'] is None
    assert row['discounted_declared_outlay_cny'] is None and row['cost_gaps']


def test_unknown_scope_maintenance_life_and_material_remain_unknown(client):
    _, ev, path = setup(client)
    data = body(ev['evidence_id'])
    item = data['packages'][0]['items'][0]
    item['annual_maintenance'] = {}
    item['service_life_years'] = None
    item['gwp_per_unit'] = None
    row = client.post(path+'/packages/preview', json=data).json()['rows'][0]
    assert row['initial_cost_cny'] == 390 and row['discounted_declared_outlay_cny'] is None
    assert row['initial_material_kgco2e'] is None
    data['scopes'][0]['evidence_id'] = None
    row = client.post(path+'/packages/preview', json=data).json()['rows'][0]
    assert row['initial_cost_cny'] is None and row['initial_material_kgco2e'] is None
    assert row['engineering_gaps']


def test_omitted_scope_and_failed_fire_cannot_be_procurement_ready(client):
    _, ev, path = setup(client)
    data = body(ev['evidence_id'])
    data['packages'][0]['items'].pop()
    row = client.post(path+'/packages/preview', json=data).json()['rows'][0]
    assert row['state'] == 'NEEDS_EVIDENCE' and row['initial_cost_cny'] is None
    data = body(ev['evidence_id'])
    data['packages'][0]['items'][0]['checks']['fire']['satisfied'] = False
    row = client.post(path+'/packages/preview', json=data).json()['rows'][0]
    assert row['state'] != 'READY_FOR_ENGINEER_REVIEW'
    assert row['items'][0]['checks'][1]['state'] == 'FAIL'
    data['packages'][0]['items'][0]['checks']['fire']['satisfied'] = None
    assert client.post(path+'/packages/preview', json=data).json()['rows'][0]['engineering_gaps']


def test_replacement_at_horizon_is_excluded_and_over_budget_preserved(client):
    _, ev, path = setup(client)
    data = body(ev['evidence_id'])
    data['horizon_years'] = 10
    data['budget_cny'] = 389.
    for item in data['packages'][0]['items']:
        item['replacement'] = {}  # not required because no replacement inside horizon
    row = client.post(path+'/packages/preview', json=data).json()['rows'][0]
    assert row['discounted_declared_outlay_cny'] == 480
    assert row['state'] == 'OVER_BUDGET' and row['within_budget'] is False


def test_expiration_and_evidence_revoke_retain_historical_record(client):
    _, ev, path = setup(client)
    data = body(ev['evidence_id'])
    data['packages'][0]['items'][0]['costs']['material']['valid_until'] = (date.today()-timedelta(days=1)).isoformat()
    r = client.post(path+'/packages', json=data)
    assert r.status_code == 201, r.text
    assert r.json()['result']['rows'][0]['initial_cost_cny'] is None
    saved = client.get(path+'/'+r.json()['sustainability_id']).json()
    assert not saved['current'] and saved['result'] is None
    data = body(ev['evidence_id'])
    record = client.post(path+'/packages', json=data).json()
    client.patch(f'/api/projects/{record["project_id"]}/evidence/{ev["evidence_id"]}', json={
        'expected_revision': ev['revision'], 'review_state': 'pending', 'responsible_person': 'Test',
        'review_note': 'Withdraw synthetic quote approval'})
    assert not client.get(path+'/'+record['sustainability_id']).json()['current']
    original = client.app.state.domain.store.get('sustainability', record['sustainability_id'])
    assert original['result'] == record['result']


@pytest.mark.parametrize('case', ['duplicate', 'bad_unit', 'unknown_scope', 'boolean', 'zero_without_source', 'nan'])
def test_schema_rejects_noncomparable_and_unsourced(case):
    data = body('evidence_'+'b'*32)
    item = data['packages'][0]['items'][0]
    if case == 'duplicate':
        data['packages'][0]['items'].append(copy.deepcopy(item))
    elif case == 'bad_unit':
        item['gwp_unit'] = 'kg'
    elif case == 'unknown_scope':
        item['scope_id'] = 'missing'
    elif case == 'boolean':
        data['scopes'][0]['quantity'] = True
    elif case == 'zero_without_source':
        item['costs']['demolition'] = {'total_cny': 0.}
    else:
        data['discount_rate'] = float('nan')
    with pytest.raises(ValidationError):
        PackageComparison.model_validate(data)


def test_csv_intake_unicode_bom_quoted_fields_and_rejects_bad_rows(client):
    _, _, path = setup(client)
    header = '\ufeffscope_id,name,quantity,unit,requirements,evidence_id,locator\r\n'
    csv = header+'wall,"西墙,含门洞扣除",100,m2,"保温,防火等级需核对",,图纸页码待复核\r\n'
    r = client.post(path+'/package-quantities', content=csv.encode(), headers={'Content-Type': 'text/plain'})
    assert r.status_code == 200, r.text
    assert r.json()['scopes'][0]['name'] == '西墙,含门洞扣除'
    assert r.json()['state'] == 'DRAFT_REQUIRES_REVIEW'
    assert client.get(path).json() == []
    for invalid in [header, csv + 'broken,row\n', csv + csv.split('\r\n')[1]+'\r\n', header+'x,y,nan,m2,Test scope,,Table 1\r\n']:
        assert client.post(path+'/package-quantities', content=invalid.encode(), headers={'Content-Type': 'text/plain'}).status_code == 409


def test_package_cross_account_and_csrf(client):
    _, ev, path = setup(client)
    data = body(ev['evidence_id'])
    csrf = client.headers.pop('X-CSRF-Token')
    assert client.post(path+'/packages', json=data).status_code == 403
    client.headers['X-CSRF-Token'] = csrf
    assert client.post('/api/auth/logout').status_code == 200
    client.headers.pop('X-CSRF-Token')
    assert client.post(path+'/packages/preview', json=data).status_code == 401
    login = client.post('/api/auth/register', json={'username':'other_package_owner','display_name':'Test',
                        'password':'Other-package-test-pass-2026'}).json()
    client.headers['X-CSRF-Token'] = login['csrf_token']
    assert client.post(path+'/packages', json=data).status_code == 404
    assert client.post(path+'/package-quantities', content='bad', headers={'Content-Type':'text/plain'}).status_code == 404
