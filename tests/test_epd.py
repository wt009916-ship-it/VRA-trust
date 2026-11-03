"""Synthetic declaration edge cases; public-source arithmetic is verified separately."""
import csv
import json
from datetime import date
from uuid import uuid4

import pytest

from backend import core
from backend.epd import EpdLibrary, EpdReference, REQUIRED
from backend.store import Store
from test_api import create_project
from test_retrofit_packages import body, setup


def write_csv(path, rows):
    fields = sorted(REQUIRED | {'Name (de)', 'Kategorie (en)', 'Laenderkennung', 'Declaration owner',
                                'Registrierungsnummer', 'Hintergrunddatenbank(en)'})
    with path.open('w', encoding='cp1252', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, delimiter=';')
        writer.writeheader()
        writer.writerows(rows)
    return path


def declaration(**overrides):
    row = {k: '' for k in REQUIRED}
    row.update({'UUID': str(uuid4()), 'Version': '00.01.000', 'Name (en)': 'Synthetic control',
                'Typ': 'specific dataset', 'Bezugsgroesse': '2', 'Bezugseinheit': 'qm', 'Modul': 'A1-A3',
                'GWPtotal (A2)': '6', 'Konformitaet': 'EN 15804+A2',
                'Gueltig bis': str(date.today().year+3), 'URL': 'javascript:alert(1)'})
    return {**row, **overrides}


def load(tmp_path, rows):
    lib = EpdLibrary(Store(tmp_path/'runtime'))
    release = lib.import_csv(write_csv(tmp_path/'epd.csv', rows))
    ref = EpdReference(release_sha256=release['sha256'], uuid=rows[0]['UUID'], version=rows[0]['Version'])
    return lib, ref


def test_declared_amount_negative_biogenic_and_no_module_d_credit(tmp_path):
    row = declaration(**{'GWPtotal (A2)': '-12'})
    rows = [row, {**row, 'Modul': 'D', 'GWPtotal (A2)': '-999'}]
    lib, ref = load(tmp_path, rows)
    result = lib.calculate(ref, 10., 'm2', 'A1-A3')
    assert result['gwp_per_unit'] == -6 and result['material_kgco2e'] == -60
    assert [r['csv_line'] for r in result['source_rows']] == [2]
    assert result['issued_credits_t'] is None and result['project_applicability'] == 'NOT_REVIEWED'
    assert result['dataset']['source_url'].startswith('https://www.oekobaudat.de/')
    assert 'javascript:' not in result['dataset']['source_url']


@pytest.mark.parametrize('changes,unit,boundary', [
    ({'GWPtotal (A2)': ''}, 'm2', 'A1-A3'),
    ({'Szenario': 'Alternative route'}, 'm2', 'A1-A3'),
    ({'Gueltig bis': str(date.today().year)}, 'm2', 'A1-A3'),
    ({'Gueltig bis': str(date.today().year-1)}, 'm2', 'A1-A3'),
    ({'Bezugsgroesse': ''}, 'm2', 'A1-A3'),
    ({'Bezugseinheit': 'm'}, 'm2', 'A1-A3'),
    ({'Konformitaet': 'EN 15804+A1'}, 'm2', 'A1-A3'),
    ({}, 'kg', 'A1-A3'), ({}, 'm2', 'A1-A5'),
])
def test_unknown_incompatible_expired_or_incomplete_never_becomes_zero(tmp_path, changes, unit, boundary):
    lib, ref = load(tmp_path, [declaration(**changes)])
    result = lib.calculate(ref, 10., unit, boundary)
    assert result['gwp_per_unit'] is result['material_kgco2e'] is None
    assert result['gaps'] and result['state'] == 'NEEDS_EVIDENCE'


def test_lifecycle_combinations_are_not_double_counted(tmp_path):
    row = declaration()
    rows = [row, *[{**row, 'Modul': m, 'GWPtotal (A2)': '2'} for m in ('A1', 'A2', 'A3', 'A4', 'A5')],
            {**row, 'Modul': 'D', 'GWPtotal (A2)': '-100'}]
    lib, ref = load(tmp_path, rows)
    result = lib.calculate(ref, 10., 'm2', 'A1-A5')
    assert result['material_kgco2e'] == 50  # (6+2+2)/declared 2 * 10
    assert [r['values']['Modul'] for r in result['source_rows']] == ['A1-A3', 'A4', 'A5']


def test_duplicate_or_alternate_scenarios_refused_not_added(tmp_path):
    row = declaration()
    lib, ref = load(tmp_path, [row, {**row, 'Szenario': 'S2', 'GWPtotal (A2)': '1'}])
    assert lib.calculate(ref, 10., 'm2', 'A1-A3')['material_kgco2e'] is None


def test_source_integrity_idempotence_and_snapshot_preservation(tmp_path):
    row = declaration()
    lib, ref = load(tmp_path, [row])
    before = lib.release()
    assert lib.import_csv(tmp_path/'epd.csv') == before
    write_csv(tmp_path/'updated.csv', [{**row, 'Version': '00.02.000', 'GWPtotal (A2)': '20'}])
    lib.import_csv(tmp_path/'updated.csv')
    assert lib.calculate(ref, 10., 'm2', 'A1-A3')['material_kgco2e'] == 30
    archive = lib.store.root/'epd-sources'/f'{ref.release_sha256}.csv'
    archive.write_bytes(archive.read_bytes()+b'\n')
    with pytest.raises(core.ValidationError, match='哈希'):
        lib.calculate(ref, 10., 'm2', 'A1-A3')


@pytest.mark.parametrize('value', ['NaN', 'Infinity', '1,2'])
def test_invalid_numbers_do_not_partially_import(tmp_path, value):
    lib = EpdLibrary(Store(tmp_path/'runtime'))
    with pytest.raises(core.ValidationError):
        lib.import_csv(write_csv(tmp_path/'bad.csv', [declaration(), declaration(**{'GWPtotal (A2)': value})]))
    assert lib.release() is None and lib.search()['total'] == 0


def test_search_pagination_filters_and_literal_sql(tmp_path):
    rows = [declaration(**{'Name (en)': f'Synthetic panel {i:02d}', 'Typ': 'generic dataset' if i%2 else 'specific dataset'}) for i in range(43)]
    lib, _ = load(tmp_path, rows)
    pages = [lib.search(page=i) for i in (1, 2, 3)]
    assert [len(p['items']) for p in pages] == [20, 20, 3]
    assert len({d['uuid'] for p in pages for d in p['items']}) == 43
    assert lib.search(dataset_type='specific dataset')['total'] == 22
    assert lib.search("' OR 1=1 --")['total'] == 0
    assert lib.search(unit='kg')['total'] == 0


def test_project_api_auth_csrf_and_epd_package_binding(client, tmp_path):
    pid, ev, path = setup(client)
    lib = client.app.state.domain.sustainability.epds
    row = declaration()
    rel = lib.import_csv(write_csv(tmp_path/'epd.csv', [row]))
    reference = dict(release_sha256=rel['sha256'], uuid=row['UUID'], version=row['Version'])
    response = client.post(path+'/epds/calculate', json={**reference, 'quantity': 10., 'unit': 'm2', 'boundary': 'A1-A3'})
    assert response.status_code == 200 and response.json()['material_kgco2e'] == 30
    data = body(ev['evidence_id'])
    data['packages'][0]['items'][0].update(epd_reference=reference, gwp_per_unit=None)
    saved = client.post(path+'/packages', json=data)
    assert saved.status_code == 201, saved.text
    result = saved.json()['result']['rows'][0]
    assert result['initial_material_kgco2e'] == 330  # actual scope 100*3 plus roof 10*3
    assert result['items'][0]['epd_calculation']['quantity'] == 100
    assert result['items'][0]['epd_calculation']['source_rows'][0]['csv_line'] == 2
    data['packages'][0]['items'][0]['gwp_per_unit'] = .001
    assert client.post(path+'/packages/preview', json=data).status_code == 409
    csrf = client.headers.pop('X-CSRF-Token')
    assert client.post(path+'/epds/calculate', json={**reference, 'quantity': 10., 'unit': 'm2'}).status_code == 403
    client.headers['X-CSRF-Token'] = csrf
    client.cookies.clear()
    assert client.get(path+'/epds').status_code == 401
    other = client.post('/api/auth/register', json={'username': 'epd_other_owner', 'display_name': 'Other', 'password': 'Other-epd-test-2026-pass'}).json()
    client.headers['X-CSRF-Token'] = other['csrf_token']
    assert client.get(path+'/epds').status_code == 404


def test_manual_carbon_needs_source_before_returning_total(client):
    _, ev, path = setup(client)
    data = body(ev['evidence_id'])
    # Keep a numeric factor but no declared source: schema must reject, not publish an amount.
    data['packages'][0]['items'][0]['gwp_evidence_id'] = None
    assert client.post(path+'/packages/preview', json=data).status_code == 422


def test_agent_epd_tools_read_actual_library(client, tmp_path):
    from backend.agent import ToolArgs
    pid = create_project(client)['project_id']
    lib = client.app.state.domain.sustainability.epds
    row = declaration()
    release = lib.import_csv(write_csv(tmp_path/'epd.csv', [row]))
    agent = client.app.state.agent
    search = agent.call(pid, 'epd_search', ToolArgs(query='Synthetic'), False)
    assert search['total'] == 1 and search['items'][0]['uuid'] == row['UUID']
    args = ToolArgs(epd={'release_sha256': release['sha256'], 'uuid': row['UUID'], 'version': row['Version'], 'quantity': 10., 'unit': 'm2'})
    result = agent.call(pid, 'epd_calculate', args, False)
    assert result['material_kgco2e'] == 30 and result['source_rows'][0]['csv_line'] == 2
    assert len(json.dumps(result)) < 10000
