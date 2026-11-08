from pathlib import Path
import json,hashlib
HERE=Path(__file__).parent;OUT=Path('C:/Users/18483/AppData/Local/Temp/vra-slab-layers-20261108')
R=Path('C:/Users/18483/AppData/Local/Temp/vra-drawing-components-20261108')
final=OUT/'final-public';final.mkdir(exist_ok=False)
(final/'frozen-public-gold-v2.json').write_bytes((OUT/'frozen-public-gold-v2.json').read_bytes())
(final/'source-hashes.json').write_text(json.dumps({n:hashlib.sha256((R/'backend'/n).read_bytes().replace(b'\r\n',b'\n')).hexdigest() for n in ['ifc_layer_quantities.py','ifc_material_collection.py','ifc_geometry.py','mesh_topology.py']},indent=2))
s=(HERE/'run_public_slab_gold.py').read_text(encoding='utf-8').replace("vra-slab-layers-20261108')", "vra-slab-layers-20261108/final-public')")
exec(compile(s,str(HERE/'run_public_slab_gold.py'),'exec'),{'__name__':'__main__'})
