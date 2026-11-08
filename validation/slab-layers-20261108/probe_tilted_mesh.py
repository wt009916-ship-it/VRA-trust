import sys,json,itertools
from pathlib import Path
import ifcopenshell,ifcopenshell.geom,numpy as np
R=Path('C:/Users/18483/AppData/Local/Temp/vra-drawing-components-20261108');sys.path.insert(0,str(R))
from backend.ifc_geometry import mesh_measurements
OUT=Path('C:/Users/18483/AppData/Local/Temp/vra-slab-layers-20261108')
doc=ifcopenshell.open(str(OUT/'diagnostic/slab.ifc'));p=doc.by_type('IfcSlab')[0]
s=ifcopenshell.geom.settings()
for k,v in {'use-world-coords':False,'convert-back-units':False,'weld-vertices':True,'mesher-linear-deflection':.001,'mesher-angular-deflection':.5,'disable-opening-subtractions':False,'boolean-attempt-2d':False}.items():s.set(k,v)
shape=ifcopenshell.geom.create_shape(s,p,p.Representation.Representations[0]);v=np.array(shape.geometry.verts).reshape(-1,3);f=np.array(shape.geometry.faces).reshape(-1,3)
pairs=[{'indices':[i,j],'distance':float(np.linalg.norm(a-b)),'a':a.tolist(),'b':b.tolist()} for (i,a),(j,b) in itertools.combinations(enumerate(v),2) if 0<np.linalg.norm(a-b)<1e-10]
record={'settings':s.setting_names(),'near_pairs':pairs,'vertices':v.tolist(),'faces':f.tolist(),'check':mesh_measurements(v,f)}
(OUT/'native-tilted-mesh-probe.json').write_text(json.dumps(record,indent=2))
print(json.dumps({'near_pairs':pairs,'check':record['check']}))
