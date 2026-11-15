

def test_concentric_circular_materials_against_independent_pi_area(tmp_path):
    import math
    doc,element,_,_,mp,solid,path=composite(tmp_path,case='adjacent')
    outer=doc.create_entity('IfcCircleHollowProfileDef',ProfileType='AREA',Radius=.3,WallThickness=.03)
    inner=doc.create_entity('IfcCircleProfileDef',ProfileType='AREA',Radius=.27)
    solid.SweptArea.Profiles=[outer,inner]
    for row,profile in zip(mp,[outer,inner]):row.Profile=profile
    doc.write(str(path));r=measure_layers(path,element.id())
    expected=[math.pi*(.3**2-.27**2)*4,math.pi*.27**2*4]
    assert r['status']=='measured',r
    # Declared curved tessellation tolerance before this first execution: 0.5%.
    assert [row['envelope_volume_m3'] for row in r['layers']]==pytest.approx(expected,rel=.005,abs=1e-8)


def test_profile_count_budget_rejects_before_native_geometry(tmp_path):
    doc,element,profiles,materials,mp,solid,path=composite(tmp_path,case='adjacent')
    group=element.HasAssociations[0].RelatingMaterial.ForProfileSet
    for _ in range(15):
        profile=doc.create_entity('IfcRectangleProfileDef',ProfileType='AREA',XDim=1.,YDim=1.)
        solid.SweptArea.Profiles=(*solid.SweptArea.Profiles,profile)
        group.MaterialProfiles=(*group.MaterialProfiles,doc.create_entity('IfcMaterialProfile',Material=materials[0],Profile=profile))
    doc.write(str(path));r=measure_layers(path,element.id())
    assert r['status']=='unavailable' and r['reason']=='composite_profile_count_or_coverage',r


def test_existing_homogeneous_multiple_sweeps_remain_supported(tmp_path):
    doc,element,profiles,materials,mp,solid,path=composite(tmp_path,case='adjacent')
    group=element.HasAssociations[0].RelatingMaterial.ForProfileSet;group.CompositeProfile=None
    mp[1].Material=materials[0]
    profiles[1].Position.Location.Coordinates=(2.,0.)
    body=element.Representation.Representations[0]
    body.Items=[doc.create_entity('IfcExtrudedAreaSolid',SweptArea=profile,Position=solid.Position,
        ExtrudedDirection=solid.ExtrudedDirection,Depth=solid.Depth) for profile in profiles]
    doc.write(str(path));r=measure_layers(path,element.id())
    assert r['status']=='measured' and len(r['layers'])==1,r
    assert r['total_layer_envelope_m3']==pytest.approx(24,abs=1e-8)
