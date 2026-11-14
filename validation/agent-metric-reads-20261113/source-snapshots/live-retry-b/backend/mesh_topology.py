"""Bounded exact intersection predicates on the supplied binary-float mesh.

No snapping, repair, boolean union, or reinterpretation of a declaration as geometry.
An AABB hierarchy narrows candidates; rational predicates resolve contacts without
an epsilon that could erase a small opening or merge nearby shells.
"""
from dataclasses import dataclass
from fractions import Fraction

import numpy as np


class BudgetExceeded(ValueError):
    pass


@dataclass
class Budget:
    max_pairs: int = 120000
    max_nodes: int = 500000
    max_ray_tests: int = 120000
    pairs: int = 0
    nodes: int = 0
    ray_tests: int = 0

    def spend(self, name):
        value = getattr(self, name) + 1
        setattr(self, name, value)
        if value > getattr(self, 'max_' + name):
            raise BudgetExceeded('topology_' + name + '_budget')


def sub(a, b):return tuple(x-y for x,y in zip(a,b))
def dot(a, b):return sum(x*y for x,y in zip(a,b))
def cross(a, b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def normal(t):return cross(sub(t[1],t[0]),sub(t[2],t[0]))
def mix(a, b, t):return tuple(x+t*(y-x) for x,y in zip(a,b))
def orient2(a,b,c):return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])


def clip_polygon(subject, triangle):
    sign = 1 if orient2(*triangle)>0 else -1
    for a,b in zip(triangle,triangle[1:]+triangle[:1]):
        output=[]
        if not subject:break
        for p,q in zip(subject,subject[1:]+subject[:1]):
            dp,dq=sign*orient2(a,b,p),sign*orient2(a,b,q)
            if dp>=0:output.append(p)
            if (dp<0<dq) or (dq<0<dp):output.append(mix(p,q,dp/(dp-dq)))
        subject=output
    return subject


def plane_cut(triangle, distances):
    points=[p for p,d in zip(triangle,distances) if d==0]
    for i,j in [(0,1),(1,2),(2,0)]:
        if distances[i]*distances[j]<0:
            points.append(mix(triangle[i],triangle[j],distances[i]/(distances[i]-distances[j])))
    return points


def pair_allowed(a, b, common):
    """Intersection must be empty or precisely within shared indexed simplex."""
    if len(common)==2:
        # Two nondegenerate triangles sharing an edge can only overlap beyond
        # that edge when coplanar and on the same side. Exact local predicate
        # avoids clipping the many valid adjacent triangles in a tessellation.
        p,q=common;edge=sub(q,p)
        u=next(v for v in a if v not in common);v=next(v for v in b if v not in common)
        nu,nv=cross(edge,sub(u,p)),cross(edge,sub(v,p))
        return bool(any(cross(nu,nv))) or dot(nu,nv)<0
    na,nb=normal(a),normal(b)
    da=[dot(nb,sub(p,b[0])) for p in a]
    db=[dot(na,sub(p,a[0])) for p in b]
    if any(all(d>0 for d in side) or all(d<0 for d in side) for side in [da,db]):return True
    if all(d==0 for d in da) and all(d==0 for d in db):
        drop=max(range(3),key=lambda k:abs(na[k]));axes=[k for k in range(3) if k!=drop]
        project=lambda p:tuple(p[k] for k in axes)
        polygon=clip_polygon([project(p) for p in a],[project(p) for p in b])
        shared=[project(p) for p in common]
        if not polygon:return True
        if len(shared)==1:return all(p==shared[0] for p in polygon)
        if len(shared)==2:
            p,q=shared
            return all(orient2(p,q,r)==0 and all(min(p[k],q[k])<=r[k]<=max(p[k],q[k]) for k in range(2)) for r in polygon)
        return False
    direction=cross(na,nb)
    if not any(direction):return True  # Distinct parallel planes were separated above.
    axis=max(range(3),key=lambda k:abs(direction[k]))
    ca,cb=plane_cut(a,da),plane_cut(b,db)
    if not ca or not cb:return True
    lo=max(min(p[axis] for p in ca),min(p[axis] for p in cb))
    hi=min(max(p[axis] for p in ca),max(p[axis] for p in cb))
    if lo>hi:return True
    if not common:return False
    return min(p[axis] for p in common)<=lo<=hi<=max(p[axis] for p in common)


def candidate_pairs(points, budget):
    lows,highs=points.min(axis=1),points.max(axis=1)
    centers=lows+(highs-lows)/2
    def build(ids):
        lo,hi=lows[ids].min(axis=0),highs[ids].max(axis=0)
        if len(ids)<=8:return (lo,hi,ids,None,None)
        axis=int(np.argmax(hi-lo));order=ids[np.argsort(centers[ids,axis],kind='stable')];mid=len(order)//2
        return (lo,hi,None,build(order[:mid]),build(order[mid:]))
    root=build(np.arange(len(points)));stack=[(root,root)]
    while stack:
        a,b=stack.pop();budget.spend('nodes')
        if np.any(a[1]<b[0]) or np.any(b[1]<a[0]):continue
        if a is b and a[2] is None:
            stack.extend([(a[3],a[3]),(a[3],a[4]),(a[4],a[4])]);continue
        if a[2] is not None and b[2] is not None:
            for i in a[2]:
                for j in b[2]:
                    if a is b and i>=j:continue
                    if np.any(highs[i]<lows[j]) or np.any(highs[j]<lows[i]):continue
                    budget.spend('pairs');yield int(i),int(j)
        elif b[2] is not None or (a[2] is None and np.max(a[1]-a[0])>=np.max(b[1]-b[0])):
            stack.extend([(a[3],b),(a[4],b)])
        else:stack.extend([(a,b[3]),(a,b[4])])


def inside(point, triangles, budget):
    """Exact parity ray, retrying edge/vertex hits rather than double counting."""
    for k in range(1,9):
        direction=(Fraction(1),Fraction(k),Fraction(k*k+1));count=0;ambiguous=False
        for t in triangles:
            budget.spend('ray_tests')
            edge1,edge2=sub(t[1],t[0]),sub(t[2],t[0]);h=cross(direction,edge2);det=dot(edge1,h)
            if det==0:
                if dot(normal(t),sub(point,t[0]))==0:ambiguous=True;break
                continue
            s=sub(point,t[0]);u=dot(s,h)/det
            q=cross(s,edge1);v=dot(direction,q)/det;distance=dot(edge2,q)/det
            if distance<0 or u<0 or v<0 or u+v>1:continue
            if distance==0 or u==0 or v==0 or u+v==1:ambiguous=True;break
            count+=1
        if not ambiguous:return bool(count%2)
    raise BudgetExceeded('ambiguous_shell_containment_rays')


def vertex_manifold(tris, edges):
    incident={};links={}
    for i,t in enumerate(tris):
        for v in t:incident.setdefault(int(v),set()).add(i)
    for (a,b),pair in edges.items():
        i,j=pair[0][0],pair[1][0]
        for v in (a,b):
            links.setdefault((v,i),[]).append(j);links.setdefault((v,j),[]).append(i)
    for v,faces in incident.items():
        unseen=set(faces);todo=[unseen.pop()]
        while todo:
            for neighbor in links[(v,todo.pop())]:
                if neighbor in unseen:unseen.remove(neighbor);todo.append(neighbor)
        if unseen:return int(v)
    return None


def validate(vertices, tris, components, signed_volumes, edges, budget=None):
    budget=budget or Budget();before={k:getattr(budget,k) for k in ['pairs','nodes','ray_tests']}
    result={'status':'not_checked','reason':None,'shells':[],
            'method':'exact_binary_float_triangle_contacts_and_parity_containment',
            'scope':'within_one_product_mesh; no repair or cross-product union'}
    def finish(status,reason=None,**details):
        result.update(status=status,reason=reason,**details)
        result['work']={k:getattr(budget,k)-before[k] for k in before}
        return result
    try:
        bad_vertex=vertex_manifold(tris,edges)
        if bad_vertex is not None:return finish('rejected','non_manifold_vertex',vertex_index=bad_vertex)
        if len(components)>128:raise BudgetExceeded('shell_count_budget')
        cache={}
        def vertex(i):
            i=int(i)
            if i not in cache:cache[i]=tuple(Fraction(float(x)) for x in vertices[i])
            return cache[i]
        def triangle(i):return [vertex(v) for v in tris[i]]
        for i,j in candidate_pairs(vertices[tris],budget):
            common=set(tris[i]) & set(tris[j])
            if not pair_allowed(triangle(i),triangle(j),[vertex(v) for v in common]):
                return finish('rejected','triangle_intersection_or_nonlocal_contact',triangle_indices=[i,j])
        bounds=[];representatives=[];containers=[[] for _ in components]
        for faces in components:
            points=vertices[tris[faces]].reshape((-1,3));bounds.append((points.min(axis=0),points.max(axis=0)))
            representatives.append(vertices[tris[faces[0],0]])
        for i,point in enumerate(representatives):
            for j,faces in enumerate(components):
                if i==j or np.any(point<bounds[j][0]) or np.any(point>bounds[j][1]):continue
                if inside(vertex(tris[components[i][0],0]),[triangle(f) for f in faces],budget):containers[i].append(j)
        roots=[i for i,parents in enumerate(containers) if not parents]
        if not roots or any(not v for v in signed_volumes):return finish('rejected','zero_or_inconsistent_shell_volume')
        orientation=1 if signed_volumes[roots[0]]>0 else -1
        for i,volume in enumerate(signed_volumes):
            depth=len(containers[i]);expected=orientation*(-1 if depth%2 else 1)
            result['shells'].append({'shell':i,'faces':len(components[i]),'depth':depth,'containers':containers[i],
                                    'signed_volume_m3':volume,'orientation_consistent':volume*expected>0})
        if not all(s['orientation_consistent'] for s in result['shells']):return finish('rejected','incompatible_shell_orientation')
        return finish('checked')
    except BudgetExceeded as exc:return finish('not_verified',str(exc))
