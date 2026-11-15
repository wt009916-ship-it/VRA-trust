import json
import math
from fractions import Fraction
from pathlib import Path

import ifcopenshell
import pytest
from pydantic import ValidationError

from backend.beam_sections import properties
from backend.engineering import BeamInput, calculate
from backend.ifc_beam_profiles import extract
from test_engineering import beam, fem


def example(profile_type='IfcRectangleProfileDef', prefix=None, **dimensions):
    doc = ifcopenshell.file(schema='IFC4')
    scale = 1000. if prefix == 'MILLI' else 1.
    unit = doc.create_entity('IfcSIUnit', UnitType='LENGTHUNIT', Prefix=prefix, Name='METRE')
    project = doc.create_entity('IfcProject', GlobalId=ifcopenshell.guid.new(), UnitsInContext=doc.create_entity('IfcUnitAssignment', Units=[unit]))
    def axis():
        return doc.create_entity('IfcAxis2Placement3D', Location=doc.create_entity('IfcCartesianPoint', Coordinates=(0.,0.,0.)))
    context = doc.create_entity('IfcGeometricRepresentationContext', ContextType='Model', CoordinateSpaceDimension=3, Precision=1e-8, WorldCoordinateSystem=axis())
    project.RepresentationContexts = [context]
    profile = doc.create_entity(profile_type, ProfileType='AREA', **{k:float(v*scale) for k,v in (dimensions or {'XDim':.2,'YDim':.3}).items()})
    solid = doc.create_entity('IfcExtrudedAreaSolid', SweptArea=profile, Position=axis(), ExtrudedDirection=doc.create_entity('IfcDirection', DirectionRatios=(0.,0.,1.)), Depth=6.*scale)
    body = doc.create_entity('IfcShapeRepresentation', ContextOfItems=context, RepresentationIdentifier='Body', RepresentationType='SweptSolid', Items=[solid])
    element = doc.create_entity('IfcBeam', GlobalId=ifcopenshell.guid.new(), Name='Independent profile fixture', ObjectPlacement=doc.create_entity('IfcLocalPlacement', RelativePlacement=axis()), Representation=doc.create_entity('IfcProductDefinitionShape', Representations=[body]))
    return doc, project, element, profile, solid, body


def with_profile(kind, dimensions, axis='x', unit='m'):
    body = beam();body.update(width=None,depth=None,section_profile={'kind':kind,'dimensions':dimensions,'unit':unit,'bending_axis':axis})
    return body


def test_frozen_public_ipe600_matches_independent_curved_area_integration():
    oracle=json.loads((Path(__file__).parents[1]/'fixtures/test/ifc_beam_oracle.json').read_text())
    result=properties('i_section',oracle['parameters_m'])
    for key in ('area_m2','ix_m4','iy_m4'):
        assert result[key]==pytest.approx(oracle[key],rel=oracle['tolerance_relative'])
    sharp=properties('i_section',{**oracle['parameters_m'],'r':0})
    assert result['ix_m4']>sharp['ix_m4'] and result['iy_m4']>sharp['iy_m4']


@pytest.mark.parametrize('kind,dims,area,ix,iy',[
    ('rectangle',{'b':.2,'h':.3},.06,float(Fraction(1,5)*Fraction(3,10)**3/12),float(Fraction(3,10)*Fraction(1,5)**3/12)),
    ('circle',{'r':.15},math.pi*.15**2,math.pi*.15**4/4,math.pi*.15**4/4),
    ('rectangular_hollow',{'b':.2,'h':.3,'t':.01},.2*.3-.18*.28,(.2*.3**3-.18*.28**3)/12,(.3*.2**3-.28*.18**3)/12),
    ('circular_hollow',{'r':.15,'t':.01},math.pi*(.15**2-.14**2),math.pi*(.15**4-.14**4)/4,math.pi*(.15**4-.14**4)/4),
])
def test_section_oracles(kind,dims,area,ix,iy):
    r=properties(kind,dims)
    assert [r['area_m2'],r['ix_m4'],r['iy_m4']]==pytest.approx([area,ix,iy],rel=1e-12)


@pytest.mark.parametrize('axis',['x','y'])
@pytest.mark.parametrize('support',['simply_supported','cantilever'])
def test_profile_beam_matches_independent_fem_and_exact_uniform_load(axis,support):
    d={'b':220.,'h':600.,'tw':12.,'tf':19.,'r':24.}
    b=with_profile('i_section',d,axis,'mm');b['support']=support
    result=calculate(BeamInput(**b));m=result['metrics']
    oracle=json.loads((Path(__file__).parents[1]/'fixtures/test/ifc_beam_oracle.json').read_text())
    inertia=oracle['i'+axis+'_m4'];ei=30e9*inertia
    expected=(5/384 if support=='simply_supported' else 1/8)*10000*6**4/ei
    assert m['max_deflection_m']==pytest.approx(expected,rel=1e-10)
    xs,ds,rs,reactions=fem(6,30e9,inertia,[],[(10000,0,6)],support)
    assert max(ds)==pytest.approx(expected,rel=1e-9)
    assert m['inertia_m4']==pytest.approx(inertia,rel=1e-10)
    assert result['structural_safety']=='NOT_ASSESSED'


@pytest.mark.parametrize('kind,dims',[
    ('rectangle',{'b':-.2,'h':.3}),('rectangle',{'b':0,'h':.3}),
    ('rectangle',{'b':True,'h':.3}),('rectangle',{'b':float('nan'),'h':.3}),
    ('rectangle',{'b':.2}),('rectangle',{'b':.2,'h':.3,'t':.1}),
    ('circular_hollow',{'r':.1,'t':.1}),('rectangular_hollow',{'b':.2,'h':.3,'t':.1}),
    ('i_section',{'b':.2,'h':.3,'tw':.2,'tf':.01,'r':0}),
    ('i_section',{'b':.2,'h':.3,'tw':.01,'tf':.02,'r':.13}),
])
def test_invalid_sections_reject(kind,dims):
    with pytest.raises(ValueError):properties(kind,dims)


def test_mixed_legacy_profile_and_unknown_axis_reject():
    b=with_profile('circle',{'r':.1});b['width']=.2
    with pytest.raises(ValidationError):BeamInput(**b)
    b['width']=None;b['section_profile']['bending_axis']='z'
    with pytest.raises(ValidationError):BeamInput(**b)


@pytest.mark.parametrize('prefix',[None,'MILLI'])
def test_ifc_real_entities_units_no_inferred_mechanics(prefix):
    doc,_,element,_,_,_=example(prefix=prefix)
    result=extract(doc,element.id())
    assert result['status']=='extracted'
    assert result['section_profile']['dimensions']==pytest.approx({'b':.2,'h':.3})
    assert result['extrusion_length_m']==6
    for key in ('engineering_span_m','elastic_modulus_pa','supports','loads'):assert result[key] is None
    assert result['source']['profile_id']>0


def test_ifc_rounded_i_and_unsupported_edge_rounding():
    doc,_,element,profile,_,_=example('IfcIShapeProfileDef',OverallWidth=.22,OverallDepth=.6,WebThickness=.012,FlangeThickness=.019,FilletRadius=.024)
    assert extract(doc,element.id())['status']=='extracted'
    profile.FlangeEdgeRadius=.002
    result=extract(doc,element.id())
    assert result['status']=='unsupported' and result['section_properties'] is None
    assert result['issues']==['unsupported_profile_detail:FlangeEdgeRadius']


@pytest.mark.parametrize('case',['units_missing','units_duplicate','two_items','oblique','opening','mapping_cycle'])
def test_ambiguous_or_nonuniform_beam_refuses(case):
    doc,project,element,profile,solid,body=example()
    if case=='units_missing':project.UnitsInContext=None
    elif case=='units_duplicate':project.UnitsInContext.Units=list(project.UnitsInContext.Units)+[doc.create_entity('IfcSIUnit',UnitType='LENGTHUNIT',Name='METRE',Prefix='MILLI')]
    elif case=='two_items':body.Items=[solid,solid]
    elif case=='oblique':solid.ExtrudedDirection.DirectionRatios=(1.,0.,1.)
    elif case=='opening':
        opening=doc.create_entity('IfcOpeningElement',GlobalId=ifcopenshell.guid.new())
        doc.create_entity('IfcRelVoidsElement',GlobalId=ifcopenshell.guid.new(),RelatingBuildingElement=element,RelatedOpeningElement=opening)
    else:
        origin=doc.create_entity('IfcAxis2Placement3D',Location=doc.create_entity('IfcCartesianPoint',Coordinates=(0.,0.,0.)))
        mapping=doc.create_entity('IfcRepresentationMap',MappingOrigin=origin,MappedRepresentation=body)
        target=doc.create_entity('IfcCartesianTransformationOperator3D',LocalOrigin=doc.create_entity('IfcCartesianPoint',Coordinates=(0.,0.,0.)))
        body.Items=[doc.create_entity('IfcMappedItem',MappingSource=mapping,MappingTarget=target)]
    result=extract(doc,element.id())
    assert result['status']=='unsupported' and result['section_profile'] is None


def test_mapped_uniform_scale_and_rotated_axis():
    doc,_,element,_,solid,body=example()
    solid.Position.RefDirection=doc.create_entity('IfcDirection',DirectionRatios=(0.,1.,0.))
    origin=doc.create_entity('IfcAxis2Placement3D',Location=doc.create_entity('IfcCartesianPoint',Coordinates=(0.,0.,0.)))
    mapping=doc.create_entity('IfcRepresentationMap',MappingOrigin=origin,MappedRepresentation=body)
    target=doc.create_entity('IfcCartesianTransformationOperator3D',LocalOrigin=doc.create_entity('IfcCartesianPoint',Coordinates=(0.,0.,0.)),Scale=2.)
    outer=doc.create_entity('IfcShapeRepresentation',ContextOfItems=body.ContextOfItems,RepresentationIdentifier='Body',RepresentationType='MappedRepresentation',Items=[doc.create_entity('IfcMappedItem',MappingSource=mapping,MappingTarget=target)])
    element.Representation.Representations=[outer]
    r=extract(doc,element.id())
    assert r['status']=='extracted'
    assert r['section_profile']['dimensions']==pytest.approx({'b':.4,'h':.6})
    assert r['extrusion_length_m']==12
    assert r['axes_world']['x']==pytest.approx([0,1,0])
    assert r['axes_world']['y']==pytest.approx([-1,0,0])
    assert r['axes_world']['extrusion']==pytest.approx([0,0,1])


@pytest.mark.parametrize('scale',[1.,1e-8,1e8])
def test_nonuniform_transform_rejects_even_at_extreme_mapping_scale(scale):
    import numpy as np
    from backend.ifc_beam_profiles import rigid_scale
    matrix=np.diag([scale,2*scale,scale,1.])
    with pytest.raises(ValueError,match='nonuniform'):
        rigid_scale(matrix,allow_scale=True)


@pytest.mark.parametrize('axis',['x','y'])
@pytest.mark.parametrize('kind,dims,expected',[
    ('circle',{'r':.15},math.pi*.15**2),
    ('circular_hollow',{'r':.15,'t':.01},math.pi*(.15**2-.14**2)),
    ('rectangular_hollow',{'b':.2,'h':.3,'t':.01},.2*.3-.18*.28),
    ('i_section',{'b':.22,'h':.6,'tw':.012,'tf':.019,'r':.024},.015598442631532275),
])
def test_beam_metrics_report_actual_section_area_not_bounding_rectangle(axis,kind,dims,expected):
    result=calculate(BeamInput(**with_profile(kind,dims,axis)))
    assert result['metrics']['area_m2']==pytest.approx(expected,rel=1e-10)


@pytest.mark.parametrize('entity,dimensions,expected_kind,expected_area',[
    ('IfcCircleProfileDef',{'Radius':.15},'circle',math.pi*.15**2),
    ('IfcCircleHollowProfileDef',{'Radius':.15,'WallThickness':.01},'circular_hollow',math.pi*(.15**2-.14**2)),
    ('IfcRectangleHollowProfileDef',{'XDim':.2,'YDim':.3,'WallThickness':.01},'rectangular_hollow',.2*.3-.18*.28),
])
def test_other_ifc_parameter_profiles_native_units(entity,dimensions,expected_kind,expected_area):
    doc,_,element,_,_,_=example(entity,prefix='MILLI',**dimensions)
    result=extract(doc,element.id())
    assert result['status']=='extracted'
    assert result['section_profile']['kind']==expected_kind
    assert result['section_properties']['area_m2']==pytest.approx(expected_area,rel=1e-12)
