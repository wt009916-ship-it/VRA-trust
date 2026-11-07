import json,sys
from pathlib import Path
repo=Path.cwd();out=Path(__file__).resolve().parent;sys.path.insert(0,str(repo))
import ifcopenshell,ifcopenshell.geom
from backend.ifc_geometry import mesh_measurements
rows=[]
for original in json.loads((out/'probe-windows-v1.json').read_text())['cases']:
    doc=ifcopenshell.open(str(out/original['file']))
    project=doc.by_type('IfcProject')[0]
    angle=doc.create_entity('IfcSIUnit',UnitType='PLANEANGLEUNIT',Name='RADIAN')
    project.UnitsInContext.Units=list(project.UnitsInContext.Units)+[angle]
    for a in doc.by_type('IfcAxis2Placement3D'):
        if a.Axis is None:a.Axis=doc.create_entity('IfcDirection',DirectionRatios=(0.,0.,1.))
        if a.RefDirection is None:a.RefDirection=doc.create_entity('IfcDirection',DirectionRatios=(1.,0.,0.))
    path=out/(original['case']+'-explicit.ifc');doc.write(str(path));wall=doc.by_type('IfcWall')[0]
    for attempt in [True,False]:
        s=ifcopenshell.geom.settings()
        for key,value in {'use-world-coords':False,'convert-back-units':False,'weld-vertices':True,'mesher-linear-deflection':.001,
                          'mesher-angular-deflection':.5,'disable-opening-subtractions':False,'boolean-attempt-2d':attempt}.items():s.set(key,value)
        ifcopenshell.get_log();error=None;volume=None;status=None
        try:
            shape=ifcopenshell.geom.create_shape(s,wall,wall.Representation.Representations[0])
            measured=mesh_measurements(shape.geometry.verts,shape.geometry.faces);volume=measured['volume_m3'];status=measured['mesh_status']
        except Exception as exc:error=type(exc).__name__+': '+str(exc);status='native_failure'
        rows.append({'case':original['case'],'boolean_attempt_2d':attempt,'volume_m3':volume,'status':status,'error':error,
          'independent_expected_m3':original['independent_geometric_net_m3'],'native_log':ifcopenshell.get_log()})
with (out/'boolean-ab-windows-v1.json').open('x',encoding='utf-8') as f:json.dump({'cases':rows,'source_modified':False,'variant':'Explicit axes and plane angle units in separate synthetic files'},f,indent=2)
print(json.dumps([{k:v for k,v in r.items() if k not in ['native_log','error']} for r in rows]))
