from pathlib import Path
p=Path('backend/ifc_union.py');s=p.read_text(encoding='utf-8')
s=s.replace("    selected = [lookup[i] for i in ids]","    selected = [lookup[i] for i in ids]\n    chains = [placement_chain(element.ObjectPlacement) for element in selected]")
s=s.replace("    try:\n        chains = [placement_chain(element.ObjectPlacement) for element in selected]\n    except (RuntimeError, ValueError, TypeError, AttributeError):\n        return refuse('unsupported_relative_placement')\n","")
p.write_text(s,encoding='utf-8',newline='\n')
