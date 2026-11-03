"""Legacy-engine fatal geometry discovered in an unseen Revit building."""
from types import SimpleNamespace

from honeybee.face import Face
from honeybee.aperture import Aperture
from ladybug_geometry.geometry3d import Face3D, Point3D

from backend.honeybee_bridge import engine_preflight


def shape(points):
    return Face3D(tuple(Point3D(*p) for p in points))


def test_triangle_that_honeybee_keeps_is_rejected_before_legacy_engine():
    # Honeybee retains this real-area triangle. EnergyPlus 9.0.1 cannot drop its
    # 5 mm edge without degenerating to fewer than three vertices.
    face = Face('short_triangle', shape([(0, 0, 0), (.005, 0, 0), (0, 1, 0)]))
    hb = SimpleNamespace(faces=[face])
    before = tuple(face.geometry.vertices)
    result = engine_preflight(hb)
    assert not result['passed']
    assert result['issues'][0]['code'] == 'TRIANGLE_EDGE_BELOW_ENGINE_MINIMUM'
    assert tuple(face.geometry.vertices) == before


def test_generated_window_is_checked_at_actual_serialized_precision():
    face = Face('wall', shape([(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)]))
    window = Aperture('tiny_window', shape([(.1, 0, .1), (.1000004, 0, .1), (.1, 0, .5)]))
    face.add_aperture(window)
    result = engine_preflight(SimpleNamespace(faces=[face]))
    assert not result['passed'] and result['checked_faces_and_windows'] == 2
    issue = result['issues'][0]
    assert issue['face'] == 'tiny_window' and issue['parent_face'] == 'wall'
    assert issue['code'] == 'AREA_BELOW_ENGINE_MINIMUM'


def test_valid_triangle_and_nonfatal_short_quad_are_not_blanket_rejected():
    triangle = Face('valid_triangle', shape([(0, 0, 0), (.01, 0, 0), (0, 1, 0)]))
    quad = Face('short_quad', shape([(0, 0, 0), (.005, 0, 0), (1, 1, 0), (0, 1, 0)]))
    assert engine_preflight(SimpleNamespace(faces=[triangle, quad]))['passed']


def test_flat_quad_below_native_projection_area_threshold_is_rejected():
    # v9 CheckConvexity calls this non-planar although all Z coordinates are 0.
    face=Face('tiny_flat_quad',shape([(0,0,0),(.005,0,0),(.005,.005,0),(0,.005,0)]))
    result=engine_preflight(SimpleNamespace(faces=[face]))
    assert not result['passed']
    assert result['issues'][0]['code']=='PROJECTED_AREA_BELOW_ENGINE_MINIMUM'
