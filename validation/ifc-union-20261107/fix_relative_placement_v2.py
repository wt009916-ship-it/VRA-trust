from pathlib import Path
p=Path('backend/ifc_union.py');s=p.read_text(encoding='utf-8')
marker='\ndef measure_union(path, ids):'
helper='''

def placement_chain(placement):
    from ifcopenshell.util.placement import get_axis2placement
    chain, seen = [], set()
    while placement is not None:
        if not placement.is_a('IfcLocalPlacement') or placement.id() in seen or len(chain) >= 128:
            raise ValueError('Unsupported or cyclic IFC placement')
        seen.add(placement.id())
        axis = get_axis2placement(placement.RelativePlacement)
        if not np.isfinite(axis).all():
            raise ValueError('Nonfinite IFC placement')
        chain.append(axis)
        placement = placement.PlacementRelTo
    if not chain:
        raise ValueError('Missing IFC placement')
    return chain[::-1]


def relative_placement(chain, origin, scale):
    # Cancel the root engineering offset before composing any child translation.
    # Subtracting it from the already composed native matrix loses precision.
    matrix = np.array(chain[0], dtype=float, copy=True)
    matrix[:3, 3] -= origin
    for local in chain[1:]:
        matrix = matrix @ local
    matrix[:3, 3] *= scale
    if not np.isfinite(matrix).all():
        raise ValueError('Nonfinite IFC relative placement')
    return matrix

'''
assert s.count(marker)==1;s=s.replace(marker,helper+marker)
s=s.replace("origin = meshes[0]['matrix'][:3, 3].copy()\n    result['common_origin_m'] = origin.tolist()", """try:
        chains = [placement_chain(element.ObjectPlacement) for element in selected]
    except (RuntimeError, ValueError, TypeError, AttributeError):
        return refuse('unsupported_relative_placement')
    origin = chains[0][0][:3, 3].copy()
    result['common_origin_m'] = (origin*scale).tolist()""")
s=s.replace("for mesh, row in zip(meshes, rows):\n        vertices = mesh['vertices'] @ mesh['matrix'][:3, :3].T + (mesh['matrix'][:3, 3] - origin)","for mesh, row, chain in zip(meshes, rows, chains):\n        matrix = relative_placement(chain, origin, scale)\n        vertices = mesh['vertices'] @ matrix[:3, :3].T + matrix[:3, 3]")
p.write_text(s,encoding='utf-8',newline='\n')
p=Path('tests/test_ifc_union.py');s=p.read_text(encoding='utf-8').replace('from pathlib import Path\n','').replace('from backend import core\n','')
p.write_text(s,encoding='utf-8',newline='\n')
