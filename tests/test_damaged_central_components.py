import json

import numpy as np
import pytest
from PIL import Image, ImageDraw
from pydantic import ValidationError
from shapely.geometry import Polygon

from backend import core, model_export
from backend.central_hvac import CentralSystem
from backend.components import ComponentBuild, source_meshes
from backend.floorplan import extract, recognize
from backend.model_import import ImportDiagnosticError
from backend.model_schema import ImportOptions, ModelDraft
from test_drawing_thermal import operation
from test_model_workbench import model_body, project, upload


def central():
    return dict(kind='four_pipe_fan_coil', basis='design_scenario', source_note='Authored control design days and system, not installed equipment.',
        design_days=[dict(kind='winter',month=1,day=21,dry_bulb_c=-19.,daily_range_c=0.,wet_bulb_c=-19.,pressure_pa=82000.,wind_speed_m_s=4.,wind_direction_deg=270.,sky_clearness=0.),
                     dict(kind='summer',month=7,day=21,dry_bulb_c=32.,daily_range_c=15.,wet_bulb_c=16.,pressure_pa=82000.,wind_speed_m_s=4.,wind_direction_deg=230.,sky_clearness=1.)],
        chiller_cop=3.2,condenser='AirCooled',boiler_efficiency=.8,boiler_fuel='NaturalGas',
        chilled_water_c=7.,chilled_water_delta_c=5.,hot_water_c=60.,hot_water_delta_c=11.,
        chilled_pump_head_pa=100000.,hot_pump_head_pa=100000.,fan_pressure_pa=75.,fan_total_efficiency=.6,fan_motor_efficiency=.9,curve_basis='native_reference')


def central_model():
    body=model_body()
    body['thermal'].update(operation=operation(),central_system=central())
    body['thermal']['operation'].update(sensible_recovery=0.,latent_recovery=0.)
    return body


def scan(path, *, faded=False, angle=0., broken=False):
    image=Image.new('RGB',(620,360),'white')
    draw=ImageDraw.Draw(image)
    color='#cecece' if faded else '#333333'
    draw.rectangle((40,40,580,320),outline=color,width=12)
    draw.rectangle((300,40,312,320),fill=color)
    if broken:
        draw.rectangle((296,150,316,160),fill='white')
    image.rotate(angle,fillcolor='white').save(path)


def options(**kwargs):
    return ImportOptions(file_id='control',mode='damaged_raster',scale_to_m=.02,
                         scale_basis='Author control: 50 pixels equal one metre',ocr_labels=False,**kwargs)


def test_faded_skewed_scan_recovers_two_rooms_in_original_coordinates(tmp_path):
    path=tmp_path/'skew.png'
    scan(path,faded=True,angle=5.)
    result=recognize(path,options())
    assert len(result['rooms'])==2
    analysis=result['metadata']['damage_analysis']
    assert abs(analysis['deskew']['applied_degrees']+5)<.3
    assert analysis['coordinate_transform']['scale_changed'] is False
    assert not analysis['coverage_complete']
    # Inverse mapping must place overlays on the rotated source, not rectified coordinates.
    import cv2
    matrix=cv2.getRotationMatrix2D((310,180),5,1)
    known=np.array([[52.,52.,1.],[299.,52.,1.],[299.,307.,1.],[52.,307.,1.]])@matrix.T
    expected=Polygon(known)
    predicted=[Polygon(r['drawing']['polygon_px']) for r in result['rooms']]
    assert max(expected.intersection(p).area/expected.union(p).area for p in predicted)>.96
    assert all(r['conditioned'] is None and r['include_floor_area'] is None for r in result['rooms'])


def test_small_break_is_explicit_proposal_not_observed_wall(tmp_path):
    path=tmp_path/'broken.png';scan(path,broken=True)
    without=recognize(path,options())
    repaired=recognize(path,options(damage_gap_m=.3))
    assert len(without['rooms'])==1 and len(repaired['rooms'])==2
    repairs=repaired['metadata']['damage_analysis']['repairs']
    assert repairs and all(r['status']=='INFERRED_REQUIRES_REVIEW' for r in repairs)
    assert repaired['rooms'][0]['drawing']['damage_analysis_hash']


def test_blank_missing_sheet_fails_with_diagnostics(tmp_path):
    path=tmp_path/'blank.png';Image.new('RGB',(300,300),'white').save(path)
    with pytest.raises(ImportDiagnosticError) as exc:
        recognize(path,options(damage_gap_m=.2))
    assert not exc.value.diagnostics['damage_analysis']['coverage_complete']
    assert not exc.value.diagnostics['damage_analysis']['repairs']


def test_engineer_bridge_is_bounded_and_keeps_source_basis(tmp_path):
    path=tmp_path/'wide_door.png';scan(path)
    im=Image.open(path);ImageDraw.Draw(im).rectangle((296,100,316,200),fill='white');im.save(path)
    before=recognize(path,options())
    assert len(before['rooms'])==1
    opts=options(manual_bridges_px=[(306,90,306,210)],manual_bridge_basis='Author control: known door endpoints, partition for volume only')
    after=recognize(path,opts)
    assert len(after['rooms'])==2
    manual=after['metadata']['damage_analysis']['manual_bridges']
    assert manual[0]['source_endpoints_px']==[[306,90],[306,210]]
    assert manual[0]['status']=='ASSUMED_REQUIRES_REVIEW'
    with pytest.raises(core.ValidationError,match='裁剪'):
        recognize(path,opts.model_copy(update={'crop_px':(330,20,600,340)}))
    with pytest.raises(ValidationError):options(manual_bridges_px=[(306,90,306,210)])


def test_recognition_cache_binds_source_and_options_and_is_not_mutable(tmp_path):
    path=tmp_path/'source.png';scan(path)
    first=extract(path,options());second=extract(path,options())
    assert not first['metadata']['recognition_cache']['hit']
    assert second['metadata']['recognition_cache']['hit']
    second['rooms'][0]['name']='caller mutation'
    assert extract(path,options())['rooms'][0]['name']!='caller mutation'
    assert not extract(path,options(deskew=False))['metadata']['recognition_cache']['hit']
    scan(path,faded=True)
    changed=extract(path,options())
    assert not changed['metadata']['recognition_cache']['hit']
    assert changed['metadata']['recognition_cache']['source_sha256']!=first['metadata']['recognition_cache']['source_sha256']


@pytest.mark.parametrize('patch',[
    {'design_days':[]},{'boiler_efficiency':0.},{'fan_total_efficiency':.95,'fan_motor_efficiency':.8},
    {'condenser':'WaterCooled'},{'basis':'documented_design'}, {'source_file_id':'unpaired'},
])
def test_central_missing_inputs_are_rejected(patch):
    with pytest.raises(ValidationError):CentralSystem.model_validate({**central(),**patch})


def test_central_native_topology_and_mode_conflicts():
    body=central_model();model=ModelDraft(**body).model_dump()
    text,_=model_export.idf(model)
    assert 'HVACTemplate:Zone:FanCoil' in text and 'HVACTemplate:Plant:Chiller' in text
    assert 'HVACTemplate:Plant:Boiler' in text and 'SizingPeriod:DesignDay' in text
    assert 'ZoneHVAC:IdealLoadsAirSystem' not in text
    assert model_export.scope(model)=='central_chiller_boiler_energy'
    assert len(model_export.central_hvac.topology(model)['terminal_zone_ids'])==2
    body['thermal']['operation']['sensible_recovery']=.5
    with pytest.raises(ValidationError,match='回收'):ModelDraft(**body)


def test_geometry_retry_tightens_without_filling_a_thin_recess():
    from backend.model_geometry import thermal_geometry_model
    body=model_body();body['rooms']=body['rooms'][:1]
    body['rooms'][0]['polygon']=[(0.,0.),(4.,0.),(4.,4.),(2.005,4.),(2.005,2.),(2.,2.),(2.,4.),(0.,4.)]
    body['thermal']['geometry_tolerance_m']=.02
    model=ModelDraft(**body).model_dump()
    with pytest.raises(core.ValidationError):thermal_geometry_model(model)
    model['thermal']['geometry_tolerance_policy']='bounded_retry'
    derived,report=thermal_geometry_model(model)
    assert report['tolerance_m']<=.02
    assert report['attempts'] or any('normalization_policy' in row for row in report['rooms'])
    assert Polygon(derived['rooms'][0]['polygon']).symmetric_difference(Polygon(model['rooms'][0]['polygon'])).area<.0001


def test_ratio_glazing_preserves_facade_total_with_tiny_numerical_fragments():
    from backend.ratio_glazing import assign
    from honeybee.face import Face
    from honeybee.facetype import face_types
    from ladybug_geometry.geometry3d import Face3D,Point3D
    faces=[Face('large',Face3D(tuple(Point3D(*p) for p in [(0,0,0),(4,0,0),(4,0,3),(0,0,3)])),face_types.wall),
           Face('tiny',Face3D(tuple(Point3D(*p) for p in [(4,0,0),(4.001,0,0),(4.001,0,3),(4,0,3)])),face_types.wall)]
    report=assign({'R1':faces},.2)
    assert report[0]['actual_glazing_m2']==pytest.approx((12+.003)*.2,abs=1e-6)
    assert faces[1].apertures  # Narrow numerical rectangles remain expressible.
    assert report[0]['actual_glazing_m2']==pytest.approx(sum(a.area for f in faces for a in f.apertures))


def test_central_import_binds_actual_source_and_project(client):
    pid=project(client);base='/api/projects/'+pid
    fid=upload(client,pid,'plant.json',json.dumps(central()).encode())
    response=client.post(base+'/model/central-import',json={'file_id':fid})
    assert response.status_code==200,response.text
    parsed=response.json()['central_system']
    assert parsed['source_file_id']==fid and parsed['source_file_hash']
    body=central_model();body['thermal']['central_system']=parsed
    assert client.put(base+'/model',json=body).status_code==200
    assert client.get(base+'/model').json()['sources'][0]['file_id']==fid
    another=project(client)
    assert client.post('/api/projects/'+another+'/model/central-import',json={'file_id':fid}).status_code==409
    parsed['source_file_hash']='0'*64;body['expected_revision']=1
    assert client.put(base+'/model',json=body).status_code==409


def component_ifc():
    import ifcopenshell
    import ifcopenshell.api
    doc=ifcopenshell.file.from_string(model_export.ifc(ModelDraft(**model_body()).model_dump()))
    context=next(c for c in doc.by_type('IfcGeometricRepresentationSubContext') if c.ContextIdentifier=='Body')
    floor=doc.by_type('IfcBuildingStorey')[0]
    for kind in ('IfcWall','IfcDoor','IfcFurnishingElement','IfcFlowTerminal'):
        entity=ifcopenshell.api.run('root.create_entity',doc,ifc_class=kind,name='Authored '+kind)
        ifcopenshell.api.run('spatial.assign_container',doc,products=[entity],relating_structure=floor)
        representation=ifcopenshell.api.run('geometry.add_wall_representation',doc,context=context,length=1.,height=1.,thickness=.2)
        ifcopenshell.api.run('geometry.assign_representation',doc,product=entity,representation=representation)
    missing=ifcopenshell.api.run('root.create_entity',doc,ifc_class='IfcDoor',name='Known missing representation')
    ifcopenshell.api.run('spatial.assign_container',doc,products=[missing],relating_structure=floor)
    return doc.to_string()


def test_source_components_keep_actual_mesh_and_missing_inventory(tmp_path):
    path=tmp_path/'control.ifc';path.write_text(component_ifc(),encoding='utf-8')
    output=source_meshes(path,ComponentBuild(file_id='control'))
    assert output['in_scope_count']==5 and output['status_counts']=={'SOURCE_MESH':4,'NO_REPRESENTATION':1}
    assert output['category_counts']['furniture']==1 and output['category_counts']['services']==1
    source=next(r for r in output['components'] if r['ifc_type']=='IfcWall')
    assert source['triangles'] and source['thermal_mapping']=='NOT_BOUND'
    translated=source_meshes(path,ComponentBuild(file_id='control',origin_m=(100.,0.,0.)))
    wall=next(r for r in translated['components'] if r['source_id']==source['source_id'])
    assert np.array(wall['vertices'])[:,0]==pytest.approx(np.array(source['vertices'])[:,0]-100)


def test_component_api_retains_scope_auth_and_source_integrity(client):
    pid=project(client);base='/api/projects/'+pid
    fid=upload(client,pid,'controlled.ifc',component_ifc().encode())
    result=client.post(base+'/components',json={'file_id':fid})
    assert result.status_code==201,result.text
    record=result.json();asset=record['component_id']
    first=client.get(base+'/components/'+asset+'/geometry?limit=2').json()
    assert first['total']==5 and len(first['components'])==2 and first['remaining']==3
    furnishings=client.get(base+'/components/'+asset+'/geometry?category=furniture').json()
    assert furnishings['total']==1
    assert client.get(base+'/components/'+asset+'/geometry?limit=301').status_code==422
    another=project(client)
    assert client.get('/api/projects/'+another+'/components/'+asset+'/geometry').status_code==409
    source=client.app.state.domain.store.get('file',fid)
    path=client.app.state.domain.store.root/source['path'];path.write_bytes(b'tampered')
    assert client.get(base+'/components/'+asset+'/geometry').status_code==409
