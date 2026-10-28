import math

import pytest
from pydantic import ValidationError
from PIL import Image, ImageDraw
from shapely.geometry import Polygon

from backend import core
from backend.measurements import SeriesImport, analyze, errors
from backend.model_schema import ModelDraft
from backend.floorplan import recognize
from test_model_workbench import project, upload, model_body
from test_damaged_central_components import options


def settings(**patch):
    return SeriesImport(**{**dict(file_id='file', building_ref='site/building', meter_boundary='plant electric meter',
        role='observed',quantity='electricity',timestamp_column='time',value_column='power',unit='W',
        interval_seconds=3600,source_note='Synthetic test, hourly average power with explicit UTC time'),**patch})


def test_missing_duplicates_gaps_negative_and_naive_dates_are_not_fixed(tmp_path):
    source=tmp_path/'meter.csv';source.write_text('time,power\n2024-01-01T00:00:00Z,1000\n2024-01-01T01:00:00Z,NA\n2024-01-01T01:00:00Z,2000\n2024-01-01T03:00:00Z,-2\n2024-01-01T04:00:00,3\n')
    summary,rows=analyze(source,settings())
    assert summary['issues']==dict(missing_value=1,invalid_or_negative_consumption=1,invalid_or_ambiguous_timestamp=1,duplicate_timestamps=1,absent_intervals=1)
    assert summary['imputed_rows']==0 and not summary['eligible_for_comparison']
    assert summary['valid_observed_energy_kwh'] is None and rows[1]['energy_kwh'] is None


def test_offsets_align_dst_fall_back_and_power_integrates(tmp_path):
    source=tmp_path/'meter.csv';source.write_text('time,power\n2024-11-03T01:00:00-04:00,1000\n2024-11-03T01:00:00-05:00,2000\n')
    result,rows=analyze(source,settings())
    assert result['eligible_for_comparison'] and result['valid_observed_energy_kwh']==3
    assert rows[0]['timestamp']=='2024-11-03T05:00:00+00:00'


@pytest.mark.parametrize('values',['1e309','-1','hello','1e308'])
def test_bad_numeric_values_cannot_be_finite_energy(tmp_path,values):
    source=tmp_path/'meter.csv';source.write_text('time,power\n2024-01-01T00:00:00Z,'+values+'\n')
    result,rows=analyze(source,settings())
    assert not result['eligible_for_comparison'] and rows[0]['energy_kwh'] is None


def test_error_metrics_known_nonzero_error_and_degrees_of_freedom():
    result=errors([(1,2),(3,5)])
    assert result['nmbe_percent']==75
    assert result['cvrmse_percent']==pytest.approx(math.sqrt(2.5)/2*100)
    assert errors([(1,2),(3,5)],1)['nmbe_percent']==150
    with pytest.raises(core.ValidationError):errors([(0,1)])
    with pytest.raises(core.ValidationError):errors([(1,2)],1)


def test_api_preserves_history_rejects_meter_mismatch_and_missing_holdout(client):
    pid=project(client);base=f'/api/projects/{pid}/measurements'
    def add(role, values, **kw):
        data='time,power\n'+''.join(f'2024-01-01T0{i}:00:00Z,{v}\n' for i,v in enumerate(values))
        fid=upload(client,pid,role+'.csv',data.encode())
        response=client.post(base,json=settings(role=role,file_id=fid,**kw).model_dump())
        assert response.status_code==201,response.text
        return response.json()['measurement_id']
    a=add('observed',[1000,2000,3000,4000]);b=add('prediction',[1100,2200,3600,4800])
    body=dict(observed_id=a,prediction_id=b,holdout_start='2024-01-01T02:00:00Z',source_note='Chronological test split, no physical model fit')
    r=client.post(base+'/compare',json=body);assert r.status_code==201,r.text
    assert r.json()['training']['nmbe_percent']==pytest.approx(10)
    assert r.json()['holdout']['nmbe_percent']==pytest.approx(20)
    assert not r.json()['calibrated']
    wrong=add('prediction',[1000,2000,3000,4000],meter_boundary='whole building electricity')
    assert client.post(base+'/compare',json={**body,'prediction_id':wrong}).status_code==409
    assert client.post(base+'/compare',json={**body,'holdout_start':'2025-01-01T00:00:00Z'}).status_code==409
    other=project(client)
    assert client.post(f'/api/projects/{other}/measurements/compare',json=body).status_code==404
    client.headers.pop('X-CSRF-Token')
    assert client.post(base+'/compare',json=body).status_code==403


def test_pixel_island_does_not_delete_main_room_or_silently_fill_void(tmp_path):
    path=tmp_path/'room.png';im=Image.new('RGB',(500,400),'white');draw=ImageDraw.Draw(im)
    draw.rectangle((20,20,480,380),outline='black',width=10)
    draw.rectangle((150,130,210,190),fill='black');im.save(path)
    result=recognize(path,options())
    room=max(result['rooms'],key=lambda r:Polygon(r['polygon'],r['holes']).area)
    assert room['holes'] and room['drawing']['interior_islands_px']
    assert Polygon(room['polygon'],room['holes']).area < Polygon(room['polygon']).area-1
    body=model_body();body['rooms']=[room]
    with pytest.raises(ValidationError,match='内部线岛'):ModelDraft(**body)
    body['rooms'][0]['drawing']['interior_review_note']='Control obstruction retained as excluded footprint, not field evidence'
    assert ModelDraft(**body).rooms[0].drawing.interior_review_note


@pytest.mark.parametrize('csv_text', ['time,power\n"unclosed,1\n', 'time,power\n2024-01-01T00:00:00Z,'+'1'*140000+'\n', 'time, \n2024-01-01T00:00:00Z,1\n'],ids=['unclosed-quote','oversized-field','blank-header'])
def test_corrupt_csv_is_actionable_validation_error(tmp_path,csv_text):
    source=tmp_path/'meter.csv';source.write_text(csv_text,encoding='utf-8')
    with pytest.raises(core.ValidationError,match='CSV'):
        analyze(source,settings())


def test_fallback_aperture_stays_on_oblique_plane(monkeypatch):
    from honeybee.face import Face
    from ladybug_geometry.geometry3d import Face3D, Point3D
    from backend.ratio_glazing import _ratio_apertures
    face=Face('Oblique',Face3D([Point3D(0,0,0),Point3D(10,0,10),Point3D(0,5,5)]))
    monkeypatch.setattr(Face,'apertures_by_ratio',lambda *a,**k:None)
    _ratio_apertures(face,.2)
    assert sum(a.area for a in face.apertures)==pytest.approx(face.area*.2)
    assert face.check_sub_faces_valid(.001)==''
    assert all(face.geometry.plane.distance_to_point(v)<1e-8 for a in face.apertures for v in a.geometry.vertices)
