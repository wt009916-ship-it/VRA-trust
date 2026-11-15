import json,sys
from pathlib import Path
repo=Path('C:/Users/18483/AppData/Local/Temp/vra-timestep-reliability-20261108');sys.path[:0]=[str(repo),str(repo/'tests')]
from test_ifc_composite_materials import composite
from backend.ifc_layer_quantities import measure_layers
out=Path(__file__).parent/'invalid-profile-before';out.mkdir(exist_ok=False)
doc,element,_,_,_,solid,path=composite(out,case='adjacent')
solid.SweptArea.ProfileType='CURVE';doc.write(str(path))
result=measure_layers(path,element.id())
(out/'result.json').write_text(json.dumps({'expected':'unavailable because a swept solid requires an AREA profile','actual':result},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'expected':'unavailable','actual':result['status'],'volume_m3':result['total_layer_envelope_m3']}))
