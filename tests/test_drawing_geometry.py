"""Independent coordinate and length answers, real raster/isolated OCR, stale and ownership paths."""
import hashlib
import math
from pathlib import Path

import pytest
from PIL import Image, ImageDraw
from pydantic import ValidationError

from backend import core
from backend.drawing_processing import point, rotation, process, suggest_angle
from backend.drawing_scale import ScaleInput, calculate, LengthInput, DrawingScales
from backend.drawings import DrawingInput
from test_api import create_project
from test_cad import upload


def reference(length=6000,unit='mm',end=(120,20)):
    return {'label':'independently declared dimension','start':{'x':20,'y':20},'end':{'x':end[0],'y':end[1]},
            'length':length,'unit':unit,'length_uncertainty':0,'point_uncertainty_px':0}


def scale_body(basis='a'*64):
    return {'basis_hash':basis,'references':[reference(),reference(3,'m',(70,20))],
            'relative_tolerance':0,'basis':'Synthetic independently declared dimensions, not a real building.',
            'plane_assumption':'user_declares_uniform_scale_on_this_page'}


@pytest.mark.parametrize('angle',[0,7,-7,15,-15])
def test_rotation_independent_geometry_and_inverse(angle):
    transform=rotation(360,240,angle)
    corners=[point(transform['source_to_preview'],p) for p in [(0,0),(360,0),(360,240),(0,240)]]
    assert min(p[0] for p in corners)==pytest.approx(0,abs=1e-10)
    assert min(p[1] for p in corners)==pytest.approx(0,abs=1e-10)
    for p in [(0,0),(360,240),(180,120),(3,237),(359,1)]:
        back=point(transform['preview_to_source'],point(transform['source_to_preview'],p))
        assert math.dist(p,back)<1e-6
    a=point(transform['source_to_preview'],(20,20));b=point(transform['source_to_preview'],(120,20))
    assert math.dist(a,b)==pytest.approx(100,abs=1e-10)
    assert math.degrees(math.atan2(b[1]-a[1],b[0]-a[0]))==pytest.approx(angle,abs=1e-10)


def test_actual_raster_rotation_matches_pixel_coordinate_receipt(tmp_path):
    image=Image.new('RGB',(360,240),'white');ImageDraw.Draw(image).rectangle((48,58,52,62),fill='black')
    derived,receipt=process(image,{'deskew_mode':'manual','angle_degrees':7.,'median_filter':False},tmp_path)
    target=point(receipt['transform']['source_to_preview'],(50.5,60.5))
    dark=[(x+.5,y+.5) for y in range(derived.height) for x in range(derived.width) if sum(derived.getpixel((x,y)))<384]
    center=(sum(p[0] for p in dark)/len(dark),sum(p[1] for p in dark)/len(dark))
    assert math.dist(center,target)<.7  # discrete resampling centroid, separately from exact matrix tolerance
    assert Image.open(tmp_path/'source-preview.png').tobytes()==image.tobytes()
    assert receipt['resampling']=='bicubic'


def test_filter_reports_erased_thin_lines_without_claiming_semantic_repair(tmp_path):
    image=Image.new('RGB',(100,100),'white');ImageDraw.Draw(image).line((10,50,90,50),fill='black',width=1)
    _,receipt=process(image,{'deskew_mode':'none','angle_degrees':0.,'median_filter':True},tmp_path)
    diff=receipt['filter_difference'];assert diff['dark_pixels_removed']==81 and diff['changed_pixels']==81
    assert diff['dark_pixels_added']==0
    assert hashlib.sha256((tmp_path/'filter-difference.png').read_bytes()).hexdigest()==diff['mask_sha256']


@pytest.mark.parametrize('angle',[True,'7',float('nan'),float('inf'),15.01,-15.01])
def test_strict_rotation_input(angle):
    with pytest.raises((ValueError,ValidationError)):
        DrawingInput(file_id='file_'+'a'*32,processing={'deskew_mode':'manual','angle_degrees':angle})


def test_rotation_growth_rejected_before_allocation():
    with pytest.raises(ValueError,match='budget'):rotation(6000,2000,15)
    with pytest.raises(ValidationError):DrawingInput(file_id='file_'+'a'*32,processing={'deskew_mode':'auto','angle_degrees':7})


def grid_image(angle=0):
    # Geometry is defined first; Pillow's independent rotate generates the degraded input.
    image=Image.new('RGB',(800,600),'white');draw=ImageDraw.Draw(image)
    for x in (80,230,440,700):draw.line((x,60,x,540),fill='black',width=3)
    for y in (60,210,360,540):draw.line((80,y,700,y),fill='black',width=3)
    return image.rotate(angle,resample=Image.Resampling.BICUBIC,expand=True,fillcolor='white')


@pytest.mark.parametrize('angle',[0,7,-7])
def test_auto_deskew_new_independent_grid(angle):
    suggestion=suggest_angle(grid_image(angle))
    assert suggestion['status']=='suggestion_requires_review',suggestion
    # PIL's positive angle is counterclockwise, correction is clockwise.
    assert suggestion['suggested_correction_degrees']==pytest.approx(angle,abs=.35)
    assert suggestion['support_ratio']>=.8


def test_blank_auto_is_unknown_and_not_rotated(tmp_path):
    image=Image.new('RGB',(300,200),'white')
    derived,r=process(image,{'deskew_mode':'auto','angle_degrees':0.,'median_filter':False},tmp_path)
    assert r['state']=='auto_not_applied' and r['auto_suggestion']['suggested_correction_degrees'] is None
    assert derived.tobytes()==image.tobytes()


def test_scale_independent_unit_conversion_and_conflict():
    body=scale_body();result=calculate(ScaleInput(**body),(360,240))
    assert result['scale_m_per_px']==pytest.approx(.06)  # 6000 mm /100 px =3 m /50 px
    body['references'][1]['length']=4
    result=calculate(ScaleInput(**body),(360,240))
    assert result['status']=='conflicting_references' and result['scale_m_per_px'] is None
    body['references']=body['references'][:1]
    assert calculate(ScaleInput(**body),(360,240))['status']=='single_reference_unverified'


def test_scale_declared_uncertainty_intersection_hand_answer():
    body=scale_body();body['references'][0].update(length_uncertainty=100,point_uncertainty_px=1)
    body['references'][1].update(length_uncertainty=.1,point_uncertainty_px=1)
    result=calculate(ScaleInput(**body),(360,240))
    low=max(5.9/102,2.9/52);high=min(6.1/98,3.1/48)
    assert result['interval_m_per_px']==pytest.approx([low,high])
    assert result['scale_m_per_px']==pytest.approx((low+high)/2)


def test_duplicate_reference_cannot_manufacture_agreement():
    body=scale_body();body['references'][1]=reference()
    with pytest.raises(core.ValidationError,match='Duplicate'):calculate(ScaleInput(**body),(360,240))
    body['references'][1]['start'],body['references'][1]['end']=body['references'][1]['end'],body['references'][1]['start']
    with pytest.raises(core.ValidationError,match='Duplicate'):calculate(ScaleInput(**body),(360,240))


@pytest.mark.parametrize('field,value',[('length',0),('length',-1),('length',True),('length','6000'),('length',float('inf')),('unit','inch'),('length_uncertainty',6000)])
def test_scale_invalid_fields(field,value):
    body=scale_body();body['references'][0][field]=value
    with pytest.raises(ValidationError):ScaleInput(**body)


@pytest.mark.parametrize('end,uncertainty', [((20,20),0),((21,20),1),((361,20),0)])
def test_scale_invalid_points_or_uncertainty(end,uncertainty):
    body=scale_body();body['references'][0].update(end={'x':end[0],'y':end[1]},point_uncertainty_px=uncertainty)
    with pytest.raises(core.ValidationError):calculate(ScaleInput(**body),(360,240))


def test_real_processed_ocr_scale_api_and_current_stale_binding(client):
    pid=create_project(client)['project_id'];base=f'/api/projects/{pid}/drawings'
    raw=(Path(__file__).resolve().parents[1]/'fixtures/drawing_gold/clean.png').read_bytes()
    fid=upload(client,pid,'new-processing.png',raw)
    response=client.post(base,json={'file_id':fid,'processing':{'deskew_mode':'manual','angle_degrees':7.,'median_filter':False}})
    assert response.status_code==201,response.text
    drawing=response.json();did=drawing['drawing_id'];url=base+'/'+did
    assert drawing['result']['processing']['transform']['angle_degrees_clockwise']==7
    assert any(c['text']=='6000 mm' for c in drawing['result']['candidates'])
    for c in drawing['result']['candidates']:
        for p,s in zip(c['polygon_px'],c['polygon_source_px']):assert math.dist(point(drawing['result']['processing']['transform']['source_to_preview'],s),p)<1e-6
    source=client.get(url+'/derivatives/source-preview.png');assert source.status_code==200
    assert hashlib.sha256(source.content).hexdigest()==drawing['result']['processing']['source_preview_sha256']
    assert client.get(url+'/derivatives/not-a-file.png').status_code==409
    body=scale_body(drawing['geometry_basis_hash']);response=client.post(url+'/scales',json=body)
    assert response.status_code==201,response.text
    scale=response.json();sid=scale['scale_id']
    measured=client.post(url+'/scales/'+sid+'/measure',json={'start':{'x':20,'y':20},'end':{'x':70,'y':20},'coordinates':'source'})
    assert measured.status_code==200 and measured.json()['length_m']==pytest.approx(3.)
    transform=drawing['result']['processing']['transform']
    a,b=[point(transform['source_to_preview'],p) for p in ((20,20),(70,20))]
    body_m={'start':dict(zip(('x','y'),a)),'end':dict(zip(('x','y'),b)),'coordinates':'preview'}
    assert client.post(url+'/scales/'+sid+'/measure',json=body_m).json()['length_m']==pytest.approx(3.)
    assert client.post(url+'/scales/'+sid+'/measure',json={'start':{'x':0,'y':0},'end':{'x':1,'y':1},'coordinates':'preview'}).status_code==409
    body['references'][1]['length']=4;conflict=client.post(url+'/scales',json=body).json()
    assert conflict['status']=='conflicting_references'
    assert client.post(url+'/scales/'+conflict['scale_id']+'/measure',json=body_m).status_code==409
    # A transcription review does not mutate the fixed raster geometry basis.
    c=drawing['result']['candidates'][0]
    assert client.post(url+'/review',json={'expected_revision':1,'candidate_id':c['candidate_id'],'decision':'unreadable','basis':'Synthetic test, original transcription uncertain.'}).status_code==200
    assert client.get(url+'/scales/'+sid).json()['status']=='consistent_declared_references'
    token=client.headers.pop('X-CSRF-Token')
    assert client.post(url+'/scales',json=body).status_code==403
    client.headers['X-CSRF-Token']=token
    other=create_project(client)['project_id']
    assert client.get(f'/api/projects/{other}/drawings/{did}/scales/{sid}').status_code==409
    domain=client.app.state.domain;assert domain.file_record(pid,fid)[1].read_bytes()==raw
    saved=domain.store.get('scale',sid)
    derivative=domain.store.root/drawing['derivatives']['source-preview.png']['path']
    derivative.write_bytes(b'isolated tamper')
    assert client.get(url+'/scales/'+sid).json()['result'] is None
    assert client.post(url+'/scales/'+sid+'/measure',json=body_m).status_code==409
    assert domain.store.get('scale',sid)==saved and domain.file_record(pid,fid)[1].read_bytes()==raw


def test_measure_refuses_race_with_drawing_withdrawal(monkeypatch):
    service=object.__new__(DrawingScales)
    monkeypatch.setattr(service,'view',lambda *args:{'status':'consistent_declared_references','basis_hash':'a'*64})
    class Drawing:
        def view(self,*args):return {'status':'stale','result':None}
    service.drawings=Drawing()
    with pytest.raises(core.ValidationError,match='changed'):
        service.measure('pid','did','sid',LengthInput(start={'x':0,'y':0},end={'x':1,'y':1},coordinates='source'))
