from pathlib import Path
p=Path('backend/ifc_union.py');s=p.read_text(encoding='utf-8')
s=s.replace('def relative_placement(chain, origin, scale):','def relative_placement(chain, origin, scale, basis):')
s=s.replace("    matrix[:3, 3] -= origin\n    for local in chain[1:]:","""    matrix[:3, 3] = basis.T @ (matrix[:3, 3] - origin)
    matrix[:3, :3] = np.eye(3) if np.array_equal(matrix[:3, :3], basis) else basis.T @ matrix[:3, :3]
    for local in chain[1:]:""")
s=s.replace("    result['common_origin_m'] = (origin*scale).tolist()","""    basis = chains[0][0][:3, :3]
    if not np.allclose(basis.T @ basis, np.eye(3), atol=1e-12, rtol=0):
        return refuse('unsupported_relative_placement')
    result['common_origin_m'] = (origin*scale).tolist()
    result['common_basis_world'] = basis.tolist()""")
s=s.replace('relative_placement(chain, origin, scale)','relative_placement(chain, origin, scale, basis)')
p.write_text(s,encoding='utf-8',newline='\n')
p=Path('frontend/src/ifc-union-ui.js');s=p.read_text(encoding='utf-8').replace('  },event.submitter);','  });')
p.write_text(s,encoding='utf-8',newline='\n')
