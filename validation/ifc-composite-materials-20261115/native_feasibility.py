import json
from pathlib import Path
from reference_fixture import composite
from backend.ifc_geometry import inspect_shapes
import ifcopenshell
root=Path(__file__).parent/'feasibility';root.mkdir(exist_ok=True)
rows=[]
for case in ['adjacent','one_sided_opening','cross_material_opening','tube_core_opening','overlap']:
    folder=root/case;folder.mkdir(exist_ok=True)
    doc,element,profiles,_,_,solid,path=composite(folder,case=case)
    whole=inspect_shapes(doc,[element],1.)['objects'][0]
    parts=[]
    for profile in profiles:
        clone=ifcopenshell.file.from_string(doc.to_string())
        clone.by_id(solid.id()).SweptArea=clone.by_id(profile.id())
        part=inspect_shapes(clone,[clone.by_id(element.id())],1.)['objects'][0]
        parts.append({'status':part['status'],'volume_m3':part['volume_m3']})
    rows.append({'case':case,'raw_whole_status':whole['status'],'raw_whole_volume_m3':whole['volume_m3'],'parts':parts})
(root/'result.json').write_text(json.dumps(rows,indent=2)+'\n')
print(json.dumps(rows))
