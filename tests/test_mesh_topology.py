"""Independent analytic solids and adversarial embeddings, not declaration oracles."""
from fractions import Fraction

import numpy as np
import pytest

from backend.ifc_geometry import mesh_measurements
from backend.mesh_topology import Budget, candidate_pairs, pair_allowed


def box(lo=(0,0,0), hi=(1,1,1)):
    x,y,z=lo;X,Y,Z=hi
    return np.array([[x,y,z],[X,y,z],[X,Y,z],[x,Y,z],[x,y,Z],[X,y,Z],[X,Y,Z],[x,Y,Z]],float),np.array([
        [0,2,1],[0,3,2],[4,5,6],[4,6,7],[0,1,5],[0,5,4],[1,2,6],[1,6,5],[2,3,7],[2,7,6],[3,0,4],[3,4,7]])


def combine(*meshes):
    vertices=[];faces=[];offset=0
    for v,f in meshes:vertices.extend(v);faces.extend(f+offset);offset+=len(v)
    return np.array(vertices),np.array(faces)


def reversed_mesh(mesh):return mesh[0],mesh[1][:,::-1]


def test_disjoint_solids_are_added_without_cancellation():
    v,f=combine(box(),box((2,0,0),(4,3,5)))
    for faces in [f,f[:,::-1]]:
        row=mesh_measurements(v,faces)
        assert row['volume_m3']==pytest.approx(1+2*3*5)
        assert row['surface_area_m2']==pytest.approx(6+2*(6+10+15))
        assert row['topology']['status']=='checked'
        assert [s['depth'] for s in row['topology']['shells']]==[0,0]
    v,f=combine(box(),reversed_mesh(box((2,0,0),(3,1,1))))
    row=mesh_measurements(v,f)
    assert row['volume_m3'] is None and row['topology']['reason']=='incompatible_shell_orientation'


@pytest.mark.parametrize('position',[(.5,0,0),(.25,.25,.25),(-.5,-.5,-.5),(1,0,0),(1,1,0),(1,1,1)])
def test_overlap_face_edge_and_point_contacts_are_not_physical_union(position):
    v,f=combine(box(),box(position,tuple(x+1 for x in position)))
    row=mesh_measurements(v,f)
    assert row['volume_m3'] is None
    assert row['surface_area_kind']=='sum_of_input_triangles_not_union_area'


def test_inverted_internal_shell_and_nested_solid_island():
    outer=box((0,0,0),(4,4,4));inner=box((1,1,1),(3,3,3));island=box((1.5,1.5,1.5),(2.5,2.5,2.5))
    row=mesh_measurements(*combine(outer,inner))
    assert row['volume_m3'] is None and row['topology']['reason']=='incompatible_shell_orientation'
    for mesh in [combine(outer,reversed_mesh(inner)),combine(outer,reversed_mesh(inner),island)]:
        row=mesh_measurements(*mesh)
        expected=64-8+(1 if len(mesh[0])==24 else 0)
        assert row['volume_m3']==pytest.approx(expected)
        assert sorted(s['depth'] for s in row['topology']['shells'])==list(range(len(mesh[0])//8))


def test_single_connected_self_intersection_rejected():
    v,f=box();v[6]=[.25,.25,-.5]
    row=mesh_measurements(v,f)
    assert row['bad_edges']==0 and row['connected_shells']==1
    assert row['volume_m3'] is None and row['topology']['reason']=='triangle_intersection_or_nonlocal_contact'


@pytest.mark.parametrize('scale,shift',[(1.,0.),(1e-6,0.),(1e6,0.),(1.,1e9)])
def test_translation_scale_do_not_hide_crossing(scale,shift):
    v,f=combine(box(),box((.5,.25,.25),(1.5,1.25,1.25)))
    assert mesh_measurements(v*scale+shift,f)['volume_m3'] is None
    v,f=box();row=mesh_measurements(v*scale+shift,f)
    assert row['volume_m3']==pytest.approx(scale**3,rel=1e-12)


def test_small_real_gap_is_not_welded_by_a_tolerance():
    gap=2**-40
    row=mesh_measurements(*combine(box(),box((1+gap,0,0),(2+gap,1,1))))
    assert row['volume_m3']==pytest.approx(2) and row['topology']['status']=='checked'


def test_slanted_prism_volume_and_surface_area_independent():
    # Shear determinant is one; top/bottom area 1, two side pairs sqrt(5)/2 and 1.
    v,f=box();v[:,0]+=v[:,2]*.5
    row=mesh_measurements(v,f)
    assert row['volume_m3']==pytest.approx(1)
    assert row['surface_area_m2']==pytest.approx(4+5**.5)


@pytest.mark.parametrize('limit', ['pairs','nodes','ray_tests'])
def test_work_budget_fails_closed_and_never_assigns_zero(limit):
    budget=Budget(**{'max_'+limit:0})
    outer,inner=box((0,0,0),(3,3,3)),reversed_mesh(box((1,1,1),(2,2,2)))
    row=mesh_measurements(*combine(outer,inner),topology_budget=budget)
    assert row['volume_m3'] is None and row['topology']['status']=='not_verified'
    assert 'budget' in row['topology']['reason']


def test_file_budget_is_shared_without_reusing_success_status():
    budget=Budget(max_pairs=100)
    rows=[mesh_measurements(*box(),topology_budget=budget) for _ in range(4)]
    assert rows[0]['volume_m3']==1
    assert rows[-1]['volume_m3'] is None and rows[-1]['topology']['status']=='not_verified'


def rational_triangle(points):return [tuple(Fraction(x) for x in p) for p in points]


@pytest.mark.parametrize('a,b,common,expected',[
    ([(0,0,0),(2,0,0),(0,2,0)],[(0,0,0),(2,0,0),(0,-2,0)],[(0,0,0),(2,0,0)],True),
    ([(0,0,0),(2,0,0),(0,2,0)],[(0,0,0),(2,0,0),(1,1,0)],[(0,0,0),(2,0,0)],False),
    ([(0,0,0),(2,0,0),(0,2,0)],[(0,0,0),(-2,0,1),(0,-2,1)],[(0,0,0)],True),
    ([(0,0,0),(2,0,0),(0,2,0)],[(0,0,0),(1,1,1),(1,1,-1)],[(0,0,0)],False),
    ([(0,0,0),(2,0,0),(0,2,0)],[(1,0,-1),(1,0,1),(1,2,0)],[],False),
    ([(0,0,0),(2,0,0),(0,2,0)],[(3,0,0),(5,0,0),(3,2,0)],[],True),
])
def test_exact_contact_predicates(a,b,common,expected):
    assert pair_allowed(rational_triangle(a),rational_triangle(b),rational_triangle(common)) is expected
    assert pair_allowed(rational_triangle(b),rational_triangle(a),rational_triangle(common)) is expected


def test_bvh_covers_bruteforce_aabb_candidates_exactly_once():
    # Seeded coordinates are only broad-phase fixtures; oracle is a separate exhaustive box comparison.
    points=np.random.default_rng(1731).integers(-5,6,size=(43,3,3)).astype(float)
    actual=[tuple(sorted(pair)) for pair in candidate_pairs(points,Budget())]
    expected={(i,j) for i in range(len(points)) for j in range(i+1,len(points))
              if all(max(points[i,:,k].min(),points[j,:,k].min())<=min(points[i,:,k].max(),points[j,:,k].max()) for k in range(3))}
    assert len(actual)==len(set(actual)) and set(actual)==expected


def test_concave_l_prism_is_not_rejected_as_a_convexity_requirement():
    # Footprint: 2x2 square minus the upper-right unit square, height one.
    base=np.array([[0,0,0],[2,0,0],[2,1,0],[1,1,0],[1,2,0],[0,2,0]],float)
    top=base+[0,0,1];cap=np.array([[0,1,3],[1,2,3],[0,3,5],[3,4,5]])
    sides=[]
    for i in range(6):
        j=(i+1)%6;sides.extend([[i,j,j+6],[i,j+6,i+6]])
    row=mesh_measurements(np.vstack([base,top]),np.vstack([cap[:,::-1],cap+6,sides]))
    assert row['topology']['status']=='checked'
    assert row['volume_m3']==pytest.approx(3)
    assert row['surface_area_m2']==pytest.approx(2*3+8)


def test_genus_one_mesh_and_solid_in_its_hole_have_two_external_shells():
    # Polygonal torus: Pappus volume using regular m-gon cross-section and
    # n-gon sweep, independent of the tetrahedral integration implementation.
    n,m,R,r=16,8,3.,1.
    vertices=[];faces=[]
    for i in range(n):
        u=2*np.pi*i/n
        for j in range(m):
            v=2*np.pi*j/m
            vertices.append([(R+r*np.cos(v))*np.cos(u),(R+r*np.cos(v))*np.sin(u),r*np.sin(v)])
    for i in range(n):
        for j in range(m):
            a=i*m+j;b=((i+1)%n)*m+j;c=((i+1)%n)*m+(j+1)%m;d=i*m+(j+1)%m
            faces.extend([[a,b,c],[a,c,d]])
    mesh=combine((np.array(vertices),np.array(faces)),box((-.25,-.25,-.25),(.25,.25,.25)))
    row=mesh_measurements(*mesh)
    assert row['topology']['status']=='checked'
    assert [s['depth'] for s in row['topology']['shells']]==[0,0]
    expected=n*R*np.sin(2*np.pi/n)*(m*r*r*np.sin(2*np.pi/m)/2)+.5**3
    assert row['volume_m3']==pytest.approx(expected,rel=1e-12)
