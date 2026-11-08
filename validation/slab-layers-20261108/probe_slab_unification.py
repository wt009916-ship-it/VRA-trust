import sys,json
from pathlib import Path
import ifcopenshell,ifcopenshell.geom,numpy as np
R=Path('C:/Users/18483/AppData/Local/Temp/vra-drawing-components-20261108');sys.path.insert(0,str(R))
from backend.ifc_geometry import mesh_measurements
OUT=Path('C:/Users/18483/AppData/Local/Temp/vra-slab-layers-20261108')
doc=ifcopenshell.open(str(OUT/'diagnostic/slab.ifc'));p=doc.by_type('IfcSlab')[0];result=[]
for unify in (False,True):
    s=ifcopenshell.geom.settings()
    for k,v in {'use-world-coords':False,'convert-back-units':False,'weld-vertices':True,'mesher-linear-deflection':.001,'mesher-angular-deflection':.5,'disable-opening-subtractions':False,'boolean-attempt-2d':False,'unify-shapes':unify}.items():s.set(k,v)
    shape=ifcopenshell.geom.create_shape(s,p,p.Representation.Representations[0]);v=np.array(shape.geometry.verts).reshape(-1,3);f=np.array(shape.geometry.faces).reshape(-1,3)
    result.append({'unify_shapes':unify,'check':mesh_measurements(v,f)})
(OUT/'native-unification-probe.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result))
