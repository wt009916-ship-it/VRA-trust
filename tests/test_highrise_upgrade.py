import copy
import csv
import io

import pytest
from pydantic import ValidationError

from backend import core, model_export, model_geometry, model_import, solid_geometry
from backend.equipment_inputs import COLUMNS
from backend.model_schema import ImportOptions, ModelDraft
from test_drawing_thermal import operation
from test_model_workbench import model_body, project, upload


def sloped_room():
    vertices = [(0., 0., 0.), (4., 0., 0.), (4., 4., 0.), (0., 4., 0.),
                (0., 0., 3.), (4., 0., 5.), (4., 4., 5.), (0., 4., 3.)]
    quads = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    triangles = [t for a, b, c, d in quads for t in [(a, b, c), (a, c, d)]]
    shell = solid_geometry.from_mesh(vertices, triangles)
    for f in shell:
        f.update(classification='NOTDEFINED', source_id='controlled_source_solid')
    return dict(id='Slope', name='Controlled sloping roof', polygon=[(0., 0.), (4., 0.), (4., 4.), (0., 4.)],
                elevation_m=0., height_m=5., shell=shell, source_locator='Controlled analytic 64 m3 solid')


def test_sloped_shell_volume_and_ifc_roundtrip(tmp_path):
    body = model_body()
    body['rooms'] = [sloped_room()]
    model = ModelDraft(**body).model_dump()
    assert model_geometry.room_volume(model['rooms'][0]) == pytest.approx(64)
    text, _ = model_export.idf(model)
    assert '80.0' not in next(chunk for chunk in text.split(';') if chunk.strip().startswith('Zone,'))
    path = tmp_path/'source.ifc'
    path.write_text(model_export.ifc(model), encoding='utf-8')
    candidate = model_import.ifc(path, ImportOptions(file_id='controlled'))
    assert candidate['rooms'][0]['shell']
    assert model_geometry.room_volume(candidate['rooms'][0]) == pytest.approx(64, abs=1e-5)


def test_shell_open_or_mismatched_projection_is_rejected():
    room = sloped_room()
    room['shell'].pop()
    with pytest.raises(ValidationError):
        ModelDraft(rooms=[room], review_note='Controlled invalid mesh test')


def test_whole_building_140_spaces_is_not_truncated(tmp_path):
    rooms = [dict(id='R'+str(i), name='Floor '+str(i), polygon=[(0., 0.), (5., 0.), (5., 8.), (0., 8.)],
                  elevation_m=float(i*3), height_m=3.) for i in range(140)]
    model = ModelDraft(rooms=rooms, review_note='Controlled 140-storey capacity input').model_dump()
    path = tmp_path/'whole.ifc'
    path.write_text(model_export.ifc(model), encoding='utf-8')
    result = model_import.ifc(path, ImportOptions(file_id='controlled'))
    assert len(result['rooms']) == 140
    assert len({r['storey_id'] for r in result['rooms']}) == 140


def source_window_model():
    body = model_body()
    body['rooms'] = [body['rooms'][0]]
    body['thermal']['window_geometry'] = 'source'
    body['rooms'][0]['source_openings'] = [{'source_id': 'controlled_window',
        'points': [(0., 1., 1.), (0., 1., 2.), (0., 3., 2.), (0., 3., 1.)],
        'source_area_m2': 2., 'projection_offset_m': 0.}]
    return body


def test_source_window_area_is_preserved_and_outside_is_rejected():
    from backend.honeybee_bridge import geometry_model
    model = ModelDraft(**source_window_model()).model_dump()
    hb = geometry_model(model, model_export.geometry(model))
    assert sum(a.area for a in hb.apertures) == pytest.approx(2)
    bad = source_window_model()
    bad['rooms'][0]['source_openings'][0]['points'][0] = (0., -1., 1.)
    with pytest.raises(core.ValidationError, match='完整保留'):
        model_export.idf(ModelDraft(**bad).model_dump())


def test_real_overlap_is_not_overridden_by_source_boundary_resolution():
    body = source_window_model()
    second = copy.deepcopy(body['rooms'][0]['source_openings'][0])
    second['source_id'] = 'different_real_overlapping_window'
    body['rooms'][0]['source_openings'].append(second)
    with pytest.raises(core.ValidationError, match='overlap'):
        model_export.idf(ModelDraft(**body).model_dump())


def nameplate_row(zone):
    return dict(zone_id=zone, system_type='PTHP', manufacturer='Controlled fixture', model='No real product claim',
        cooling_capacity_w=5000., heating_capacity_w=6000., airflow_m3_s=.26, cooling_cop=3.2, heating_cop=3.5,
        sensible_heat_ratio=.75, fan_pressure_pa=150., fan_total_efficiency=.6, fan_motor_efficiency=.9,
        supplemental_capacity_w=6000., minimum_outdoor_c=-15., minimum_cooling_outdoor_c=0.,
        curve_basis='native_reference', source_note='Explicit synthetic nameplate test, not installed equipment.', curves_json='')


def test_nameplate_csv_binds_units_files_and_exact_zone_coverage(client):
    pid = project(client)
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=COLUMNS)
    writer.writeheader()
    writer.writerows([nameplate_row('R1'), nameplate_row('R2')])
    fid = upload(client, pid, 'equipment.csv', stream.getvalue().encode())
    result = client.post(f'/api/projects/{pid}/model/equipment-import', json={'file_id': fid})
    assert result.status_code == 200, result.text
    body = model_body()
    body['thermal']['operation'] = {**operation(), 'sensible_recovery': 0.}
    body['equipment'] = result.json()['equipment']
    saved = client.put(f'/api/projects/{pid}/model', json=body)
    assert saved.status_code == 200, saved.text
    model = saved.json()
    assert model['sources'][0]['file_id'] == fid
    text, _ = model_export.idf(model)
    rows = [r for r in text.split(';') if r.strip().startswith('HVACTemplate:Zone:PTHP,')]
    assert len(rows) == 2 and model_export.scope(model) == 'packaged_heat_pump_electricity'
    published = client.post(f'/api/projects/{pid}/model/publish', json={'revision': model['revision'],
        'responsible_person': 'Controlled software test',
        'review_note': 'Synthetic source equipment input, not installed performance verification'})
    assert published.status_code == 200, published.text
    assert 'PTHP耗电' in published.json()['evidence']['name']
    assert published.json()['binding']['scope'] == 'packaged_heat_pump_electricity'
    bad = copy.deepcopy(body)
    bad['equipment'].pop()
    assert client.put(f'/api/projects/{pid}/model', json=bad).status_code == 422
    file = client.app.state.domain.store.get('file', fid)
    (client.app.state.domain.store.root/file['path']).write_text('changed', encoding='utf-8')
    assert 'hash' in str(client.get(f'/api/projects/{pid}/model/validate').json()['blockers']).lower()


def test_geometry_cache_cannot_be_mutated_by_callers():
    model = ModelDraft(**model_body()).model_dump()
    first = model_export.geometry(model)
    first[0]['points'][0][0] = 999.
    second = model_export.geometry(model)
    assert second[0]['points'][0][0] != 999.


def test_compute_budget_is_bounded(monkeypatch):
    monkeypatch.setenv('VRA_ENGINE_TIMEOUT_SECONDS', '1200')
    assert core.engine_timeout_seconds() == 1200
    monkeypatch.setenv('VRA_ENGINE_TIMEOUT_SECONDS', '999999')
    with pytest.raises(core.ValidationError):
        core.engine_timeout_seconds()


@pytest.mark.parametrize('timeout', [None, 30])
def test_actual_simulation_entry_serializes_default_and_explicit_budgets(monkeypatch, tmp_path, timeout):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    first_entered, second_attempted, second_entered, release = (threading.Event() for _ in range(4))
    call_lock = threading.Lock()
    calls = []

    def controlled_case(case_id):
        with call_lock:
            calls.append(case_id)
            (first_entered if len(calls) == 1 else second_entered).set()
        assert release.wait(5), 'Controlled release timed out'
        raise core.ValidationError('Controlled pre-engine failure; no native process needed')

    monkeypatch.setattr(core, 'load_case', controlled_case)
    monkeypatch.setenv('VRA_ENGINE_TIMEOUT_SECONDS', '30')
    def invoke(case_id):
        if case_id == 'second':
            second_attempted.set()
        return core.run_simulation(case_id, 'baseline', 'none', tmp_path/case_id, timeout=timeout)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(invoke, 'first')
        assert first_entered.wait(3)
        second = pool.submit(invoke, 'second')
        try:
            assert second_attempted.wait(3)
            assert not second_entered.wait(.15), 'Second simulation entered while the first still held the slot'
        finally:
            release.set()
        assert first.result(5)['status'] == second.result(5)['status'] == 'failed'
    assert calls == ['first', 'second']


def test_wall_slab_reconstruction_uses_solids_and_has_no_roof_height_fallback(tmp_path):
    import ifcopenshell.api
    run = ifcopenshell.api.run
    doc = ifcopenshell.file(schema='IFC4')
    root = run('root.create_entity', doc, ifc_class='IfcProject', name='Controlled wall/slab source')
    run('unit.assign_unit', doc, length={'is_metric': True, 'raw': 'METERS'})
    context = run('context.add_context', doc, context_type='Model')
    body = run('context.add_context', doc, context_type='Model', context_identifier='Body', target_view='MODEL_VIEW', parent=context)
    building = run('root.create_entity', doc, ifc_class='IfcBuilding', name='Controlled two-storey source')
    run('aggregate.assign_object', doc, products=[building], relating_object=root)
    for index in range(3):
        floor = run('root.create_entity', doc, ifc_class='IfcBuildingStorey', name='Source floor '+str(index))
        floor.Elevation = float(index*3.4)
        run('aggregate.assign_object', doc, products=[floor], relating_object=building)

        def solid(kind, polygon, z, height):
            item = run('root.create_entity', doc, ifc_class=kind)
            points = [doc.createIfcCartesianPoint((float(x), float(y))) for x, y in polygon]
            polyline = doc.createIfcPolyline(points+[points[0]])
            profile = doc.createIfcArbitraryClosedProfileDef('AREA', None, polyline)
            placement = doc.createIfcAxis2Placement3D(doc.createIfcCartesianPoint((0., 0., float(z))), None, None)
            extrusion = doc.createIfcExtrudedAreaSolid(profile, placement, doc.createIfcDirection((0., 0., 1.)), float(height))
            representation = doc.createIfcShapeRepresentation(body, 'Body', 'SweptSolid', [extrusion])
            run('geometry.assign_representation', doc, product=item, representation=representation)
            run('spatial.assign_container', doc, products=[item], relating_structure=floor)

        solid('IfcSlab', [(0, 0), (10, 0), (10, 8), (0, 8)], index*3.4-.2, .2)
        if index < 2:
            for polygon in [[(0, 0), (10, 0), (10, .2), (0, .2)], [(0, 7.8), (10, 7.8), (10, 8), (0, 8)],
                            [(0, .2), (.2, .2), (.2, 7.8), (0, 7.8)], [(9.8, .2), (10, .2), (10, 7.8), (9.8, 7.8)],
                            [(4.9, .2), (5.1, .2), (5.1, 7.8), (4.9, 7.8)]]:
                solid('IfcWall', polygon, index*3.4, 3.2)
    path = tmp_path/'walls-and-slabs.ifc'
    doc.write(str(path))
    candidate = model_import.ifc(path, ImportOptions(file_id='controlled', reconstruct_elements=True))
    assert len(candidate['rooms']) == 4
    assert sum(model_geometry.floor_area(r) for r in candidate['rooms']) == pytest.approx(142.88, abs=.001)
    assert all(r['conditioned'] is None and r['reconstruction']['ceiling_basis'] == 'slab_surfaces' for r in candidate['rooms'])
    assert any(r['status'] == 'unbounded_ceiling_cell' for r in candidate['diagnostics']['storeys'])


def test_source_curve_negative_interior_is_rejected_not_just_endpoints():
    from backend.equipment_inputs import PerformanceCurve
    # Positive endpoints; negative stationary interior. Do not accept a sampled
    # endpoint-only check as physical validity across the declared range.
    with pytest.raises(ValidationError, match='非正值'):
        PerformanceCurve(kind='quadratic', coefficients=[.15, -1., 1.], x_min=0., x_max=1.,
                         source_note='Controlled invalid interior test')


def test_column_mass_fills_only_proven_columns_and_preserves_air_and_mass():
    from backend import column_mass, heat_pump
    body = model_body()
    column = [[1., 1.], [1.4, 1.], [1.4, 1.4], [1., 1.4]]
    shaft = [[3., 3.], [4., 3.], [4., 4.], [3., 4.]]
    room = dict(id='R1', name='Column and shaft', polygon=[[0., 0.], [6., 0.], [6., 6.], [0., 6.]],
        holes=[column, shaft], elevation_m=0., height_m=3., source_locator='Controlled source column fixture',
        segments=[dict(polygon=[[0., 0.], [6., 0.], [6., 6.], [0., 6.]], holes=[column, shaft], elevation_m=0., height_m=3.)],
        reconstruction=dict(method='IFC_ELEMENT_SECTION', storey_id='floor', source_elements=['column_source'],
            slice_height_m=.9, closed_wall_fraction=1., ceiling_basis='slab_surfaces',
            assumption='Controlled source geometry, not an actual building',
            column_voids=[dict(polygon=column, source_elements=['column_source'])]))
    body['rooms'] = [room]
    body['thermal'].update(column_mass_policy='lumped_scenario', column_mass_material=dict(name='Assumed concrete',
        conductivity_w_mk=1.4, density_kg_m3=2300., specific_heat_j_kgk=900., source_note='Controlled homogeneous material assumption'))
    model = ModelDraft(**body).model_dump()
    before = copy.deepcopy(model)
    derived, report = column_mass.reduce(model)
    assert model == before
    assert len(derived['rooms'][0]['segments'][0]['holes']) == 1
    assert model_geometry.floor_area(model['rooms'][0]) == pytest.approx(34.84)
    assert model_geometry.room_volume(model['rooms'][0]) == pytest.approx(104.52)
    mass = report[0]
    assert mass['column_volume_m3'] == pytest.approx(.48)
    assert mass['exposed_lateral_area_m2'] == pytest.approx(4.8)
    assert mass['equivalent_thickness_m']*mass['exposed_lateral_area_m2'] == pytest.approx(.48)
    text, _ = model_export.idf(model)
    objects = heat_pump.objects(text)
    zone = next(row for row in objects if row[0] == 'Zone')
    assert float(zone[9]) == pytest.approx(104.52)  # Original air volume, not filled envelope.
    assert float(zone[10]) == pytest.approx(34.84)
    assert any(row[0] == 'InternalMass' for row in objects)


def test_precision_closure_and_volume_budget_are_translation_invariant():
    from backend import thermal_mesh
    model = ModelDraft(**model_body()).model_dump()
    source = model_geometry.geometry(model)
    shifted = copy.deepcopy(source)
    for s in shifted:
        s['points'] = [[p[0]+1000., p[1]-2000., p[2]+500.] for p in s['points']]
    a, ra = thermal_mesh.conform(source, return_report=True)
    b, rb = thermal_mesh.conform(shifted, return_report=True)
    assert all(v['unmatched_edges'] == 0 for v in thermal_mesh.edge_incidence(a).values())
    assert all(v['unmatched_edges'] == 0 for v in thermal_mesh.edge_incidence(b).values())
    assert [r['volume_after_m3'] for r in ra['zones']] == pytest.approx([r['volume_after_m3'] for r in rb['zones']])


def test_source_trapezoid_is_not_silently_rectangularized_by_engine():
    from backend.honeybee_bridge import geometry_model
    body = source_window_model()
    window = body['rooms'][0]['source_openings'][0]
    window.update(points=[(0., 1., 1.), (0., 1., 2.), (0., 2.5, 2.), (0., 3., 1.)], source_area_m2=1.75)
    model = ModelDraft(**body).model_dump()
    hb = geometry_model(model, model_export.geometry(model))
    assert sum(a.area for a in hb.apertures) == pytest.approx(1.75)
    assert all(len(a.geometry.vertices) == 3 for a in hb.apertures)


def test_paired_contact_slivers_merge_both_sides_without_losing_area():
    from backend import thermal_mesh
    def contact(name, zone, other, points):
        return dict(name=name, zone=zone, other=other, points=points, kind='Roof' if zone=='A' else 'Floor',
                    boundary='Surface', construction='Floor' if zone=='A' else 'FloorReverse', boundary_basis='Controlled pair')
    tiny=[[0.,0.,3.],[1.,0.,3.],[0.,.00001,3.]]
    large=[[0.,.00001,3.],[1.,0.,3.],[.5,1.,3.]]
    reverse=lambda ring:[[x,y,z+.2] for x,y,z in reversed(ring)]
    source=[contact('a1','A','b1',tiny),contact('a2','A','b2',large),
            contact('b1','B','a1',reverse(tiny)),contact('b2','B','a2',reverse(large))]
    result,report=thermal_mesh.merge_small_pairs(source)
    assert len(result)==2 and len(report)==1
    names={s['name'] for s in result}
    assert all(s['other'] in names for s in result)
    assert all(thermal_mesh.measures(s['points'])[0]==pytest.approx(.5000025) for s in result)
    assert len(source)==4


def test_cumulative_geometry_budget_rejects_changes_across_all_passes():
    from backend import thermal_mesh
    before=model_geometry.geometry(ModelDraft(**model_body()).model_dump())
    bad=copy.deepcopy(before)
    bad[0]['points'][0][0]+=.02
    with pytest.raises(core.ValidationError,match='累计'):
        thermal_mesh.conservation(before,bad)


@pytest.mark.parametrize('key,expected',[
 ('rectangle',192.),('l_plan',117.),('u_plan',189.),('courtyard',252.),('multiple_voids',408.),
 ('setback',300.),('cantilever',96.),('podium_two_towers',672.),('skybridge',312.),('split_level',96.),
 ('sloped_roof',64.),('hip_roof',176./3),('leaning_solid',48.)])
def test_morphology_volume_and_exposed_floor_semantics(key,expected):
    from scripts.morphology_cases import cases
    from test_model_workbench import THERMAL,ASSEMBLIES
    model=ModelDraft(name=key,rooms=cases()[key],review_note='Controlled analytic shape coverage test',
                     thermal={**THERMAL,'constructions':ASSEMBLIES}).model_dump()
    assert sum(model_geometry.room_volume(r) for r in model['rooms'])==pytest.approx(expected,abs=1e-5)
    if key=='cantilever':assert model_geometry.floor_area(model['rooms'][0])==pytest.approx(24.)
    surfaces=model_export.geometry(model)
    assert model_export.geometry_audit(model)['passed']
    if key in ('cantilever','skybridge','split_level'):
        assert any(s['kind']=='Floor' and s['boundary']=='Outdoors' for s in surfaces)


def test_coplanar_opposite_facing_walls_are_not_joined_with_a_flipped_normal():
    from backend import thermal_mesh
    tiny=[[0.,2.,0.],[.01,2.,0.],[0.,2.,.1]]
    large=[[0.,2.,.1],[1.,2.,.2],[.01,2.,0.]]
    surfaces=[dict(name=name,zone='R',kind='Wall',construction='Wall',boundary='Adiabatic',other='',
                   points=points,boundary_basis='Controlled opposite normal') for name,points in [('a',tiny),('b',large)]]
    result=thermal_mesh.conform(surfaces)
    assert len(result)==2
    assert sorted(model_geometry.frame(s['points'])['side'] for s in result)==[-1,1]


@pytest.mark.parametrize('payload',[b'\xff\xfe',(','.join(COLUMNS)+'\n"unterminated').encode()])
def test_malformed_equipment_source_has_validation_error_not_server_error(tmp_path,payload):
    from backend.equipment_inputs import read_csv
    path=tmp_path/'source.csv';path.write_bytes(payload)
    with pytest.raises(core.ValidationError,match='CSV'):
        read_csv({'file_id':'controlled','hash':core.sha(path)},path)


def test_nearly_axial_planes_keep_the_same_uv_orientation_after_rounding():
    import numpy as np
    from backend.thermal_mesh import frame
    a=frame([[0.,0.,0.],[1.,.00000012,0.],[1.,.00000012,3.],[0.,0.,3.]])
    b=frame(list(reversed([[0.,0.,0.],[1.,.00000008,0.],[1.,.00000008,3.],[0.,0.,3.]])))
    assert float(np.dot(a['normal'],b['normal']))>1-1e-10
    assert float(np.dot(a['normal']*a['side'],b['normal']*b['side']))<-1+1e-10



def test_same_elevation_buildings_reconstruct_without_duplicate_rooms(tmp_path):
    import ifcopenshell.api
    import numpy as np
    test_wall_slab_reconstruction_uses_solids_and_has_no_roof_height_fallback(tmp_path)
    path=tmp_path/'walls-and-slabs.ifc'
    doc=ifcopenshell.open(str(path));run=ifcopenshell.api.run
    floors=list(doc.by_type('IfcBuildingStorey'))
    second=run('root.create_entity',doc,ifc_class='IfcBuilding',name='Second building, same elevations')
    run('aggregate.assign_object',doc,products=[second],relating_object=doc.by_type('IfcProject')[0])
    for old in floors:
        floor=run('root.create_entity',doc,ifc_class='IfcBuildingStorey',name=old.Name)
        floor.Elevation=old.Elevation
        run('aggregate.assign_object',doc,products=[floor],relating_object=second)
        for item in [e for relation in old.ContainsElements for e in relation.RelatedElements]:
            duplicate=run('root.copy_class',doc,product=item);duplicate.Representation=None
            for representation in item.Representation.Representations:
                run('geometry.assign_representation',doc,product=duplicate,representation=representation)
            matrix=np.eye(4);matrix[0,3]=20.
            run('geometry.edit_object_placement',doc,product=duplicate,matrix=matrix,is_si=True)
            run('spatial.assign_container',doc,products=[duplicate],relating_structure=floor)
    doc.write(str(path))
    candidate=model_import.ifc(path,ImportOptions(file_id='controlled',reconstruct_elements=True))
    assert len(candidate['rooms'])==8
    assert len({r['building_id'] for r in candidate['rooms']})==2
    assert all(r['geometry_inferred'] for r in candidate['rooms'])
    assert sum(model_geometry.floor_area(r) for r in candidate['rooms'])==pytest.approx(285.76,abs=.001)
    ModelDraft(rooms=candidate['rooms'],review_note='Controlled same-elevation multi-building reconstruction')


def test_native_collinear_contact_vertices_are_preserved_in_triangles():
    from backend import thermal_mesh
    front=[[0.,0.,0.],[0.,1.,0.],[0.,2.,0.],[0.,1.,1.]]
    back=[[.2,y,z] for _,y,z in reversed(front)]
    surfaces=[dict(name=name,zone=zone,other=other,points=points,kind='Wall',construction='Wall',
                   boundary='Surface',boundary_basis='Controlled native collinear contact')
              for name,zone,other,points in [('a','A','b',front),('b','B','a',back)]]
    result=thermal_mesh.conform(surfaces)
    assert len(result)==4
    assert all(len(s['points'])==3 for s in result)
    for zone in ['A','B']:
        assert sum(thermal_mesh.measures(s['points'])[0] for s in result if s['zone']==zone)==pytest.approx(1.)
