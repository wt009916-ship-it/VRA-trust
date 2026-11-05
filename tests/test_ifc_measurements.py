"""Independent primitives, units and declaration conflicts for actual IFC processing."""
import hashlib
import math

import ifcopenshell
import numpy as np
import pytest

from backend.cad_worker import parse_ifc
from backend.ifc_details import declarations, normalized_quantity, project_units, unit_scale
from backend.ifc_geometry import mesh_measurements
from test_api import create_project
from test_cad import upload


def make_box(prefix=None, offset=(10., 20., 30.), opening=False):
    doc = ifcopenshell.file(schema='IFC4')
    f = 1000. if prefix == 'MILLI' else 1.
    unit = doc.create_entity('IfcSIUnit', UnitType='LENGTHUNIT', Prefix=prefix, Name='METRE')
    project = doc.create_entity('IfcProject', GlobalId=ifcopenshell.guid.new(), UnitsInContext=doc.create_entity('IfcUnitAssignment', Units=[unit]))
    def axis(xyz, rotated=False):
        return doc.create_entity('IfcAxis2Placement3D', Location=doc.create_entity('IfcCartesianPoint', Coordinates=tuple(float(x) for x in xyz)),
                                 RefDirection=doc.create_entity('IfcDirection', DirectionRatios=(0., 1., 0.)) if rotated else None)
    context = doc.create_entity('IfcGeometricRepresentationContext', ContextType='Model', CoordinateSpaceDimension=3, Precision=1e-7, WorldCoordinateSystem=axis((0., 0., 0.)))
    project.RepresentationContexts = [context]
    placement = doc.create_entity('IfcLocalPlacement', RelativePlacement=axis(tuple(x*f for x in offset), True))
    def solid(width, length):
        profile = doc.create_entity('IfcRectangleProfileDef', ProfileType='AREA', XDim=width*f, YDim=length*f)
        extrusion = doc.create_entity('IfcExtrudedAreaSolid', SweptArea=profile, Position=axis((0., 0., 0.)),
                                      ExtrudedDirection=doc.create_entity('IfcDirection', DirectionRatios=(0., 0., 1.)), Depth=4*f)
        body = doc.create_entity('IfcShapeRepresentation', ContextOfItems=context, RepresentationIdentifier='Body', RepresentationType='SweptSolid', Items=[extrusion])
        return doc.create_entity('IfcProductDefinitionShape', Representations=[body])
    wall = doc.create_entity('IfcWall', GlobalId=ifcopenshell.guid.new(), Name='Independent 2x3x4 box', ObjectPlacement=placement, Representation=solid(2., 3.))
    if opening:
        hole = doc.create_entity('IfcOpeningElement', GlobalId=ifcopenshell.guid.new(), ObjectPlacement=placement, Representation=solid(.5, 1.))
        doc.create_entity('IfcRelVoidsElement', GlobalId=ifcopenshell.guid.new(), RelatingBuildingElement=wall, RelatedOpeningElement=hole)
    return doc, project, wall


def result(doc, tmp_path):
    path = tmp_path/'case.ifc'
    doc.write(str(path))
    return parse_ifc(path)


@pytest.mark.parametrize('prefix', [None, 'MILLI'])
def test_native_box_si_rotation_and_world_bbox(prefix, tmp_path):
    doc, _, wall = make_box(prefix)
    data = result(doc, tmp_path)
    row = next(x for x in data['ifc_geometry']['objects'] if x['id'] == wall.id())
    assert row['volume_m3'] == pytest.approx(2*3*4)
    assert row['surface_area_m2'] == pytest.approx(2*(2*3+2*4+3*4))
    assert row['bbox_world_m']['min'] == pytest.approx([8.5, 19, 30])
    assert row['bbox_world_m']['max'] == pytest.approx([11.5, 21, 34])
    assert row['mesh_status'] == 'oriented_edge_closed'
    assert row['representation_ids'] and row['item_ids']


def test_native_opening_is_subtracted_and_never_summed_with_host(tmp_path):
    doc, _, wall = make_box(opening=True)
    data = result(doc, tmp_path)
    rows = data['ifc_geometry']['objects']
    row = next(x for x in rows if x['id'] == wall.id())
    assert row['volume_m3'] == pytest.approx(24-.5*1*4)
    assert row['surface_area_m2'] == pytest.approx(52-2*.5*1+2*(.5+1)*4)
    assert len(rows) == 2  # host and opening remain separate, no misleading total


def test_large_world_translation_does_not_corrupt_local_volume(tmp_path):
    doc, _, _ = make_box(offset=(5e8, 3e9, 0.))
    row = result(doc, tmp_path)['ifc_geometry']['objects'][0]
    assert row['volume_m3'] == pytest.approx(24, abs=1e-10)


def test_mapped_nonuniform_scale_and_nested_placement(tmp_path):
    doc, _, wall = make_box()
    body = wall.Representation.Representations[0]
    origin = doc.create_entity('IfcAxis2Placement3D', Location=doc.create_entity('IfcCartesianPoint', Coordinates=(0.,0.,0.)))
    mapping = doc.create_entity('IfcRepresentationMap', MappingOrigin=origin, MappedRepresentation=body)
    transform = doc.create_entity('IfcCartesianTransformationOperator3DnonUniform',
                                  LocalOrigin=origin.Location, Scale=2., Scale2=3., Scale3=4.)
    item = doc.create_entity('IfcMappedItem', MappingSource=mapping, MappingTarget=transform)
    mapped = doc.create_entity('IfcShapeRepresentation', ContextOfItems=body.ContextOfItems,
                               RepresentationIdentifier='Body', RepresentationType='MappedRepresentation', Items=[item])
    wall.Representation.Representations = [mapped]
    parent_axis = doc.create_entity('IfcAxis2Placement3D', Location=doc.create_entity('IfcCartesianPoint', Coordinates=(100.,200.,300.)))
    wall.ObjectPlacement.PlacementRelTo = doc.create_entity('IfcLocalPlacement', RelativePlacement=parent_axis)
    row = result(doc,tmp_path)['ifc_geometry']['objects'][0]
    assert row['volume_m3'] == pytest.approx(4*9*16)
    assert row['surface_area_m2'] == pytest.approx(2*(4*9+9*16+4*16))
    assert row['bbox_world_m']['min'] == pytest.approx([105.5,218,330])
    assert row['bbox_world_m']['max'] == pytest.approx([114.5,222,346])


@pytest.mark.parametrize('missing', ['unit', 'placement', 'body', 'duplicate_body'])
def test_missing_geometry_prerequisites_remain_unknown(missing, tmp_path):
    doc, project, wall = make_box()
    if missing == 'unit': project.UnitsInContext = None
    if missing == 'placement': wall.ObjectPlacement = None
    if missing == 'body': wall.Representation = None
    if missing == 'duplicate_body': wall.Representation.Representations *= 2
    row = result(doc, tmp_path)['ifc_geometry']['objects'][0]
    assert row['volume_m3'] is None and row['surface_area_m2'] is None
    assert row['status'] != 'measured_mesh'


def tetrahedron():
    # Independent tetrahedron volume = determinant(diag(2,3,4))/6 = 4.
    return np.array([[0,0,0],[2,0,0],[0,3,0],[0,0,4]], float), np.array([[0,2,1],[0,1,3],[0,3,2],[1,2,3]])


def test_mesh_integral_and_invalid_topology():
    vertices, faces = tetrahedron()
    expected_area = 3+4+6+math.sqrt(61)
    for shift in (0, 1e9):
        row = mesh_measurements(vertices+shift, faces)
        assert row['volume_m3'] == pytest.approx(4)
        assert row['surface_area_m2'] == pytest.approx(expected_area)
    for invalid in (faces[:-1], np.vstack([faces,faces[0]]), np.vstack([faces, [0,0,1]]), np.vstack([faces[:3], faces[3][::-1]])):
        assert mesh_measurements(vertices, invalid)['volume_m3'] is None


def test_signed_inner_shell_is_not_added_as_solid():
    v, f = tetrahedron()
    vertices = np.vstack([v, v*.25+.1])
    faces = np.vstack([f, (f+4)[:, ::-1]])
    assert mesh_measurements(vertices, faces)['volume_m3'] == pytest.approx(4*(1-.25**3))


@pytest.mark.parametrize('kind,name,prefix,value,expected', [
    ('LENGTHUNIT','METRE','MILLI',2500.,2.5),
    ('AREAUNIT','SQUARE_METRE','MILLI',2000000.,2.),
    ('VOLUMEUNIT','CUBIC_METRE','MILLI',3000000000.,3.),
    ('MASSUNIT','GRAM','KILO',7.,7.),
    ('MASSUNIT','GRAM',None,2000.,2.),
    ('TIMEUNIT','SECOND',None,60.,60.),
])
def test_quantity_dimension_specific_scale(kind, name, prefix, value, expected):
    doc = ifcopenshell.file(schema='IFC4')
    unit = doc.create_entity('IfcSIUnit', UnitType=kind, Name=name, Prefix=prefix)
    assert value * unit_scale(unit, kind) == pytest.approx(expected)


def add_quantity(doc, wall, unit=None, value=24., name='NetVolume'):
    q = doc.create_entity('IfcQuantityVolume', Name=name, Unit=unit, VolumeValue=value)
    pset = doc.create_entity('IfcElementQuantity', GlobalId=ifcopenshell.guid.new(), Name='BaseQuantities', MethodOfMeasurement='Declared sample', Quantities=[q])
    doc.create_entity('IfcRelDefinesByProperties', GlobalId=ifcopenshell.guid.new(), RelatedObjects=[wall], RelatingPropertyDefinition=pset)
    return q


def test_declared_volume_never_inferred_from_length_unit(tmp_path):
    doc, project, wall = make_box('MILLI')
    q = add_quantity(doc, wall, value=99.)
    assert normalized_quantity(q, project_units(project))['status'] == 'missing_unit'
    q.Unit = doc.create_entity('IfcSIUnit', UnitType='VOLUMEUNIT', Name='CUBIC_METRE')
    data = result(doc, tmp_path)
    declared = data['objects'][0]['quantities'][0]
    measured = data['ifc_geometry']['objects'][0]
    assert declared['value_si'] == 99 and measured['volume_m3'] == pytest.approx(24)
    assert declared['source_kind'] == 'model_declaration' and declared['unit_source'] == 'explicit'


def test_invalid_conflicting_context_and_conversion_units():
    doc, project, wall = make_box()
    unit = doc.create_entity('IfcSIUnit', UnitType='VOLUMEUNIT', Name='CUBIC_METRE')
    q = add_quantity(doc, wall, unit)
    q.Unit = project.UnitsInContext.Units[0]
    assert normalized_quantity(q, {})['status'] == 'unit_dimension_mismatch'
    q.Unit = None
    assert normalized_quantity(q, {'VOLUMEUNIT':[unit,unit]})['status'] == 'conflicting_project_units'
    q.Unit = unit; q.VolumeValue = -1.
    assert normalized_quantity(q, {})['status'] == 'invalid_quantity_value'
    q.VolumeValue = 1.
    unknown = doc.create_entity('IfcContextDependentUnit', Dimensions=doc.create_entity('IfcDimensionalExponents', 3,0,0,0,0,0,0), UnitType='VOLUMEUNIT', Name='mystery')
    q.Unit = unknown
    assert normalized_quantity(q, {})['status'] == 'unsupported_unit'
    ft3 = doc.create_entity('IfcConversionBasedUnit', Dimensions=unknown.Dimensions, UnitType='VOLUMEUNIT', Name='cubic foot',
                            ConversionFactor=doc.create_entity('IfcMeasureWithUnit', ValueComponent=doc.create_entity('IfcVolumeMeasure', .028316846592), UnitComponent=unit))
    q.Unit = ft3
    assert normalized_quantity(q, {})['value_si'] == pytest.approx(.028316846592)
    ft3.ConversionFactor.UnitComponent = ft3
    assert normalized_quantity(q, {})['status'] == 'cyclic_or_deep_unit'
    ft3.Dimensions = doc.create_entity('IfcDimensionalExponents', 1,0,0,0,0,0,0)
    assert normalized_quantity(q, {})['status'] == 'unit_exponents_mismatch'


def test_mesh_budget_and_invalid_inputs(monkeypatch):
    v,f = tetrahedron()
    with pytest.raises(ValueError,match='index'): mesh_measurements(v, [[0,1,9]])
    with pytest.raises(ValueError,match='coordinate'): mesh_measurements(v*np.nan,f)
    monkeypatch.setattr('backend.ifc_geometry.MAX_VERTICES',3)
    with pytest.raises(ValueError,match='budget'): mesh_measurements(v,f)


def test_complex_quantities_and_cyclic_definitions_rejected():
    doc, _, wall = make_box()
    quantity = add_quantity(doc,wall)
    pset = wall.IsDefinedBy[0].RelatingPropertyDefinition
    complex_q = doc.create_entity('IfcPhysicalComplexQuantity',Name='Assembly',HasQuantities=[quantity],Discrimination='source')
    pset.Quantities = [complex_q]
    row = declarations(wall,{})['quantities'][0]
    assert row['path'] == ['Assembly','NetVolume']
    complex_q.HasQuantities = [complex_q]
    with pytest.raises(ValueError,match='Cyclic'): declarations(wall,{})


def test_conflicting_length_units_reject_file(tmp_path):
    doc,project,_ = make_box()
    project.UnitsInContext.Units *= 2
    with pytest.raises(ValueError,match='Conflicting'): result(doc,tmp_path)


def test_spatial_decomposition_preserves_floor_relation(tmp_path):
    doc,_,wall = make_box()
    floor = doc.create_entity('IfcBuildingStorey',GlobalId=ifcopenshell.guid.new(),Name='Level 1')
    room = doc.create_entity('IfcSpace',GlobalId=ifcopenshell.guid.new(),Name='Room A')
    relation = doc.create_entity('IfcRelAggregates',GlobalId=ifcopenshell.guid.new(),RelatingObject=floor,RelatedObjects=[room])
    row = next(r for r in result(doc,tmp_path)['objects'] if r['id']==room.id())
    assert row['spatial_relations'] == [{'relation_id':relation.id(),'relation_type':'IfcRelAggregates',
                                        'parent_id':floor.id(),'parent_type':'IfcBuildingStorey','parent_name':'Level 1'}]


def test_type_inheritance_override_and_duplicate_are_traceable():
    doc, project, wall = make_box()
    def pset(value):
        p = doc.create_entity('IfcPropertySingleValue', Name='FireRating', NominalValue=doc.create_entity('IfcLabel', value))
        return doc.create_entity('IfcPropertySet', GlobalId=ifcopenshell.guid.new(), Name='Pset_WallCommon', HasProperties=[p])
    inherited = pset('60min')
    typ = doc.create_entity('IfcWallType', GlobalId=ifcopenshell.guid.new(), HasPropertySets=[inherited], PredefinedType='STANDARD')
    doc.create_entity('IfcRelDefinesByType', GlobalId=ifcopenshell.guid.new(), RelatedObjects=[wall], RelatingType=typ)
    instance = pset('90min')
    doc.create_entity('IfcRelDefinesByProperties', GlobalId=ifcopenshell.guid.new(), RelatedObjects=[wall], RelatingPropertyDefinition=instance)
    data = declarations(wall, project_units(project))
    assert len(data['types']) == 1
    assert {r['value']:r['selection'] for r in data['properties']} == {'90min':'effective_declaration','60min':'overridden_by_instance'}
    doc.create_entity('IfcRelDefinesByProperties', GlobalId=ifcopenshell.guid.new(), RelatedObjects=[wall], RelatingPropertyDefinition=pset('120min'))
    assert all(r['selection'] == 'ambiguous' for r in declarations(wall, {})['properties'])


def test_actual_api_retains_original_and_geometry_source_binding(client, monkeypatch):
    doc, _, _ = make_box('MILLI', opening=True)
    content = doc.to_string().encode()
    pid = create_project(client)['project_id']
    fid = upload(client, pid, 'geometry.ifc', content)
    base = f'/api/projects/{pid}/cad-inspections'
    response = client.post(base, json={'file_id':fid})
    assert response.status_code == 201, response.text
    record = response.json()
    assert record['source']['hash'] == hashlib.sha256(content).hexdigest()
    assert record['result']['ifc_geometry']['objects'][0]['volume_m3'] == pytest.approx(22)
    monkeypatch.setattr('backend.cad.parser_version', lambda: 'changed-helper')
    assert client.get(base+'/'+record['cad_id']).json()['result'] is None
