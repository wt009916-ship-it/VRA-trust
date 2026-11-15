from decimal import Decimal as D
import hashlib, json
from pathlib import Path
root=Path(__file__).parent
def mul(*values):
    value=D(1)
    for x in values:value*=D(str(x))
    return str(value)
out={'method':'independent Decimal rectangular solids; frozen before product partition implementation',
 'absolute_tolerance_m3':'0.00000001',
 'adjacent':{'material_m3':[mul(1,3,4),mul(1,3,4)],'whole_m3':mul(2,3,4)},
 'one_sided_opening':{'material_m3':['12','10'],'whole_m3':'22','opening_m3':mul(.5,1,4)},
 'cross_material_opening':{'material_m3':['11','11'],'whole_m3':'22'},
 'tube_core_opening':{'material_m3':[str((mul and D(2)*D(3)-D('1.5')*D('2.5'))*D(4)),'13'],'whole_m3':'22'},
 'overlap':{'expected':'unavailable','intersection_m3':mul(.4,3,4)},
 'two_disjoint_members':{'material_m3':['22','22'],'whole_m3':'44'}}
p=root/'reference-frozen.json'
assert not p.exists(), 'Do not rewrite frozen reference'
p.write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8')
print(hashlib.sha256(p.read_bytes()).hexdigest())
