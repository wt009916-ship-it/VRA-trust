from pathlib import Path
p=Path('backend/cad_worker.py');s=p.read_text(encoding='utf-8')
a="'container_id': container.id() if container else None, **declarations(e, units)})"
b="'container_id': container.id() if container else None,\n            'eligible_for_union':e.is_a('IfcElement') and not e.is_a('IfcFeatureElement'), **declarations(e, units)})"
assert s.count(a)==1;s=s.replace(a,b);p.write_text(s,encoding='utf-8',newline='\n')
p=Path('frontend/src/cad-ui.js');s=p.read_text(encoding='utf-8');s="import {mountUnionWorkspace} from './ifc-union-ui.js';\n"+s
s=s.replace("  const base='/projects/'+state.project.project_id;","  const base='/projects/'+state.project.project_id;\n  let disposeUnion=()=>{};")
s=s.replace('<div id="cad-source"></div><div id="cad-results"','<div id="cad-source"></div><div id="cad-union"></div><div id="cad-results"')
a="    const records=await request(base+'/cad-inspections');if(!host.isConnected)return;"
assert s.count(a)==1;s=s.replace(a,a+"\n    disposeUnion();disposeUnion=mountUnionWorkspace(records,host.querySelector('#cad-union'),base,action);")
p.write_text(s,encoding='utf-8',newline='\n')
