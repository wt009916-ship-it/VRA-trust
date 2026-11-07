from pathlib import Path
p=Path('validation/ifc-union-20261107/public_oracle_v1.py');s=p.read_text(encoding='utf-8')
s=s.replace('groups=[];overlap=separate=0','groups=[];overlap=separate=near=0')
s=s.replace("if intersection>0 and overlap<6:overlap+=1","if intersection>D('1e-8') and overlap<6:overlap+=1\n elif D(0)<intersection<=D('1e-8') and near<3:near+=1")
s=s.replace("'zero_overlap_pairs':separate","'zero_overlap_pairs':separate,'sub_1e8_overlap_pairs':near")
s=s.replace('public-gold-v1.json','public-gold-v2.json')
Path('validation/ifc-union-20261107/public_oracle_v2.py').write_text(s,encoding='utf-8')
