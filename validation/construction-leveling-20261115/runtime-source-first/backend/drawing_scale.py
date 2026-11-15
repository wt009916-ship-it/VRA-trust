"""User-declared pixel references, interval consistency and scoped length estimates."""
import math
from pathlib import Path
from typing import Literal
from pydantic import Field, StrictFloat, model_validator
from .schema import Contract
from . import core
from .domain import identifier
from .drawing_processing import point


class PixelPoint(Contract):
    x: StrictFloat = Field(ge=0,le=6000)
    y: StrictFloat = Field(ge=0,le=6000)


class ScaleReference(Contract):
    label: str = Field(min_length=1,max_length=120)
    start: PixelPoint
    end: PixelPoint
    length: StrictFloat = Field(gt=0,le=1e9)
    unit: Literal['mm','cm','m']
    length_uncertainty: StrictFloat = Field(ge=0,le=1e8)
    point_uncertainty_px: StrictFloat = Field(ge=0,le=100)

    @model_validator(mode='after')
    def uncertainty(self):
        if self.length_uncertainty>=self.length:raise ValueError('Length uncertainty must be below length')
        return self


class ScaleInput(Contract):
    basis_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    references: list[ScaleReference] = Field(min_length=1,max_length=8)
    relative_tolerance: StrictFloat = Field(ge=0,le=0.05)
    basis: str = Field(min_length=10,max_length=2000)
    plane_assumption: Literal['user_declares_uniform_scale_on_this_page']


class LengthInput(Contract):
    start: PixelPoint
    end: PixelPoint
    coordinates: Literal['source','preview']


def geometry_basis(record):
    result=record.get('result')
    if not result or 'processing' not in result:raise core.ValidationError('Current processed drawing required; create a new record')
    return core.hash_json({'drawing_id':record['drawing_id'],'source_hash':record['source']['hash'],
                          'page':record['input']['page'],'parser_hash':record['parser_hash'],
                          'preview':result['preview_sha256'],'processing':result['processing']})


def checked_point(value, size):
    xy=[value.x,value.y]
    if not 0<=xy[0]<=size[0] or not 0<=xy[1]<=size[1]:raise core.ValidationError('Point outside normalized source raster')
    return xy


def calculate(body, source_size):
    rows=[];seen=set()
    for ref in body.references:
        start=checked_point(ref.start,source_size);end=checked_point(ref.end,source_size)
        key=tuple(sorted((tuple(start),tuple(end))))
        if key in seen:raise core.ValidationError('Duplicate or reversed reference segment is not an independent reference')
        seen.add(key)
        distance=math.dist(start,end);uncertainty=2*ref.point_uncertainty_px
        if distance<=uncertainty:raise core.ValidationError('Reference points coincide or uncertainty covers their distance')
        factor={'mm':.001,'cm':.01,'m':1}[ref.unit]
        nominal=ref.length*factor/distance
        lower=(ref.length-ref.length_uncertainty)*factor/(distance+uncertainty)*(1-body.relative_tolerance)
        upper=(ref.length+ref.length_uncertainty)*factor/(distance-uncertainty)*(1+body.relative_tolerance)
        rows.append({'label':ref.label,'distance_px':distance,'length_m':ref.length*factor,'m_per_px':nominal,
                     'interval_m_per_px':[lower,upper],'source_kind':'USER_DECLARED_REFERENCE'})
    low=max(r['interval_m_per_px'][0] for r in rows);high=min(r['interval_m_per_px'][1] for r in rows)
    # Floating-point roundoff only; never a configurable tolerance that conceals conflicting references.
    conflict=low>high and not math.isclose(low,high,rel_tol=1e-12,abs_tol=0.)
    if not conflict and low>high:low=high=(low+high)/2
    sufficient=len(rows)>=2
    state='conflicting_references' if conflict else 'single_reference_unverified' if not sufficient else 'consistent_declared_references'
    accepted=sufficient and not conflict
    return {'status':state,'references':rows,'scale_m_per_px':(low+high)/2 if accepted else None,
            'interval_m_per_px':[low,high] if accepted else None,'method':'intersection midpoint of declared uncertainty/tolerance intervals; no averaging conflicts',
            'tolerance_origin':'user supplied, not a building-code tolerance',
            'limitations':['标定尺寸、点位误差和同页等比假设由用户声明，未独立测绘核验。',
                           '一致只表示输入区间相交，不证明图纸没有透视、局部拉伸或错误标注。',
                           '至少两条相符参考才提供条件长度估算；单条参考不推断全图比例尺。',
                           '不输出墙体工程量、结构安全结论或认证结果，不自动改写工程参数。']}


class DrawingScales:
    def __init__(self, drawings):
        self.drawings=drawings;self.store=drawings.store

    def version(self):
        return core.sha(Path(__file__))

    def save(self,pid,did,body,author):
        drawing=self.drawings.view(pid,did)
        if drawing['status']=='stale' or geometry_basis(drawing)!=body.basis_hash:
            raise core.ValidationError('Drawing basis changed; reread the current source')
        result=calculate(body,drawing['result']['processing']['transform']['source_size'])
        obj={'scale_id':identifier('scale'),'project_id':pid,'drawing_id':did,'basis_hash':body.basis_hash,
             'input':body.model_dump(),'result':result,'author_id':author,'created_at':core.now(),'calculator_hash':self.version()}
        obj['hash']=core.hash_json(obj)
        with self.store.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            count=con.execute("SELECT count(DISTINCT id) FROM records WHERE kind='scale' AND project_id=?",(pid,)).fetchone()[0]
            if count>=200:raise core.ValidationError('Project scale record limit is 200')
            current=self.drawings.view(pid,did)
            if current['status']=='stale' or geometry_basis(current)!=body.basis_hash:raise core.ValidationError('Drawing changed during scale calculation')
            self.store.put_in(con,'scale',obj)
        return self.view(pid,did,obj['scale_id'])

    def view(self,pid,did,sid):
        record=self.store.get('scale',sid)
        if record['project_id']!=pid or record['drawing_id']!=did:raise core.ValidationError('Cross-drawing scale rejected')
        if core.hash_json({k:v for k,v in record.items() if k not in {'revision','hash'}})!=record['hash']:
            raise core.ValidationError('Scale record integrity failed')
        drawing=self.drawings.view(pid,did)
        stale=drawing['status']=='stale' or record['calculator_hash']!=self.version() or geometry_basis(drawing)!=record['basis_hash']
        return {**record,'status':'stale' if stale else record['result']['status'],'result':None if stale else record['result']}

    def measure(self,pid,did,sid,body):
        scale=self.view(pid,did,sid)
        if scale['status']!='consistent_declared_references':raise core.ValidationError('Current consistent scale references required')
        drawing=self.drawings.view(pid,did)
        if drawing['status']=='stale' or geometry_basis(drawing)!=scale['basis_hash']:raise core.ValidationError('Drawing changed during measurement')
        transform=drawing['result']['processing']['transform']
        values=[]
        for value in (body.start,body.end):
            xy=checked_point(value,transform['preview_size'] if body.coordinates=='preview' else transform['source_size'])
            if body.coordinates=='preview':xy=point(transform['preview_to_source'],xy)
            if not all(-1e-7<=v<=limit+1e-7 for v,limit in zip(xy,transform['source_size'])):
                raise core.ValidationError('Point lies in added preview padding, outside the original raster')
            values.append(xy)
        length=math.dist(*values)
        if length==0:raise core.ValidationError('Measurement points coincide')
        return {'scale_id':sid,'drawing_id':did,'basis_hash':scale['basis_hash'],'scale_record_hash':scale['hash'],
                'calculator_hash':self.version(),'input':body.model_dump(),'source_points_px':values,'distance_px':length,
                'length_m':length*scale['result']['scale_m_per_px'],
                'scale_interval_length_m':[length*x for x in scale['result']['interval_m_per_px']],
                'status':'conditional_length_estimate','source_kind':'USER_DECLARED_SCALE',
                'notice':'区间仅传播标定尺度不确定性，不包含本次选点、扫描畸变或原尺寸错误；不是实测或工程量。'}
