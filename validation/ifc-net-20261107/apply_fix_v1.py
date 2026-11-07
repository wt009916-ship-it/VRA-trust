from pathlib import Path
p=Path('backend/ifc_geometry.py');s=p.read_text(encoding='utf-8')
old="'disable-opening-subtractions': False}"
assert s.count(old)==1
s=s.replace(old,"'disable-opening-subtractions': False, 'boolean-attempt-2d': False}")
s=s.replace("    settings = ifcopenshell.geom.settings()","    # 2D boolean shortcut can ignore an opening that wholly covers its host.\n    # Force 3D subtraction; empty native meshes remain unknown, never gross volume.\n    settings = ifcopenshell.geom.settings()")
p.write_text(s,encoding='utf-8',newline='\n')
