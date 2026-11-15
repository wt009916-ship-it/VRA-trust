"""Frozen alternative mesh experiment only; never writes application source."""
import hashlib,json,math,sys,time
from pathlib import Path
import numpy as np
ROOT=Path('D:/稀土agent-稀土制暖全流程/.codex_work/vra-resource-leveling-20261115')
BASE=Path(__file__).parent
sys.path.insert(0,str(ROOT))
from backend.thermal_bridge import Section,normalize
from backend import thermal_bridge_solver as solver

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,r):p.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def graded_edges(length,regions,axis,step):
    cuts=sorted({0.,length,*(r[axis+'0'] for r in regions),*(r[axis+'1'] for r in regions)})
    result=[]
    for a,b in zip(cuts,cuts[1:]):
        if b-a<1e-8:raise ValueError('Geometry spacing exceeds supported budget')
        widths=[];total=0.;h=step/8
        while total<(b-a)/2:
            widths.append(h);total+=h;h=min(step,h*1.5)
            if len(widths)*2>solver.MAX_CELLS:raise ValueError('Mesh axis exceeds supported budget')
        widths=np.asarray(widths)*((b-a)/2/total)
        left=np.concatenate([[a],a+np.cumsum(widths)])
        local=np.concatenate([left,b-(left[-2::-1]-a)])
        result.extend(local[:-1])
    result.append(length)
    return np.asarray(result)

source=ROOT/'validation/thermal-bridge-20261114/composite-reference-frozen.json'
reference=json.loads(source.read_text(encoding='utf-8'))
cases=[]
for size in [4.,2.]:
    body={**reference['input'],'cell_size':size}
    data=normalize(Section(**body))
    cases.append({'name':f'graded-{size:g}mm','input':body,'normalized':data})
frozen={'source_sha256':sha(source),'script_sha256':sha(Path(__file__)),'solver_sha256':sha(Path(solver.__file__)),
    'cases':cases,'expected':reference['expected'],'method':{'growth':1.5,'near_interface_fraction':.125,'max_cells':160000,'max_iterations':6000,'deadline_seconds':25},
    'purpose':'Independent experiment, not installed in application or accepted as field validation'}
assert not (BASE/'frozen.json').exists();save(BASE/'frozen.json',frozen)
solver.edges=graded_edges
receipt={'cases':[],'frozen_sha256':sha(BASE/'frozen.json'),'product_changed':False}
for case in cases:
    start=time.monotonic()
    try:
        result=solver.calculate(case['normalized']);save(BASE/(case['name']+'.json'),result)
        expected=reference['expected'];error=max(abs(p['temperature_c']-expected['temperature_c'][p['name']]) for p in result['probes'])
        row={'name':case['name'],'status':result['status'],'max_probe_error_k':error,'heat_w_per_m':result['boundary_heat_into_domain_w_per_m']['bottom'],
            'mesh_check':result['mesh_check'],'linear_solver':result['linear_solver'],
            'reference_points_passed':error<=.1,'reference_heat_passed':abs(result['boundary_heat_into_domain_w_per_m']['bottom']-9.5)<=.1}
    except Exception as e:row={'name':case['name'],'status':'failed','error':type(e).__name__+': '+str(e)}
    row['seconds']=time.monotonic()-start;receipt['cases'].append(row);save(BASE/'receipt.json',receipt);print(json.dumps(row),flush=True)
