import io
import math

import ezdxf
import numpy as np
import pytest
from ezdxf.math import Vec3
from backend.dxf_geometry import inspect_geometry,curve_length,simple_polygon_area
from test_api import create_project
from test_cad import upload


def complex_doc():
    doc=ezdxf.new('R2010');doc.units=4
    block=doc.blocks.new('IndependentRoom',base_point=(100,200,0))
    block.add_line((100,200,0),(3100,4200,0))
    block.add_lwpolyline([(100,200),(2100,200),(2100,3200),(100,3200)],close=True)
    block.add_circle((1100,1700),500)
    group=doc.blocks.new('IndependentGroup')
    group.add_blockref('IndependentRoom',(1000,2000),dxfattribs={'xscale':2,'yscale':3,'rotation':90})
    doc.modelspace().add_blockref('IndependentGroup',(10000,20000),dxfattribs={'rotation':90,'xscale':-1,'yscale':1,'row_count':2,'row_spacing':10000})
    return doc


def complex_dxf_bytes():
    stream=io.StringIO();complex_doc().write(stream);return stream.getvalue().encode()


def gauss_ellipse(a,b,start=0,sweep=2*math.pi):
    # Independent fixed-order quadrature, not application's adaptive Simpson code.
    x,w=np.polynomial.legendre.leggauss(128)
    t=(x+1)*sweep/2+start
    return float(np.dot(w,np.sqrt((a*np.sin(t))**2+(b*np.cos(t))**2))*sweep/2)


def test_nested_basepoint_mirror_rotation_nonuniform_array_independent_answer():
    g=inspect_geometry(complex_doc(),.001)
    assert g['expanded_counts']=={'LINE':2,'LWPOLYLINE':2,'CIRCLE':2}
    lines=[r for r in g['objects'] if r['type']=='LINE'];polys=[r for r in g['objects'] if r['type']=='LWPOLYLINE'];circles=[r for r in g['objects'] if r['type']=='CIRCLE']
    # Local delta(3000,4000) -> (6000,12000) -> (-12000,6000),
    # inner origin(1000,2000); outer mirror X then rotate90 then translate.
    assert lines[0]['start']==pytest.approx([8000,19000,0])
    assert lines[0]['end']==pytest.approx([2000,31000,0])
    assert lines[0]['length_m']==pytest.approx(math.sqrt(180))
    assert lines[1]['start']==pytest.approx([-2000,19000,0])
    assert lines[0]['path']!=lines[1]['path'] and lines[0]['source_handle']==lines[1]['source_handle']
    assert all(r['area_m2']==pytest.approx(36) and r['length_m']==pytest.approx(26) for r in polys)
    assert all(r['area_m2']==pytest.approx(1.5*math.pi) and r['length_m']==pytest.approx(gauss_ellipse(1,1.5),rel=1e-9) for r in circles)


@pytest.mark.parametrize('axes',[(1,1),(1,2),(.01,100),(10,.1)])
def test_curve_length_independent_quadrature(axes):
    a,b=axes;value,error=curve_length(Vec3(a,0,0),Vec3(0,b,0),0,2*math.pi)
    # Extremely eccentric cases use dense composite trapezoid independently.
    t=np.linspace(0,2*math.pi,100001);answer=float(np.trapezoid(np.hypot(a*np.sin(t),b*np.cos(t)),t))
    assert value==pytest.approx(answer,rel=2e-8)
    assert 0<=error<max(a,b)*1e-8


def test_bulges_open_and_closed_are_not_straight_chords():
    d=ezdxf.new();m=d.modelspace()
    m.add_lwpolyline([(0,0,1),(2,0,0)],format='xyb')
    m.add_lwpolyline([(0,0,-1),(2,0,0)],format='xyb',close=True)
    g=inspect_geometry(d,1)
    assert g['objects'][0]['length_m']==pytest.approx(math.pi)
    assert g['objects'][1]['length_m']==pytest.approx(math.pi+2)
    assert g['objects'][1]['area_m2'] is None
    assert g['objects'][1]['area_status']=='curved_boundary_topology_not_checked'
    assert g['objects'][0]['preview_points']==[]


def test_nonuniform_scaled_bulge_and_ocs_elevation():
    d=ezdxf.new();b=d.blocks.new('curve');b.add_lwpolyline([(0,0,1),(2,0,0)],format='xyb',dxfattribs={'elevation':4,'extrusion':(0,1,0)})
    d.modelspace().add_blockref('curve',(10,20,30),dxfattribs={'xscale':2,'yscale':3,'zscale':4})
    r=inspect_geometry(d,1)['objects'][0]
    assert r['length_m']==pytest.approx(gauss_ellipse(2,4,0,math.pi),rel=1e-9)
    assert r['area_m2'] is None


@pytest.mark.parametrize('pts,area,status',[
    ([(0,0),(4,0),(4,3),(0,3)],12,'simple_planar_boundary'),
    ([(0,0),(0,3),(4,3),(4,0)],12,'simple_planar_boundary'),
    ([(0,0),(4,3),(4,0),(0,3)],None,'self_intersection'),
    ([(0,0),(4,0),(2,0),(2,2),(0,2)],None,'overlapping_edges'),
    ([(0,0),(4,0),(4,3),(0,0)],None,'repeated_vertices')])
def test_exact_simple_polygon_predicates(pts,area,status):
    assert simple_polygon_area(pts)==(area,status)


def test_open_unknown_units_unsupported_and_width_are_explicit():
    d=ezdxf.new();d.modelspace().add_lwpolyline([(0,0),(3,0),(3,4)],dxfattribs={'const_width':2})
    d.modelspace().add_point((1,1,1))
    g=inspect_geometry(d,None)
    assert g['coverage']=='partial' and g['objects'][0]['length_m'] is None and g['objects'][0]['area_m2'] is None
    assert g['objects'][0]['geometry_status']=='unit_unknown' and g['issue_count']==1
    g=inspect_geometry(d,1);assert g['objects'][0]['length_m']==7 and g['objects'][0]['area_status']=='open_curve'


def test_arc_ellipse_and_3d_polyline():
    d=ezdxf.new();m=d.modelspace();m.add_arc((0,0),2,300,60);m.add_ellipse((0,0),major_axis=(4,0,0),ratio=.5)
    m.add_polyline3d([(0,0,0),(3,4,0),(3,4,12)])
    rows=inspect_geometry(d,1)['objects']
    assert rows[0]['length_m']==pytest.approx(4*math.pi/3) and rows[0]['area_m2'] is None
    assert rows[1]['length_m']==pytest.approx(gauss_ellipse(4,2),rel=1e-9) and rows[1]['area_m2']==pytest.approx(8*math.pi)
    assert rows[2]['length_m']==17 and rows[2]['area_m2'] is None


def test_almost_closed_ellipse_does_not_gain_enclosed_area():
    d=ezdxf.new();d.modelspace().add_ellipse((0,0),major_axis=(4,0,0),ratio=.5,end_param=2*math.pi-1e-9)
    r=inspect_geometry(d,1)['objects'][0]
    assert r['area_m2'] is None and not r['closed']


def test_decimal_rounded_full_ellipse_does_not_modulo_to_zero():
    d=ezdxf.new();d.modelspace().add_ellipse((0,0),major_axis=(4,0,0),ratio=.5,end_param=6.28318530718)
    r=inspect_geometry(d,1)['objects'][0]
    assert r['length_m']==pytest.approx(gauss_ellipse(4,2),rel=1e-9)
    assert r['closed'] and r['area_m2']==pytest.approx(8*math.pi)
    assert r['closure_parameter_tolerance_rad']==1e-12


def test_cycles_external_references_and_capacity_do_not_silently_succeed():
    d=ezdxf.new();b=d.blocks.new('cycle');b.add_blockref('cycle',(0,0));d.modelspace().add_blockref('cycle',(0,0))
    with pytest.raises(ValueError,match='Cyclic'):inspect_geometry(d,1)
    d=ezdxf.new();b=d.blocks.new('external');b.block.dxf.flags=4;b.block.dxf.xref_path='https://example.invalid/do-not-load.dxf';d.modelspace().add_blockref('external',(0,0))
    g=inspect_geometry(d,1);assert not g['objects'] and g['issues'][0]['reason']=='external_reference_not_loaded'
    d=complex_doc();e=list(d.modelspace())[0];e.dxf.row_count=10001
    with pytest.raises(ValueError,match='budget'):inspect_geometry(d,1)


def test_distinct_zero_spacing_instances_preserved_and_layer_inheritance():
    d=ezdxf.new();d.layers.new('Host');b=d.blocks.new('B');b.add_line((0,0),(1,0));d.modelspace().add_blockref('B',(0,0),dxfattribs={'layer':'Host','row_count':2,'row_spacing':0})
    g=inspect_geometry(d,1);assert len(g['objects'])==2 and all(r['layer']=='Host' for r in g['objects'])
    assert g['objects'][0]['path']!=g['objects'][1]['path']


def test_length_is_translation_invariant_at_large_coordinates():
    d=ezdxf.new();b=d.blocks.new('tiny');b.add_line((0,0),(.001,0));b.add_lwpolyline([(0,0),(.001,0),(.001,.002)])
    d.modelspace().add_blockref('tiny',(1e11,1e11))
    rows=inspect_geometry(d,1)['objects']
    assert rows[0]['length_m']==pytest.approx(.001,rel=1e-12)
    assert rows[1]['length_m']==pytest.approx(.003,rel=1e-12)


def test_api_actual_subprocess_preserves_original_and_geometry_version(client,monkeypatch):
    from backend import cad
    pid=create_project(client)['project_id'];fid=upload(client,pid,'nested-reference.dxf',complex_dxf_bytes());base=f'/api/projects/{pid}/cad-inspections'
    response=client.post(base,json={'file_id':fid});assert response.status_code==201,response.text
    r=response.json();assert r['result']['counts']=={'INSERT':1} and r['result']['geometry']['expanded_counts']['CIRCLE']==2
    assert client.app.state.domain.file_record(pid,fid)[1].read_bytes().startswith(b'  0')
    old=cad.core.sha
    monkeypatch.setattr(cad.core,'sha',lambda p:'changed' if p.name=='dxf_geometry.py' else old(p))
    assert client.get(base+'/'+r['cad_id']).json()['result'] is None
