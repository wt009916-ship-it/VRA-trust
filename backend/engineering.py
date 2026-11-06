"""Constant-EI Euler–Bernoulli beam analysis; not a structural safety assessment."""
import html
import json
import math
from pathlib import Path
from typing import Annotated, Literal
from pydantic import Field, StrictFloat, model_validator
from .calculation_provenance import validity, persist, version as provenance_version
from . import core
from .domain import identifier
from .schema import Contract

LENGTH = {'m':1.0, 'cm':.01, 'mm':.001}
MODULUS = {'Pa':1.0, 'MPa':1e6, 'GPa':1e9}
FORCE = {'N':1.0, 'kN':1000.0}
LINE_LOAD = {'N/m':1.0, 'kN/m':1000.0, 'N/mm':1000.0}
LengthUnit = Literal['m','cm','mm']


class PointLoad(Contract):
    type: Literal['point']
    name: str = Field(min_length=1, max_length=120)
    magnitude: StrictFloat | None = Field(default=None, ge=0, le=1e12)
    unit: Literal['N','kN']
    position: StrictFloat | None = Field(default=None, ge=0, le=1e9)
    position_unit: LengthUnit
    source: str = Field(min_length=5, max_length=1000)


class UniformLoad(Contract):
    type: Literal['uniform']
    name: str = Field(min_length=1, max_length=120)
    magnitude: StrictFloat | None = Field(default=None, ge=0, le=1e12)
    unit: Literal['N/m','kN/m','N/mm']
    start: StrictFloat | None = Field(default=None, ge=0, le=1e9)
    end: StrictFloat | None = Field(default=None, gt=0, le=1e9)
    position_unit: LengthUnit
    source: str = Field(min_length=5, max_length=1000)


class BeamInput(Contract):
    name: str = Field(min_length=1, max_length=160)
    support: Literal['simply_supported','cantilever']
    span: StrictFloat | None = Field(default=None, gt=0, le=1e9)
    span_unit: LengthUnit
    width: StrictFloat | None = Field(default=None, gt=0, le=1e9)
    depth: StrictFloat | None = Field(default=None, gt=0, le=1e9)
    section_unit: LengthUnit
    elastic_modulus: StrictFloat | None = Field(default=None, gt=0, le=1e15)
    modulus_unit: Literal['Pa','MPa','GPa']
    geometry_source: str = Field(min_length=5, max_length=1000)
    material_source: str = Field(min_length=5, max_length=1000)
    support_basis: str = Field(min_length=5, max_length=1000)
    analysis_basis: str = Field(min_length=10, max_length=2000)
    evidence_ids: list[str] = Field(default_factory=list, max_length=50)
    loads: list[Annotated[PointLoad | UniformLoad, Field(discriminator='type')]] = Field(min_length=1, max_length=100)

    @model_validator(mode='after')
    def dimensions(self):
        n = normalize(self)
        for key,low,high in [('span_m',1e-6,1e4),('width_m',1e-6,1e3),('depth_m',1e-6,1e3),('e_pa',1,1e15)]:
            if n[key] is not None and not low <= n[key] <= high:
                raise ValueError(key+' outside supported numerical range')
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError('Duplicate evidence identifiers')
        for load in n['loads']:
            positions = [load['position_m']] if load['type']=='point' else [load['start_m'],load['end_m']]
            if n['span_m'] is not None and any(x is not None and x > n['span_m'] for x in positions):
                raise ValueError('Load is outside beam span after unit conversion')
            if load['type']=='uniform' and all(x is not None for x in positions) and positions[0] >= positions[1]:
                raise ValueError('Uniform load requires start < end')
        return self


def normalize(body):
    convert = lambda value, scale: None if value is None else value*scale
    return {'span_m':convert(body.span,LENGTH[body.span_unit]), 'width_m':convert(body.width,LENGTH[body.section_unit]),
        'depth_m':convert(body.depth,LENGTH[body.section_unit]), 'e_pa':convert(body.elastic_modulus,MODULUS[body.modulus_unit]),
        'loads':[{'name':load.name, 'type':load.type, **(
            {'force_n':convert(load.magnitude,FORCE[load.unit]),'position_m':convert(load.position,LENGTH[load.position_unit])}
            if load.type=='point' else {'q_n_m':convert(load.magnitude,LINE_LOAD[load.unit]),
                'start_m':convert(load.start,LENGTH[load.position_unit]),'end_m':convert(load.end,LENGTH[load.position_unit])})} for load in body.loads]}


def checked(value):
    if not math.isfinite(value):
        raise core.ValidationError('Non-finite engineering result')
    return value


def calculate(body):
    n=normalize(body)
    missing=[key for key,value in n.items() if value is None]
    for i,load in enumerate(n['loads']):
        missing.extend(f'loads[{i}].{key}' for key,value in load.items() if value is None)
    base={'normalized':n, 'missing':missing, 'structural_safety':'NOT_ASSESSED', 'code_compliance':'NOT_ASSESSED',
        'source_status':'USER_DECLARED', 'self_weight_included_automatically':False,
        'sign_convention':'Loads and deflections downward positive; reactions upward; support reaction moment counterclockwise; internal moment sagging positive.',
        'limitations':['等截面矩形、恒定EI、小挠度线弹性Euler–Bernoulli梁；忽略剪切变形、扭转、轴力、屈曲和动力影响。',
            '只支持向下集中力及分段均布荷载；不自动加入自重、组合系数或材料设计强度。',
            '输入来源及支承理想化由用户声明；弯曲应力不是承载能力验算，不能输出结构安全或规范合格结论。',
            '跨高比、转角和挠跨比只用于模型适用性提示，阈值为本工具的筛查值，不是规范限值。'],
        'method_sources':['https://mude.citg.tudelft.nl/workbook-2025/assignments/WS1.3/2-solving-boundary-value-problems.html'],
        'method':'Factored Green-function integration of equilibrium and EI*y_second=M; reactions from statics; exact interval extrema and bisection of rotation, not plot-sample maxima.'}
    if missing:
        return {**base,'status':'incomplete','metrics':None,'samples':[]}
    span,width,depth,e=(n[k] for k in ('span_m','width_m','depth_m','e_pa'))
    inertia=checked(width*depth**3/12); rigidity=checked(e*inertia)
    points=[(x['force_n'],x['position_m']) for x in n['loads'] if x['type']=='point']
    uniforms=[(x['q_n_m'],x['start_m'],x['end_m']) for x in n['loads'] if x['type']=='uniform']
    weight=math.fsum([p for p,a in points]+[q*(b-a) for q,a,b in uniforms])
    moment=math.fsum([p*a for p,a in points]+[q*(b-a)*(a+b)/2 for q,a,b in uniforms])
    simply=body.support=='simply_supported'
    ra=(math.fsum([p*(span-a) for p,a in points]+[q*(b-a)*((span-b)+(span-a))/2 for q,a,b in uniforms])/span) if simply else weight
    rb=moment/span if simply else 0.0
    m0=0.0 if simply else -moment

    def shear(x,side):
        terms=[]
        for p,a in points:
            passed=a<x or (side=='right' and a==x)
            terms.append((-p*a/span if passed else p*(span-a)/span) if simply else (0.0 if passed else p))
        for q,a,b in uniforms:
            left=min(x,b); right=max(x,a)
            if simply:
                if left>a: terms.append(-q*(left-a)*(left+a)/(2*span))
                if right<b: terms.append(q*(b-right)*((span-b)+(span-right))/(2*span))
            elif right<b: terms.append(q*(b-right))
        return math.fsum(terms)
    def bending(x):
        terms=[]
        for p,a in points:
            terms.append((p*(span-a)*x/span if x<=a else p*a*(span-x)/span) if simply else -p*max(0,a-x))
        for q,a,b in uniforms:
            left=min(x,b); right=max(x,a)
            if simply:
                if left>a: terms.append(q*(span-x)*(left-a)*(left+a)/(2*span))
                if right<b: terms.append(q*x*(b-right)*((span-b)+(span-right))/(2*span))
            elif right<b: terms.append(-q*(b-right)*((b-x)+(right-x))/2)
        return math.fsum(terms)
    def simply_point(x,a,p):
        b=span-a
        if x>a:
            t=span-x
            return (p*a*t*(2*a*b+(x-a)*(span-a+t))/(6*span*rigidity),
                    -p*a*(b*(span+a)-3*t*t)/(6*span*rigidity))
        return (p*b*x*(2*a*b+(a-x)*(a+x))/(6*span*rigidity),
                p*b*(a*(span+b)-3*x*x)/(6*span*rigidity))
    def simply_left_patch(x,a,b,q):
        # All distributed forces lie left of x. Positive factored expressions
        # preserve very short patches and loads almost at either support.
        t=span-x; diff2=(b-a)*(b+a)
        d=q*t*diff2*(4*x*t+(x-b)*(x+b)+(x-a)*(x+a))/(24*span*rigidity)
        r=q*diff2*(6*t*t-(span-b)*(span+b)-(span-a)*(span+a))/(24*span*rigidity)
        return d,r
    def displacement_rotation(x):
        ds,rs=[],[]
        for p,a in points:
            if simply: d,r=simply_point(x,a,p)
            elif x<=a: d,r=p*x*x*(3*a-x)/(6*rigidity),p*x*(2*a-x)/(2*rigidity)
            else: d,r=p*a*a*(3*x-a)/(6*rigidity),p*a*a/(2*rigidity)
            ds.append(d);rs.append(r)
        for q,a,b in uniforms:
            left=min(x,b);right=max(x,a)
            if left>a:
                if simply: d,r=simply_left_patch(x,a,left,q)
                else:
                    diff3=(left-a)*(left*left+left*a+a*a)
                    diff4=(left-a)*(left+a)*(left*left+a*a)
                    d,r=q*(x*diff3-diff4/4)/(6*rigidity),q*diff3/(6*rigidity)
                ds.append(d);rs.append(r)
            if right<b:
                if simply:
                    # Preserve the original patch length; mirroring twice loses
                    # sub-ulp distances close to the left support.
                    factor=q*(b-right)*((span-b)+(span-right))/(24*span*rigidity)
                    d=factor*x*(4*(span-x)*x+(b-x)*(span-x+span-b)+(right-x)*(span-x+span-right))
                    r=-factor*(6*x*x-b*(span+span-b)-right*(span+span-right))
                else:
                    length=b-right
                    d=q*x*x*length*(1.5*(b+right)-x)/(6*rigidity)
                    r=q*x*length*(b+right-x)/(2*rigidity)
                ds.append(d);rs.append(r)
        return math.fsum(ds),math.fsum(rs)
    def rotation(x): return displacement_rotation(x)[1]
    def deflection(x): return displacement_rotation(x)[0]
    c1=-rotation(0)
    breaks=sorted({0.0,span,*[a for p,a in points],*[x for q,a,b in uniforms for x in (a,b)]})
    moment_candidates=list(breaks)
    for a,b in zip(breaks,breaks[1:]):
        q=math.fsum(q for q,start,end in uniforms if start <= a and end >= b)
        if q:
            root=a+shear(a,'right')/q
            if a < root < b: moment_candidates.append(root)
    max_m_x=max(moment_candidates,key=lambda x:abs(bending(x)))
    shear_candidates=[(x,side,shear(x,side)) for x in breaks for side in ('left','right')
                      if not (x==0 and side=='left') and not (x==span and side=='right')]
    max_v=max(shear_candidates,key=lambda item:abs(item[2]))
    if simply and weight:
        lo,hi=0.0,span
        for _ in range(70):
            middle=(lo+hi)/2
            if rotation(middle)>0: lo=middle
            else: hi=middle
        max_d_x=(lo+hi)/2
    else: max_d_x=span if weight else 0.0
    max_d=abs(deflection(max_d_x))
    max_rotation=max(abs(rotation(x)) for x in breaks)
    span_depth=span/depth; deflection_ratio=max_d/span
    screening=[]
    if span_depth < 10: screening.append('span/depth < 10: shear deformation may be material; not a code limit')
    if deflection_ratio > .05: screening.append('deflection/span > 0.05: small-deflection assumption requires review; not a code limit')
    if max_rotation > .1: screening.append('rotation > 0.1 rad: linearized geometry requires review; not a code limit')
    positions=sorted({span*i/80 for i in range(81)}|set(breaks)|set(moment_candidates)|{max_d_x})
    samples=[{'x_m':x,'shear_left_n':None if x==0 else checked(shear(x,'left')),
        'shear_right_n':None if x==span else checked(shear(x,'right')), 'moment_nm':checked(bending(x)),
        'deflection_down_m':checked(deflection(x)), 'rotation_down_rad':checked(rotation(x))} for x in positions]
    metrics={'area_m2':width*depth,'inertia_m4':inertia,'ei_nm2':rigidity,'total_downward_load_n':weight,
        'left_reaction_n':ra,'right_reaction_n':rb,'left_reaction_moment_nm':-m0,
        'max_abs_moment_nm':abs(bending(max_m_x)), 'max_moment_at_m':max_m_x,
        'max_abs_shear_n':abs(max_v[2]), 'max_shear_at_m':max_v[0], 'max_shear_side':max_v[1],
        'max_deflection_m':max_d,'max_deflection_at_m':max_d_x,'max_abs_rotation_rad':max_rotation,
        'max_elastic_bending_stress_pa':abs(bending(max_m_x))*depth/(2*inertia),
        'span_depth_ratio':span_depth,'deflection_span_ratio':deflection_ratio}
    for value in metrics.values():
        if isinstance(value,(float,int)): checked(value)
    return {**base,'status':'outside_model_screen' if screening else 'calculated','metrics':metrics,'samples':samples,
        'model_screening':screening,'integration_constants':{'y_at_left_m':0,'upward_slope_constant_rad':c1},
        'equilibrium_residual':{'force_n':math.fsum([ra,rb,-weight]),'moment_nm':math.fsum([rb*span,-m0,-moment])},
        'formulas':['y is upward-positive; output deflection_down=-y and rotation_down=-y_prime','I=b*h^3/12','EI*y_second=M(x)','M(x)=M0+RA*x-sum(P*<x-a>)-sum(q*(<x-a>^2-<x-b>^2)/2)',
            'EI*y=M0*x^2/2+RA*x^3/6-sum(P*<x-a>^3/6)-sum(q*(<x-a>^4-<x-b>^4)/24)+EI*C1*x',
            'simply supported: y(0)=y(L)=0; cantilever: y(0)=y_prime(0)=0','sigma_max=abs(M_max)*(h/2)/I']}


class Engineering:
    def __init__(self,domain): self.domain,self.store=domain,domain.store

    def save(self,pid,body, *, expected_bindings=None):
        project=self.store.get('project',pid); snapshots=[]
        for eid in body.evidence_ids:
            evidence=self.store.get('evidence',eid)
            if evidence['project_id']!=pid: raise core.ValidationError('Cross-project engineering evidence rejected')
            if evidence['review_state']=='rejected': raise core.ValidationError('Withdrawn engineering evidence cannot support a new calculation')
            if evidence['source_file']: self.domain.file_record(pid,evidence['source_file'])
            snapshots.append(evidence)
        obj={'engineering_id':identifier('engineering'),'project_id':pid,'project_revision':project['revision'],
            'input':body.model_dump(),'result':calculate(body),'source_snapshot':snapshots,'created_at':core.now(),
            'calculator_hash':provenance_version(Path(__file__))}
        obj['hash']=core.hash_json(obj);persist(self.domain, 'engineering', obj, expected_bindings)
        return self.view(pid,obj['engineering_id'])

    def view(self,pid,eid):
        obj=self.store.get('engineering',eid)
        if obj['project_id']!=pid: raise core.ValidationError('Cross-project engineering record rejected')
        if core.hash_json({k:v for k,v in obj.items() if k not in {'hash','revision'}})!=obj['hash']:
            raise core.ValidationError('Engineering record integrity failed')
        provenance = validity(self.domain, obj, provenance_version(Path(__file__)))
        stale = provenance['stale_reasons']
        return {**obj, **provenance,'status':'stale' if stale else obj['result']['status'],'result':None if stale else obj['result']}


def report(record):
    escaped=html.escape; result=record.get('result'); metrics=(result or {}).get('metrics')
    summary='<p>来源已失效或输入不完整，不能给出当前计算值。</p>'
    if metrics:
        summary='<table>'+''.join('<tr><th>'+escaped(k)+'</th><td>'+escaped(str(v))+'</td></tr>' for k,v in metrics.items())+'</table>'
    return ('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>梁分析记录</title>'
        '<style>body{max-width:960px;margin:40px auto;padding:20px;font:16px/1.7 system-ui}td,th{border:1px solid #ccc;padding:6px;text-align:left}table{border-collapse:collapse}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style>'
        '<h1>'+escaped(record['input']['name'])+'</h1><p>线弹性梁计算辅助；未评估结构安全或规范符合性。</p><p>状态：'+escaped(record['status'])+'</p>'+summary+
        '<h2>输入、单位换算、计算过程与来源快照</h2><pre>'+escaped(json.dumps(record,ensure_ascii=False,indent=2,allow_nan=False))+'</pre></html>')
