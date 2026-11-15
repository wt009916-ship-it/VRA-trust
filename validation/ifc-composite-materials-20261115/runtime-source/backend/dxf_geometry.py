"""Bounded source-linked DXF block expansion and geometric measurements.

No entity is rewritten; measurements do not assign building semantics or net QTO.
"""
import math
from collections import Counter
from fractions import Fraction

from ezdxf.math import Matrix44, Vec3

MAX_EXPANDED=10000
MAX_VERTICES=100000
MAX_DEPTH=16


def point(value):
    result=list(Vec3(value))
    if not all(math.isfinite(v) and abs(v)<=1e12 for v in result):raise ValueError('DXF coordinate exceeds finite geometry bounds')
    return result


def curve_length(u,v,start,sweep):
    """Adaptive Simpson integral of affine-circle speed; fail if not converged."""
    def speed(t):return (u*(-math.sin(t))+v*math.cos(t)).magnitude
    if not all(math.isfinite(x) for x in (*u,*v,start,sweep)):raise ValueError('Nonfinite curve')
    if not sweep:return 0.,0.
    def simpson(a,b,fa,fm,fb):return (b-a)*(fa+4*fm+fb)/6
    a,b=start,start+abs(sweep)
    tolerance=max(u.magnitude,v.magnitude)*abs(sweep)*1e-10
    def refine(a,b,fa,fm,fb,whole,tol,depth):
        mid=(a+b)/2;fl,fr=speed((a+mid)/2),speed((mid+b)/2)
        left,right=simpson(a,mid,fa,fl,fm),simpson(mid,b,fm,fr,fb);delta=left+right-whole
        if abs(delta)<=15*tol:return left+right+delta/15,abs(delta)/15
        if not depth:raise ValueError('Curve integration did not converge')
        x,ex=refine(a,mid,fa,fl,fm,left,tol/2,depth-1);y,ey=refine(mid,b,fm,fr,fb,right,tol/2,depth-1)
        return x+y,ex+ey
    # Split into <= pi/4 pieces: a full period must not alias all quadrature points.
    total=error=0.;parts=max(1,math.ceil(abs(sweep)/(math.pi/4)))
    for i in range(parts):
        x=a+(b-a)*i/parts;y=a+(b-a)*(i+1)/parts;m=(x+y)/2
        fx,fm,fy=speed(x),speed(m),speed(y)
        value,err=refine(x,y,fx,fm,fy,simpson(x,y,fx,fm,fy),tolerance/parts,16);total+=value;error+=err
    return total,error


def simple_polygon_area(coords):
    """Exact predicates on stored decimal coordinates; unknown if not a simple ring."""
    if len(coords)<3 or len(coords)>512:return None,'topology_not_checked'
    points=[(Fraction(str(x)),Fraction(str(y))) for x,y in coords]
    if len(set(points))!=len(points):return None,'repeated_vertices'
    def orient(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
    def intersect(a,b,c,d):
        if max(a[0],b[0])<min(c[0],d[0]) or max(c[0],d[0])<min(a[0],b[0]) or max(a[1],b[1])<min(c[1],d[1]) or max(c[1],d[1])<min(a[1],b[1]):return False
        return orient(a,b,c)*orient(a,b,d)<=0 and orient(c,d,a)*orient(c,d,b)<=0
    n=len(points)
    for i in range(n):
        a,b=points[i],points[(i+1)%n]
        # Adjacent collinear backtracking is not a simple boundary either.
        c=points[(i+2)%n]
        if orient(a,b,c)==0 and (b[0]-a[0])*(c[0]-b[0])+(b[1]-a[1])*(c[1]-b[1])<0:return None,'overlapping_edges'
        for j in range(i+2,n):
            if i==0 and j==n-1:continue
            if intersect(a,b,points[j],points[(j+1)%n]):return None,'self_intersection'
    area=abs(sum(points[i][0]*points[(i+1)%n][1]-points[(i+1)%n][0]*points[i][1] for i in range(n)))/2
    return (float(area),'simple_planar_boundary') if area else (None,'degenerate_boundary')


def inspect_geometry(doc,scale):
    rows=[];issues=[];vertices=0;visited=0;issue_count=0
    def spend(count=1):
        nonlocal vertices
        vertices+=count
        if vertices>MAX_VERTICES:raise ValueError('Expanded geometry vertex budget exceeded')
    def issue(path,reason):
        nonlocal issue_count
        issue_count+=1
        if len(issues)<1000:issues.append({'path':path,'reason':reason})
    def metric(value,power=1):
        if value is None or scale is None:return None
        result=value*scale**power
        if not math.isfinite(result):raise ValueError('Geometry measurement overflow')
        return result
    def visit(entity,matrix,path,stack,inherited_layer):
        nonlocal visited
        visited+=1
        if visited>MAX_EXPANDED:raise ValueError('Expanded entity budget exceeded')
        kind=entity.dxftype();layer=entity.dxf.layer
        if layer=='0' and inherited_layer is not None:layer=inherited_layer
        if kind=='INSERT':
            name=entity.dxf.name;block=entity.block()
            if name in stack:raise ValueError('Cyclic block reference')
            if len(stack)>=MAX_DEPTH:raise ValueError('Block nesting depth exceeded')
            if block is None:issue(path,'missing_block');return
            if block.block.dxf.flags & (4|8):issue(path,'external_reference_not_loaded');return
            nr,nc=entity.dxf.row_count,entity.dxf.column_count
            if nr<1 or nc<1 or nr*nc>MAX_EXPANDED:raise ValueError('Block array budget exceeded')
            for rr in range(nr):
                for cc in range(nc):
                    instance=entity.copy()
                    offset=Vec3(cc*entity.dxf.column_spacing,rr*entity.dxf.row_spacing,0).rotate_deg(entity.dxf.rotation)
                    instance.dxf.insert=entity.dxf.insert+offset
                    transform=instance.matrix44() @ matrix
                    if not all(math.isfinite(x) and abs(x)<=1e12 for x in transform):raise ValueError('Invalid block transform')
                    cell=path+[f'{name}[{rr},{cc}]']
                    for child in block:visit(child,transform,cell+[child.dxf.handle],stack+[name],layer)
                    # ATTRIB coordinates are in the containing drawing, not block-local.
                    for attr_index,attr in enumerate(instance.attribs):
                        attr.dxf.insert=attr.dxf.insert+offset
                        visit(attr,matrix,cell+['ATTRIB:'+str(attr_index)+':'+str(attr.dxf.tag)],stack,layer)
            return
        row={'path':path,'source_handle':entity.dxf.get('handle'),'type':kind,'layer':layer,'length_m':None,'area_m2':None,'geometry_status':'unsupported',
            'measurement_basis':'geometric_only_not_net_building_quantity'}
        def wcs(p):spend();return point(matrix.transform(p))
        def basis():
            ocs=entity.ocs();u=matrix.transform_direction(ocs.ux);v=matrix.transform_direction(ocs.uy)
            point(u);point(v)
            if u.cross(v).magnitude==0:raise ValueError('Degenerate planar geometry transform')
            return ocs,u,v
        if kind=='LINE':
            row.update(start=wcs(entity.dxf.start),end=wcs(entity.dxf.end),geometry_status='measured')
            row['length_m']=metric(matrix.transform_direction(entity.dxf.end-entity.dxf.start).magnitude);row['preview_points']=[row['start'],row['end']]
        elif kind in {'CIRCLE','ARC','ELLIPSE'}:
            if kind=='ELLIPSE':
                center=wcs(entity.dxf.center);major=Vec3(entity.dxf.major_axis);normal=Vec3(entity.dxf.extrusion).normalize()
                ratio=entity.dxf.ratio
                if not 0<ratio<=1:raise ValueError('Invalid ellipse ratio')
                minor=normal.cross(major).normalize(major.magnitude*ratio)
                u,v=matrix.transform_direction(major),matrix.transform_direction(minor)
                start,end=entity.dxf.start_param,entity.dxf.end_param
                sweep=(end-start)%(2*math.pi);closed=math.isclose(abs(end-start),2*math.pi,rel_tol=0,abs_tol=1e-12)
                row['closure_parameter_tolerance_rad']=1e-12
                if closed:sweep=2*math.pi
            else:
                ocs,u,v=basis();radius=entity.dxf.radius
                if not math.isfinite(radius) or radius<=0:raise ValueError('Invalid arc radius')
                center=wcs(ocs.to_wcs(entity.dxf.center));u=u*radius;v=v*radius
                start=0 if kind=='CIRCLE' else math.radians(entity.dxf.start_angle)
                sweep=2*math.pi if kind=='CIRCLE' else math.radians((entity.dxf.end_angle-entity.dxf.start_angle)%360);closed=kind=='CIRCLE'
            point(u);point(v)
            if u.cross(v).magnitude==0:raise ValueError('Degenerate curve transform')
            length,error=curve_length(u,v,start,sweep);spend(65)
            preview=[point(Vec3(center)+u*math.cos(start+sweep*i/64)+v*math.sin(start+sweep*i/64)) for i in range(65)]
            row.update(geometry_status='measured',length_m=metric(length),length_numerical_error_estimate_m=metric(error),area_m2=metric(math.pi*u.cross(v).magnitude,2) if closed else None,
                area_status='simple_ellipse' if closed else 'open_curve',preview_points=preview,preview_approximate=True,closed=closed)
        elif kind=='LWPOLYLINE' or kind=='POLYLINE' and entity.is_2d_polyline:
            ocs,u,v=basis();elevation=entity.dxf.elevation if kind=='LWPOLYLINE' else entity.dxf.elevation.z
            coords=list(entity.get_points('xyb')) if kind=='LWPOLYLINE' else [(p.dxf.location.x,p.dxf.location.y,p.dxf.bulge) for p in entity.vertices]
            spend(len(coords));closed=entity.closed if kind=='LWPOLYLINE' else entity.is_closed
            if len(coords)<2:raise ValueError('Polyline needs at least two vertices')
            if not all(math.isfinite(x) and abs(x)<=1e12 for p in coords for x in p):raise ValueError('Invalid polyline coordinate or bulge')
            points=[point(matrix.transform(ocs.to_wcs((x,y,elevation)))) for x,y,_ in coords];length=error=0.;curved=False
            count=len(coords) if closed else len(coords)-1
            for i in range(count):
                j=(i+1)%len(coords);a,b=coords[i],coords[j];bulge=a[2]
                if not bulge:
                    length+=matrix.transform_direction(ocs.to_wcs((b[0]-a[0],b[1]-a[1],0))).magnitude
                    continue
                curved=True
                # Tangent-quarter-angle bulge: source circular segment then affine transform.
                dx,dy=b[0]-a[0],b[1]-a[1];chord=math.hypot(dx,dy)
                if not chord:raise ValueError('Nonzero bulge on zero chord')
                cx=(a[0]+b[0])/2-dy*(1-bulge*bulge)/(4*bulge);cy=(a[1]+b[1])/2+dx*(1-bulge*bulge)/(4*bulge)
                radius=chord*(1+bulge*bulge)/(4*abs(bulge));start=math.atan2(a[1]-cy,a[0]-cx);sweep=4*math.atan(bulge)
                # Speed integral is evaluated forward from the smaller parameter.
                value,err=curve_length(u*radius,v*radius,start+min(0,sweep),abs(sweep));length+=value;error+=err
            area,area_status=(None,'open_curve')
            if closed:
                area,area_status=(None,'curved_boundary_topology_not_checked') if curved else simple_polygon_area([(x,y) for x,y,_ in coords])
            row.update(geometry_status='measured',length_m=metric(length),length_numerical_error_estimate_m=metric(error),area_m2=metric(area*u.cross(v).magnitude,2) if area is not None else None,
                area_status=area_status,closed=bool(closed),vertex_count=len(coords),has_bulge=curved,
                preview_points=[] if curved else points[:200]+([points[0]] if closed and len(points)<=200 else []),preview_truncated=len(points)>200,
                preview_note='曲线折线不以端点直线伪装；有弧段时不绘制此预览。' if curved else '原始折线顶点，最多200点。')
        elif kind=='POLYLINE' and entity.is_3d_polyline:
            local=[v.dxf.location for v in entity.vertices];pts=[wcs(p) for p in local];closed=entity.is_closed
            length=sum(matrix.transform_direction(b-a).magnitude for a,b in zip(local,local[1:]))+(matrix.transform_direction(local[0]-local[-1]).magnitude if closed and len(local)>1 else 0)
            row.update(geometry_status='measured',length_m=metric(length),area_status='3d_boundary_not_assessed',vertex_count=len(pts),closed=bool(closed),preview_points=pts[:200]+([pts[0]] if closed and 0<len(pts)<=200 else []),preview_truncated=len(pts)>200)
        elif kind in {'TEXT','MTEXT','ATTRIB'}:
            row.update(text=entity.text if kind=='MTEXT' else entity.dxf.text,geometry_status='text_only')
        if row['geometry_status']=='unsupported':issue(path,'unsupported_entity:'+kind)
        if row.get('area_status') in {'topology_not_checked','repeated_vertices','overlapping_edges','self_intersection','degenerate_boundary','curved_boundary_topology_not_checked'}:
            issue(path,'area_unavailable:'+row['area_status'])
        if scale is None and row['geometry_status']=='measured':row['geometry_status']='unit_unknown'
        rows.append(row)
    for entity in doc.modelspace():visit(entity,Matrix44(),[entity.dxf.handle],[],None)
    return {'objects':rows,'expanded_counts':dict(Counter(r['type'] for r in rows)),'visited_entities':visited,'vertex_budget_used':vertices,'issues':issues,'issue_count':issue_count,'issues_truncated':issue_count>len(issues),
        'coverage':'partial' if issues or any(r['geometry_status']=='unit_unknown' for r in rows) else 'supported_entities_extracted',
        'coordinate_frame':'WCS drawing units; lengths m and areas m2 only with declared INSUNITS',
        'limitations':['几何测量不是净工程量：不自动识别墙/柱、不去重叠、不扣洞，不把图层或块名当作建筑分类。',
            '嵌套块与阵列逐实例展开；保留原句柄和实例路径。外部参照不访问，未知实体明确列入缺口。',
            '曲线长度为自适应数值积分，误差字段为估计而非严格证明；曲线预览仅65点采样。',
            '闭合直线多边形最多512点核验自交；带弧多边形面积暂缺，禁止当零。多段线宽度不计入中心线长度/边界面积。',
            '长度从局部差向量变换，避免大平移相减丢失精度；显示坐标仍受双精度限制。预览是WCS XY投影，不是完整CAD渲染。',
            '完整椭圆按参数跨度与2π的绝对差≤1e-12弧度判断，容纳文件小数舍入；此容差内的微小开口不作独立拓扑证明。']}
