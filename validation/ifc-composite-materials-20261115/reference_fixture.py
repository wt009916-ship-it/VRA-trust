import sys
from pathlib import Path
REPO=Path('C:/Users/18483/AppData/Local/Temp/vra-timestep-reliability-20261108')
sys.path[:0]=[str(REPO),str(REPO/'tests')]
from test_ifc_member_quantities import member
from test_ifc_materials import associate

def composite(folder,prefix=None,case='cross_material_opening'):
    doc,project,element,material,path=member(folder,prefix=prefix,opening=case!='adjacent' and case!='overlap')
    scale=1000 if prefix=='MILLI' else 1
    doc.remove(element.HasAssociations[0])
    solid=element.Representation.Representations[0].Items[0]
    def rectangle(width,depth,x):
        pos=doc.create_entity('IfcAxis2Placement2D',Location=doc.create_entity('IfcCartesianPoint',Coordinates=(float(x*scale),0.)))
        return doc.create_entity('IfcRectangleProfileDef',ProfileType='AREA',Position=pos,XDim=width*scale,YDim=depth*scale)
    if case=='tube_core_opening':
        profiles=[doc.create_entity('IfcRectangleHollowProfileDef',ProfileType='AREA',XDim=2.*scale,YDim=3.*scale,WallThickness=.25*scale),rectangle(1.5,2.5,0.)]
    else:
        width,offset=(1.2,.4) if case=='overlap' else (1.,.5)
        profiles=[rectangle(width,3.,-offset),rectangle(width,3.,offset)]
    cp=doc.create_entity('IfcCompositeProfileDef',ProfileType='AREA',Profiles=profiles)
    solid.SweptArea=cp
    materials=[material,doc.create_entity('IfcMaterial',Name='Second material <declared>')]
    mp=[doc.create_entity('IfcMaterialProfile',Material=m,Profile=p) for m,p in zip(materials,profiles)]
    group=doc.create_entity('IfcMaterialProfileSet',MaterialProfiles=mp,CompositeProfile=cp)
    usage=doc.create_entity('IfcMaterialProfileSetUsage',ForProfileSet=group,CardinalPoint=5)
    associate(doc,element,usage)
    if case=='one_sided_opening':
        opening=element.HasOpenings[0].RelatedOpeningElement.Representation.Representations[0].Items[0]
        opening.Position.Location.Coordinates=(.5*scale,0.,0.)
    doc.write(str(path))
    return doc,element,profiles,materials,mp,solid,path
