"""Actual local OCR plus fail-closed source, raster and review contracts."""
import io
import json
import hashlib
from pathlib import Path

import pytest
from PIL import Image
from pydantic import ValidationError
from reportlab.pdfgen.canvas import Canvas

from backend import core
from backend.drawings import Drawings, DrawingInput, DrawingReview
from backend.drawing_worker import load_page
from test_api import create_project
from test_cad import upload

GOLD = Path(__file__).resolve().parents[1]/'fixtures/drawing_gold'


def create_ocr(client, name='clean.png', data=None, page=1):
    pid=create_project(client)['project_id'];data=data or (GOLD/name).read_bytes()
    fid=upload(client,pid,name,data);base=f'/api/projects/{pid}/drawings'
    response=client.post(base,json={'file_id':fid,'page':page})
    assert response.status_code==201,response.text
    return pid,base,response.json(),data


def test_real_ocr_review_history_no_auto_engineering_and_stale(client,monkeypatch):
    pid,base,record,raw=create_ocr(client)
    did=record['drawing_id'];assert record['source']['hash']==hashlib.sha256(raw).hexdigest()
    candidates=record['result']['candidates'];assert {c['text'] for c in candidates}=={'平面图','6000 mm','办公室','会议室','LEVEL 1'}
    assert all(c['review_required'] and c['source_kind']=='AI_INFERRED' for c in candidates)
    truth=json.loads((GOLD/'truth.json').read_text(encoding='utf-8'))['labels']
    for expected in truth:
        c=next(c for c in candidates if c['text']==expected['text']);x=sum(p[0] for p in c['polygon_px'])/4;y=sum(p[1] for p in c['polygon_px'])/4
        left,top,right,bottom=expected['bbox'];assert left-10<=x<=right+10 and top-10<=y<=bottom+10
    preview=client.get(base+'/'+did+'/preview.png');assert preview.status_code==200
    assert hashlib.sha256(preview.content).hexdigest()==record['result']['preview_sha256']
    original=client.app.state.domain.store.get('project',pid)
    candidate=next(c for c in candidates if c['text']=='6000 mm')
    body={'expected_revision':1,'candidate_id':candidate['candidate_id'],'decision':'confirmed','basis':'逐字核对独立设计的原图标注，与模型文字一致。'}
    r=client.post(base+'/'+did+'/review',json=body);assert r.status_code==200,r.text
    review=r.json()['reviews'][candidate['candidate_id']]
    assert review['effective_text']=='6000 mm' and review['source_kind']=='HUMAN_TRANSCRIPTION' and review['reviewer_id']
    assert client.post(base+'/'+did+'/review',json=body).status_code==409  # no lost update
    body.update(expected_revision=2,decision='corrected',corrected_text='6000 mm（仅转录，单位待项目核对）')
    assert client.post(base+'/'+did+'/review',json=body).status_code==200
    body.update(expected_revision=3,decision='unreadable',corrected_text=None,basis='模拟重新复核无法确认原始标注，应撤回确定转录。')
    r=client.post(base+'/'+did+'/review',json=body);assert r.status_code==200
    assert r.json()['reviews'][candidate['candidate_id']]['effective_text'] is None
    history=client.get(base+'/'+did+'/history').json();assert [r['revision'] for r in history]==[1,2,3,4]
    assert history[1]['last_review']['effective_text']=='6000 mm'
    assert client.app.state.domain.store.get('project',pid)==original
    assert client.app.state.domain.store.list('evidence',pid)==[]
    body.update(expected_revision=4,candidate_id='text_999')
    assert client.post(base+'/'+did+'/review',json=body).status_code==409
    other=create_project(client)['project_id']
    assert client.get(f'/api/projects/{other}/drawings/{did}/preview.png').status_code==409
    monkeypatch.setattr('backend.drawings.parser_hash',lambda:'changed-model')
    view=client.get(base+'/'+did).json();assert view['status']=='stale' and view['result'] is None and view['reviews'] is None
    assert client.post(base+'/'+did+'/review',json=body).status_code==409
    assert client.get(base+'/'+did+'/preview.png').status_code==409
    client.cookies.clear();assert client.get(base+'/'+did).status_code==401


@pytest.mark.parametrize('kind',['source','preview'])
def test_source_and_preview_corruption_invalidate_candidates(client,kind):
    pid,base,record,_=create_ocr(client,'blank.png')
    domain=client.app.state.domain
    path=domain.file_record(pid,record['source']['file_id'])[1] if kind=='source' else domain.store.root/record['preview_path']
    path.write_bytes(b'isolated test tamper')
    assert client.get(base+'/'+record['drawing_id']).json()['result'] is None
    assert client.get(base+'/'+record['drawing_id']+'/preview.png').status_code==409


def pdf_bytes():
    stream=io.BytesIO();c=Canvas(stream,pagesize=(360,240));c.setFont('Helvetica',24);c.drawString(30,120,'PAGE ONE');c.showPage()
    c.setFont('Helvetica',24);c.drawString(30,120,'PAGE TWO');c.showPage();c.save();return stream.getvalue()


def test_real_pdf_page_selection_not_text_layer_shortcut(client):
    _,_,record,_=create_ocr(client,'drawing.pdf',pdf_bytes(),2)
    result=record['result'];assert result['page']['page']==2 and result['page']['page_count']==2 and result['page']['kind']=='pdf_raster'
    assert any(c['text']=='PAGE TWO' for c in result['candidates'])
    assert not any('ONE' in c['text'] for c in result['candidates'])
    # PDFium ceil(240 * (150/72)) is 501 with IEEE binary floating point.
    # Boxes and preview must use actual raster dimensions, not nominal 500.
    assert (result['width'],result['height'])==(750,501)
    assert result['page']['raster_rounding'].startswith('ceil per axis')


def test_blank_is_unknown_not_successful_comprehension(client):
    _,_,record,_=create_ocr(client,'blank.png')
    assert record['result']['candidates']==[]
    assert record['result']['state']=='no_text_detected_not_proof_of_absence'


@pytest.mark.parametrize('filename,data',[('bad.png',b'not png'),('bad.pdf',b'%PDF broken'),('bad.jpg',b'bad'),('unknown.dxf',b'wrong input')])
def test_bad_files_rejected_original_retained(client,filename,data):
    pid=create_project(client)['project_id'];fid=upload(client,pid,filename,data)
    base=f'/api/projects/{pid}/drawings'
    assert client.post(base,json={'file_id':fid}).status_code==409
    assert client.get(base).json()==[]
    assert client.app.state.domain.file_record(pid,fid)[1].read_bytes()==data


def test_exif_orientation_and_transparency_have_explicit_preview_coordinates(tmp_path):
    image=Image.new('RGB',(80,40),'red');exif=Image.Exif();exif[274]=6
    path=tmp_path/'exif.jpg';image.save(path,exif=exif)
    decoded,info=load_page(path,1);assert decoded.size==(40,80) and info['exif_orientation']==6
    path=tmp_path/'alpha.png';Image.new('RGBA',(64,64),(0,0,0,0)).save(path)
    decoded,_=load_page(path,1);assert decoded.getpixel((0,0))==(255,255,255)


def test_image_and_pdf_page_budgets(tmp_path):
    large=tmp_path/'large.png';Image.new('L',(6001,32),'white').save(large)
    with pytest.raises(ValueError,match='budget'): load_page(large,1)
    path=tmp_path/'fake.png';Image.new('RGB',(64,64),'white').save(path,format='GIF')
    with pytest.raises(ValueError,match='single-frame'): load_page(path,1)
    with pytest.raises(ValueError,match='page 1'): load_page(GOLD/'clean.png',2)
    path=tmp_path/'pages.pdf';path.write_bytes(pdf_bytes())
    with pytest.raises(ValueError,match='range'):load_page(path,3)


def test_pdf_rounded_area_budget_checked_before_native_allocation(tmp_path,monkeypatch):
    import pypdfium2 as pdfium
    path=tmp_path/'rounded.pdf';path.write_bytes(pdf_bytes())
    # Continuous 750*500 fits this limit; PDFium's real 750*501 does not.
    monkeypatch.setattr('backend.drawing_worker.MAX_PIXELS',375000)
    def forbidden_render(*args,**kwargs):
        pytest.fail('Native raster allocation must not occur beyond budget')
    monkeypatch.setattr(pdfium.PdfPage,'render',forbidden_render)
    with pytest.raises(ValueError,match='pixel budget'):load_page(path,1)


def test_missing_ocr_package_fails_closed(client,monkeypatch):
    from importlib.metadata import PackageNotFoundError
    pid,base,record,_=create_ocr(client,'blank.png')
    def missing():raise PackageNotFoundError('rapidocr')
    monkeypatch.setattr('backend.drawings.parser_hash',missing)
    assert client.get(base+'/'+record['drawing_id']).json()['status']=='stale'
    response=client.post(base,json={'file_id':record['source']['file_id']})
    assert response.status_code==409 and 'unavailable' in response.text


def test_drawing_routes_enforce_csrf_and_owner(client):
    from fastapi.testclient import TestClient
    from test_auth import register
    _,base,record,_=create_ocr(client,'blank.png')
    did=record['drawing_id']
    token=client.headers.pop('X-CSRF-Token')
    assert client.post(base,json={'file_id':record['source']['file_id']}).status_code==403
    assert client.post(base+'/'+did+'/review',json={}).status_code==403
    client.headers['X-CSRF-Token']=token
    with TestClient(client.app) as stranger:
        register(stranger,'other_ocr_owner')
        for suffix in ('','/'+did,'/'+did+'/preview.png','/'+did+'/history'):
            assert stranger.get(base+suffix).status_code==404
        assert stranger.post(base+'/'+did+'/review',json={}).status_code==404


@pytest.mark.parametrize('value',[0,-1,201,True,1.5,'2'])
def test_page_input_is_strict(value):
    with pytest.raises(ValidationError):DrawingInput(file_id='file_'+'a'*32,page=value)


@pytest.mark.parametrize('decision,text',[('confirmed','invented'),('corrected',None),('unreadable','invented')])
def test_review_cannot_hide_inference_in_confirmation(decision,text):
    with pytest.raises(ValidationError):DrawingReview(expected_revision=1,candidate_id='text_1',decision=decision,corrected_text=text,basis='This is a test review basis.')


def test_timeout_releases_capacity_and_no_provider_keys_forwarded(client,monkeypatch):
    pid=create_project(client)['project_id'];fid=upload(client,pid,'blank.png',(GOLD/'blank.png').read_bytes())
    service=Drawings(client.app.state.domain);monkeypatch.setenv('DEEPSEEK_API_KEY','test-only-key')
    def timeout(*args,**kwargs):
        from backend.execution import ExecutionError
        assert args[4]==60
        raise ExecutionError('Native execution timeout')
    monkeypatch.setattr('backend.parser_runtime.execution.supervise',timeout)
    for _ in range(2):
        with pytest.raises(core.ValidationError,match='isolated execution failed'):service.save(pid,DrawingInput(file_id=fid))


def test_model_tamper_rejected_without_download(monkeypatch,tmp_path):
    from backend.drawing_models import model_paths
    class Distribution:
        def locate_file(self,name):return tmp_path
    monkeypatch.setattr('backend.drawing_models.distribution',lambda _:Distribution())
    with pytest.raises(ValueError,match='hash mismatch'):model_paths()
