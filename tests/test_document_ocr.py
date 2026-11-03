"""Real CPU OCR plus revision, ownership and original-document preservation."""
import io
import subprocess

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from backend import core, document_reader
from backend.agent import provider_context
from backend.intake import parse_source
from test_intake_admin import PROJECT, batch, register


def synthetic_image():
    image = Image.new('RGB', (1100, 420), 'white')
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=36)
    for index, line in enumerate(['name: Synthetic OCR test', 'use: office',
                                  'location: Test city', 'region: TEST', 'area_m2: 1234.5 m2']):
        draw.text((30, 25 + index * 75), line, fill='black', font=font)
    return image


def test_real_raster_and_mixed_pdf(tmp_path):
    image = synthetic_image()
    path = tmp_path/'scan.png'
    image.save(path)
    result = parse_source(path)
    values = {c['field']: c['value'] for c in result['candidates']}
    assert values['area_m2'] == 1234.5 and values['region'] == 'TEST'
    facts = result['facts']
    assert facts['ocr']['external_upload'] is False
    assert len(facts['ocr']['model_hashes']) == 3
    assert facts['document_pages'][0]['lines'][0]['box']
    pdf = tmp_path/'mixed.pdf'
    c = canvas.Canvas(str(pdf), pagesize=(550, 210))
    c.drawString(20, 170, 'name: Text page retained in mixed scan document')
    c.showPage()
    c.drawImage(ImageReader(image), 0, 0, width=550, height=210)
    c.showPage()
    c.save()
    extracted = parse_source(pdf)
    pages = extracted['facts']['document_pages']
    assert [p['method'] for p in pages] == ['text', 'ocr']
    assert any(c['field'] == 'area_m2' and c['value'] == 1234.5 for c in extracted['candidates'])
    preview = document_reader.preview(pdf, 2)
    assert preview.startswith(b'\x89PNG')
    with pytest.raises(core.ValidationError, match='页码'):
        document_reader.preview(pdf, 3)


def test_correction_history_authorization_conflicts_and_adoption(client):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer)
    c.drawString(20, 700, 'name: Original declared project title')
    c.drawString(20, 670, 'area_m2: 100')
    c.save()
    b = batch(client, [('original.pdf', buffer.getvalue()), ('conflict.txt', b'area_m2: 200')])
    base = '/api/intakes/'+b['id']
    source = b['files'][0]
    url = base+'/files/'+source['file_id']
    assert b['conflicts'] == ['area_m2']
    assert client.get(url+'/pages/1').status_code == 200
    assert client.get(url+'/pages/0').status_code == 422
    assert client.get(url+'/pages/81').status_code == 422
    body = {'expected_revision': 0, 'page': 1, 'text':'name: Corrected declared title\narea_m2: 200',
            'reason':'Review against source drawing'}
    with TestClient(client.app) as stranger:
        register(stranger, 'other_ocr_user')
        assert stranger.post(url+'/corrections', json=body).status_code == 404
        assert stranger.get(url+'/pages/1').status_code == 404
    assert client.post(url+'/corrections', json=body, headers={'X-CSRF-Token':''}).status_code == 403
    assert client.post(url+'/corrections', json={**body, 'reason':'   '}).status_code == 422
    assert client.post(url+'/corrections', json={**body, 'page':2}).status_code == 422
    corrected = client.post(url+'/corrections', json=body)
    assert corrected.status_code == 200, corrected.text
    record = corrected.json()
    assert record['conflicts'] == [] and record['suggestions']['area_m2'] == 200
    assert record['files'][0]['analysis']['facts']['document_pages'] == source['analysis']['facts']['document_pages']
    assert record['files'][0]['corrections'][0]['source_hash'] == source['hash']
    assert client.post(url+'/corrections', json=body).status_code == 409
    # Appending another source and re-analysis must not erase reviewed text or its original.
    assert client.post(base+'/files', files={'file':('extra.txt', b'region: TEST')}).status_code == 201
    assert client.post(base+'/analyze').status_code == 202
    record = client.get(base).json()
    assert record['suggestions']['name'] == 'Corrected declared title'
    assert len(record['files'][0]['corrections']) == 1
    committed = client.post(base+'/commit', json={'project':PROJECT,'reviewed':True}).json()
    evidence = client.get('/api/projects/'+committed['project_id']+'/evidence').json()
    ev = next(e for e in evidence if e['name'] == 'original.pdf')
    assert ev['review_state'] == 'pending'
    assert ev['value']['corrections'][0]['actor']
    assert ev['value']['analysis']['facts']['document_pages'] == source['analysis']['facts']['document_pages']
    assert client.post(url+'/corrections', json={**body,'expected_revision':1}).status_code == 409
    filtered = provider_context(ev)
    assert 'document_pages' not in filtered['value']['analysis']['facts']
    assert 'corrections' not in filtered['value']


def test_blank_image_never_makes_project_fields(tmp_path):
    path = tmp_path/'blank.png'
    Image.new('RGB', (320, 240), 'white').save(path)
    result = parse_source(path)
    assert result['candidates'] == []
    assert result['facts']['document_pages'][0]['text'] == ''
    assert any('未识别' in warning for warning in result['warnings'])


def test_document_timeout_explicit(monkeypatch, tmp_path):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs['timeout'])
    monkeypatch.setattr(subprocess, 'run', timeout)
    with pytest.raises(core.ValidationError, match='超时'):
        document_reader.worker(tmp_path/'any.pdf')


def test_original_tampering_blocks_preview_and_correction(client):
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(20, 700, 'name: Hash preservation regression project')
    c.save()
    b = batch(client, [('source.pdf', buf.getvalue())])
    source = b['files'][0]
    core.relative_file(client.app.state.domain.store.root, source['path']).write_bytes(b'changed')
    base = '/api/intakes/'+b['id']+'/files/'+source['file_id']
    assert client.get(base+'/pages/1').status_code == 409
    assert client.post(base+'/corrections', json={'expected_revision':0,'page':1,'text':'name: New',
                                               'reason':'Hash mismatch'}).status_code == 409
