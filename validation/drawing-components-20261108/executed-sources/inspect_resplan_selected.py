from pathlib import Path
import json,sys
sys.path.insert(0,str(Path(__file__).parent/'drawing-components'))
from wkb_reference import polygons,extent
root=Path('C:/Users/18483/AppData/Local/Temp/vra-floorplan-feasibility-20261108')
data=json.loads((root/'selected-geometries.json').read_text())
for plan in data['plans']:
    row={'id':plan['id']}
    for label in ('wall','door','front_door','window'):
        values=polygons(plan[label]['_wkb_hex'])
        row[label]={'count':len(values),'first_bounds':extent(values[0]) if values else None}
    print(json.dumps(row),flush=True)
