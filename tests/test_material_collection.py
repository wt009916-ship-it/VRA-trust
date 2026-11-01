"""Protect the API-200-without-body trap; fixtures are synthetic XML, not source data."""
import json

from scripts import collect_material_sources as collect


def test_pmc_batch_checks_each_body_and_keeps_license(tmp_path, monkeypatch):
    monkeypatch.setattr(collect, 'PMC', ['Synthetic title'])
    monkeypatch.setattr(collect.time, 'sleep', lambda _: None)
    xml = b'''<pmc-articleset><article><front><article-title>Test full article</article-title>
    <article-id pub-id-type="doi">10.0000/full</article-id><license>CC BY test</license></front>
    <body><p>Explicit synthetic body</p></body></article>
    <article><front><article-title>Metadata only</article-title><article-id pub-id-type="doi">10.0000/meta</article-id></front></article></pmc-articleset>'''
    monkeypatch.setattr(collect, 'request', lambda url: json.dumps({'esearchresult': {'count':'2','idlist':['1','2']}}).encode()
                        if 'esearch' in url else xml)
    rows = collect.retrieve_pmc(tmp_path, '2026-11-01')
    assert sum(r['has_body'] for r in rows) == 1
    assert rows[0]['licenses'] == ['CC BY test']
    assert rows[1]['status'] == 'UNREVIEWED_DISCOVERY'


def test_success_http_invalid_envelope_is_recorded_as_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(collect, 'request', lambda _: b'{"errCode":503,"errMsg":"Unavailable"}')
    monkeypatch.setattr(collect.time, 'sleep', lambda _: None)
    rows, audit = collect.retrieve(tmp_path, 'europepmc', ['Synthetic query'], '2026-11-01')
    assert rows == [] and audit[0]['status'] == 'failed'
    assert 'Invalid Europe PMC envelope' in audit[0]['error']
