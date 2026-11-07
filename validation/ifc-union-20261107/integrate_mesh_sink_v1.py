from pathlib import Path
p=Path('backend/ifc_geometry.py');s=p.read_text(encoding='utf-8')
s=s.replace('def inspect_shapes(doc, products, length_scale):','def inspect_shapes(doc, products, length_scale, mesh_sink=None):')
old="            row['status'] = 'measured_mesh' if row['volume_m3'] is not None else 'partial_mesh'"
new=old+"\n            if mesh_sink is not None and row['volume_m3'] is not None:\n                mesh_sink.append({'id': element.id(), 'vertices': verts, 'faces': faces, 'matrix': matrix})"
assert s.count(old)==1;s=s.replace(old,new);p.write_text(s,encoding='utf-8',newline='\n')
