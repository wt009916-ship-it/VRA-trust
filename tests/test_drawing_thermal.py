import io

import ezdxf
import pytest
from PIL import Image, ImageDraw
from pydantic import ValidationError
from shapely.geometry import Polygon

from backend import core, honeybee_bridge, model_export, model_import
from backend.floorplan import extract
from backend.model_schema import ImportOptions, ModelDraft, Operation
from test_model_workbench import ASSEMBLIES, model_body, project, upload


def operation():
    return dict(weekday=[float(8 <= h < 18) for h in range(24)], weekend=[0.]*24,
                outdoor_air_l_s_person=5., outdoor_air_l_s_m2=.3, sensible_recovery=.6,
                latent_recovery=0., heating_setback_c=12., cooling_setback_c=32.,
                source_note='Synthetic schedule and ventilation scenario for automated tests.')


def heat_pump():
    return dict(cooling_w_m2=120., heating_w_m2=150., airflow_l_s_m2=6.5,
                cooling_cop=3.2, heating_cop=3.5, sensible_heat_ratio=.75,
                fan_pressure_pa=150., fan_total_efficiency=.6, fan_motor_efficiency=.9,
                supplemental_w_m2=150., minimum_outdoor_c=-15., minimum_cooling_outdoor_c=0.,
                source_note='Explicit test assumptions, not a manufacturer product or calibrated equipment.')


def test_raster_requires_scale_source_and_bounded_crop():
    for fields in ({}, {'scale_to_m': .02}, {'scale_to_m': .02, 'scale_basis': 'tiny'},
                   {'scale_to_m': .02, 'scale_basis': 'Known scale test', 'crop_px': [20, 0, 10, 40]}):
        with pytest.raises(ValidationError):
            ImportOptions(file_id='x', mode='local_raster', **fields)
    with pytest.raises(ValidationError):
        Operation(**{**operation(), 'weekday': [1.1]*24})


def test_local_raster_rooms_and_gap_provenance(tmp_path):
    # Synthetic fixture; public drawing measurements belong to the external benchmark.
    image = Image.new('RGB', (620, 360), 'white')
    draw = ImageDraw.Draw(image)
    draw.rectangle((40, 40, 580, 320), outline='#555555', width=12)
    draw.rectangle((300, 40, 312, 150), fill='#555555')
    draw.rectangle((300, 180, 312, 320), fill='#555555')
    path = tmp_path/'plan.png'
    image.save(path)
    opts = ImportOptions(file_id='x', mode='local_raster', scale_to_m=.02, closure_m=.8,
                         scale_basis='Synthetic fixture: 50 pixels correspond to one metre')
    result = extract(path, opts)
    assert len(result['rooms']) == 2
    assert all(r['conditioned'] is None and r['include_floor_area'] is None for r in result['rooms'])
    assert all(r['drawing']['closure_m'] == .8 and r['drawing']['annotated_area_m2'] is None for r in result['rooms'])
    assert result['metadata']['ocr']['external_upload'] is False
    before = extract(path, opts.model_copy(update={'closure_m': 0.}))
    assert len(before['rooms']) == 1  # Unclosed door connects the two air regions.


def test_dxf_transformed_nested_blocks_and_curve(tmp_path):
    doc = ezdxf.new('R2010')
    doc.units = 6
    block = doc.blocks.new('ROOM')
    block.add_lwpolyline([(0, 0), (4, 0), (4, 3), (0, 3)], close=True)
    group = doc.blocks.new('GROUP')
    group.add_blockref('ROOM', (2, 1))
    doc.modelspace().add_blockref('GROUP', (10, 20), dxfattribs={'rotation': 90, 'layer': 'ROOMS'})
    doc.modelspace().add_circle((30, 30), radius=2, dxfattribs={'layer': 'ROOMS'})
    path = tmp_path/'block.dxf'
    doc.saveas(path)
    result = model_import.dxf(path, ImportOptions(file_id='x', layer='ROOMS'))
    areas = sorted(Polygon(r['polygon']).area for r in result['rooms'])
    assert len(areas) == 2
    assert areas[0] == pytest.approx(12.)
    assert areas[1] == pytest.approx(12.566, rel=.01)
    bounds = Polygon(result['rooms'][0]['polygon']).bounds
    assert bounds == pytest.approx((6, 22, 9, 26))


def test_wall_gap_partial_contacts_are_closed_and_reciprocal():
    body = model_body()
    body['rooms'][1]['polygon'] = [[5.3, 2], [10, 2], [10, 6], [5.3, 6]]
    body['thermal']['adjacency_gap_m'] = .35
    model = ModelDraft.model_validate(body).model_dump()
    faces = model_export.geometry(model)
    audit = honeybee_bridge.audit(model, faces)
    assert audit['passed'], audit['issues']
    contact = [s for s in faces if s['boundary'] == 'Surface']
    assert contact
    from backend.model_geometry import frame
    lookup = {s['name']: s for s in faces}
    for face in contact:
        other = lookup[face['other']]
        assert other['other'] == face['name']
        assert frame(face['points'])['poly'].area == pytest.approx(frame(other['points'])['poly'].area)
        assert '0.300000 m' in face['boundary_basis']
    # Independent audit must actually reject a missing piece of the envelope.
    broken = [s for s in faces if s['name'] != next(s['name'] for s in faces if s['kind'] == 'Roof')]
    assert not honeybee_bridge.audit(model, broken)['passed']


def test_honeybee_schedules_ventilation_and_geometry_export(client):
    pid = project(client)
    base = f'/api/projects/{pid}'
    body = model_body()
    body['thermal']['operation'] = operation()
    saved = client.put(base+'/model', json=body)
    assert saved.status_code == 200, saved.text
    check = client.get(base+'/model/validate').json()
    assert check['geometry_review']['independent_audit']['passed']
    text = client.get(base+'/model/export.idf').text
    assert 'Schedule:Year' in text and 'Occupied_Weekend' in text
    assert 'DesignSpecification:OutdoorAir' in text and 'R1_OA..R1' in text
    assert 'OutdoorAir:Node' in text and 'Sensible' in text
    assert text.count('Temperature,') > 0
    data = client.get(base+'/model/geometry.hbjson').json()
    from honeybee.model import Model
    hb = Model.from_dict(data)
    assert len(hb.rooms) == 2
    assert hb.check_rooms_solid(raise_exception=False) == ''
    image = io.BytesIO()
    Image.new('RGB', (100, 60), 'white').save(image, format='PNG')
    fid = upload(client, pid, 'source.png', image.getvalue())
    assert client.get(base+f'/files/{fid}/plan-preview').status_code == 200
    other = project(client)
    assert client.get(f'/api/projects/{other}/files/{fid}/plan-preview').status_code == 409
    assert client.get(base+f'/files/{fid}/plan-preview?page=501').status_code == 409


def test_ifc_reconstruction_rejects_missing_quantities(tmp_path):
    import ifcopenshell
    from backend.ifc_footprint import reconstruct
    body = ModelDraft.model_validate(model_body()).model_dump()
    document = ifcopenshell.file.from_string(model_export.ifc(body))
    space = document.by_type('IfcSpace')[0]
    with pytest.raises(ValueError, match='FootPrint'):
        reconstruct(document, space)


def test_ifc_footprint_quantity_reconstruction_and_conflict():
    import ifcopenshell
    from ifcopenshell.util.unit import calculate_unit_scale
    from backend.ifc_footprint import reconstruct
    from backend.model_schema import Reconstruction
    doc = ifcopenshell.file.from_string(model_export.ifc(ModelDraft.model_validate(model_body()).model_dump()))
    space = doc.by_type('IfcSpace')[0]
    scale = calculate_unit_scale(doc)
    curve = doc.createIfcPolyline([doc.createIfcCartesianPoint((x/scale, y/scale))
                                   for x, y in [(0., 0.), (4., 0.), (4., 3.), (0., 3.), (0., 0.)]])
    old = space.Representation.Representations[0]
    rep = doc.createIfcShapeRepresentation(old.ContextOfItems, 'FootPrint', 'Curve2D', [curve])
    space.Representation.Representations = [rep]
    quantities = [doc.createIfcQuantityLength('Height', None, None, 3./scale, None),
                  doc.createIfcQuantityArea('NetFloorArea', None, None, 12./calculate_unit_scale(doc, 'AREAUNIT'), None),
                  doc.createIfcQuantityVolume('NetVolume', None, None, 36./calculate_unit_scale(doc, 'VOLUMEUNIT'), None)]
    qset = doc.createIfcElementQuantity(ifcopenshell.guid.new(), None, 'MeasuredSource', None, None, quantities)
    doc.createIfcRelDefinesByProperties(ifcopenshell.guid.new(), None, None, None, [space], qset)
    sections, provenance = reconstruct(doc, space)
    assert Polygon(sections[0]['polygon']).area == pytest.approx(12.)
    assert sections[0]['height_m'] == 3.
    assert Reconstruction.model_validate(provenance).volume_error_percent == 0
    quantities[2].VolumeValue *= .8
    with pytest.raises(ValueError, match='体积'):
        reconstruct(doc, space)


def test_mixed_equipment_and_ideal_scopes_cannot_rank():
    from backend.domain import Domain
    from types import SimpleNamespace
    domain = object.__new__(Domain)
    jobs = {'ideal': {'evidence_snapshot': {'idf': {'value': {'scope': 'ideal_thermal_loads'}}}},
            'equipment': {'evidence_snapshot': {'idf': {'value': {'scope': 'packaged_heat_pump_electricity'}}}}}
    domain.store = SimpleNamespace(job=lambda rid: jobs[rid])
    domain.view = lambda rid: {'status': 'succeeded'}
    with pytest.raises(core.ValidationError, match='口径不同'):
        domain.compare(list(jobs))


@pytest.mark.engine
def test_advanced_schedule_native_energyplus(tmp_path):
    try:
        core.engine_path()
    except core.ValidationError:
        pytest.skip('EnergyPlus not installed')
    import subprocess
    body = model_body()
    body['thermal']['operation'] = operation()
    body['thermal']['constructions'] = ASSEMBLIES
    text, _ = model_export.idf(ModelDraft.model_validate(body).model_dump())
    path = tmp_path/'test.idf'
    path.write_text(text)
    weather = core.relative_file(core.ROOT, core.load_case('reference_5zone')['weather'])
    result = subprocess.run([str(core.engine_path()), '-w', str(weather), '-d', str(tmp_path/'output'), str(path)],
                            capture_output=True, timeout=180)
    errors = (tmp_path/'output/eplusout.err').read_text()
    assert result.returncode == 0, errors
    assert '** Severe' not in errors
    assert '** Warning' not in errors


@pytest.mark.engine
def test_heat_pump_native_expansion_and_cop_response(tmp_path):
    try:
        core.engine_path()
    except core.ValidationError:
        pytest.skip('EnergyPlus not installed')
    import copy
    body = model_body()
    body['thermal'].update(operation=operation(), heat_pump=heat_pump(), constructions=ASSEMBLIES)
    with pytest.raises(ValidationError, match='热回收'):
        ModelDraft.model_validate(body)
    body['thermal']['operation']['sensible_recovery'] = 0.
    case = copy.deepcopy(core.load_case('reference_5zone'))
    case['weather'] = str(core.relative_file(core.ROOT, case['weather']))
    # Core confines all paths to the fixture root; only the IDF is newly generated.
    import shutil
    shutil.copy2(case['weather'], tmp_path/'weather.epw')
    case['weather'] = 'weather.epw'
    results = []
    for i, cop in enumerate((2., 4.)):
        body['thermal']['heat_pump'].update(heating_cop=cop, cooling_cop=cop)
        text, _ = model_export.idf(ModelDraft.model_validate(body).model_dump())
        if i:
            from backend.decision import replace_material
            from backend.robustness import set_conductivity
            layer = body['thermal']['constructions']['wall'][0]
            text, _ = replace_material(text, 'Wall_L1', layer, layer['thickness_m'])
            text = set_conductivity(text, 'Wall_L1', layer['conductivity_w_mk'])
        (tmp_path/'model.idf').write_text(text)
        case['schemes'] = [{'scheme_id': 'baseline', 'name': 'PTHP test', 'model': 'model.idf', 'cost': None}]
        rd = tmp_path/f'run{i}'
        result = core.run_simulation(case['case_id'], 'baseline', 'reference_scenario', rd,
                                     case_override=case, file_root=tmp_path)
        assert result['status'] == 'succeeded', result
        verified, manifest, _ = core.read_validated(rd, check_current=False)
        assert manifest['fingerprints']['expander']
        expanded = (rd/'input/expanded.idf').read_text()
        assert 'ZoneHVAC:PackagedTerminalHeatPump' in expanded
        assert 'HVACTemplate:Zone:PTHP' not in (rd/'input/fixed.idf').read_text()
        assert manifest['warnings'] == 0
        assert verified['metrics']['annual_days'] == 365
        assert result['metrics']['energy_by_carrier_kwh']['District Heating'] == 0
        results.append(result['metrics']['energy_by_carrier_kwh']['Electricity'])
    assert results[1] < results[0] * .9, results
