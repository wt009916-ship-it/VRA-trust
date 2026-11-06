"""Actual IFC4 tessellated files through the isolated parser and authenticated API."""
import hashlib

import pytest

from backend import cad, core
from test_api import create_project
from test_cad import upload
from test_ifc_measurements import make_box
from test_mesh_topology import box, combine, reversed_mesh


def tessellated_document(mesh):
    doc, _, wall = make_box()
    vertices, faces = mesh
    points = doc.create_entity('IfcCartesianPointList3D', CoordList=vertices.tolist())
    item = doc.create_entity('IfcTriangulatedFaceSet', Coordinates=points, Closed=True,
                             CoordIndex=(faces+1).tolist())
    body = wall.Representation.Representations[0]
    body.RepresentationType = 'Tessellation'
    body.Items = [item]
    wall.Name = 'Synthetic topology witness; not an actual building'
    return doc


@pytest.mark.parametrize('case,expected', [('disjoint',2),('overlap',None),('cavity',26),('nested_wrong',None)])
def test_actual_tessellated_ifc_preserves_original_and_gates_volume(client, case, expected):
    meshes = {
        'disjoint': combine(box(), box((2,0,0),(3,1,1))),
        'overlap': combine(box(), box((.5,.25,.25),(1.5,1.25,1.25))),
        'cavity': combine(box((0,0,0),(3,3,3)), reversed_mesh(box((1,1,1),(2,2,2)))),
        'nested_wrong': combine(box((0,0,0),(3,3,3)), box((1,1,1),(2,2,2))),
    }
    content = tessellated_document(meshes[case]).to_string().encode()
    pid = create_project(client)['project_id']
    fid = upload(client, pid, case+'.ifc', content)
    base = f'/api/projects/{pid}/cad-inspections'
    response = client.post(base, json={'file_id':fid})
    assert response.status_code == 201, response.text
    record = response.json()
    row = record['result']['ifc_geometry']['objects'][0]
    assert record['source']['hash'] == hashlib.sha256(content).hexdigest()
    _, original = client.app.state.domain.file_record(pid, fid)
    assert original.read_bytes() == content
    assert row['triangles'] == 24 and row['bad_edges'] == 0
    if expected is None:
        assert row['volume_m3'] is None and row['status'] == 'partial_mesh'
        reason = 'triangle_intersection_or_nonlocal_contact' if case=='overlap' else 'incompatible_shell_orientation'
        assert row['topology']['reason'] == reason
    else:
        assert row['volume_m3'] == pytest.approx(expected)
        assert row['topology']['status'] == 'checked'
    assert client.get(base+'/'+record['cad_id']).json()['result'] == record['result']


def test_topology_helper_is_bound_to_parser_version(monkeypatch):
    before = cad.parser_version()
    original = core.sha
    monkeypatch.setattr(core, 'sha', lambda path: 'changed-topology-helper' if path.name=='mesh_topology.py' else original(path))
    assert cad.parser_version() != before
