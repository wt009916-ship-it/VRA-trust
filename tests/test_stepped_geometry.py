import copy

import ifcopenshell
import ifcopenshell.geom
import numpy as np
import pytest
from pydantic import ValidationError

from backend import core, model_export, model_import
from backend.model_geometry import floor_area, frame, mesh_segments, thermal_geometry_model
from backend.model_schema import ImportOptions, ModelDraft
from test_model_workbench import model_body, project


def stepped():
    body = model_body()
    body["rooms"] = [
        {"id": "Stair", "name": "Stepped space", "polygon": [[0, 0], [4, 0], [4, 4], [0, 4]],
         "height_m": 6, "segments": [
             {"polygon": [[0, 0], [4, 0], [4, 4], [0, 4]], "elevation_m": 0, "height_m": 3},
             {"polygon": [[0, 0], [3, 0], [3, 4], [0, 4]], "elevation_m": 3, "height_m": 3}]},
        {"id": "Upper", "name": "Upper bedroom", "polygon": [[3, 0], [4, 0], [4, 4], [3, 4]],
         "elevation_m": 3, "height_m": 3},
    ]
    return body


def test_steps_preserve_volume_and_roundtrip_ifc(tmp_path):
    model = ModelDraft.model_validate(stepped()).model_dump()
    original = copy.deepcopy(model)
    path = tmp_path/"stepped.ifc"
    path.write_text(model_export.ifc(model), encoding="utf-8")
    candidate = model_import.ifc(path, ImportOptions(file_id="test"))
    assert len(candidate["rooms"]) == 2
    stair = next(r for r in candidate["rooms"] if r["name"] == "Stepped space")
    assert len(stair["segments"]) == 2
    assert floor_area(stair) == pytest.approx(16)
    from shapely.geometry import Polygon
    assert sum(Polygon(s["polygon"]).area*s["height_m"] for s in stair["segments"]) == pytest.approx(84)
    assert model == original
    bad = stepped()
    bad["rooms"][0]["segments"] = []
    with pytest.raises(ValidationError, match="体积重叠"):
        ModelDraft.model_validate(bad)


def test_compiled_closed_zone_volume_from_oriented_faces():
    model = ModelDraft.model_validate(stepped()).model_dump()
    volumes = {}
    for face in model_export.geometry(model):
        p = np.asarray(face["points"])
        v = sum(np.dot(p[0], np.cross(p[i], p[i+1]))/6 for i in range(1, len(p)-1))
        volumes[face["zone"]] = volumes.get(face["zone"], 0)+v
    assert volumes == pytest.approx({"Stair": 84, "Upper": 12})


def test_steps_require_consistent_summary_and_closed_mesh(tmp_path):
    bad = stepped()
    bad["rooms"][0]["polygon"][1][0] = 5
    with pytest.raises(ValidationError, match="底面"):
        ModelDraft.model_validate(bad)
    path = tmp_path/"box.ifc"
    path.write_text(model_export.ifc(ModelDraft.model_validate(model_body()).model_dump()), encoding="utf-8")
    doc = ifcopenshell.open(str(path))
    shape = ifcopenshell.geom.create_shape(ifcopenshell.geom.settings(), doc.by_type("IfcSpace")[0])
    with pytest.raises(ValueError, match="不闭合"):
        mesh_segments(shape.geometry.verts, shape.geometry.faces[:-3])
    vertices = np.array(shape.geometry.verts).reshape(-1, 3)
    vertices[:, 2] += vertices[:, 0]*.1
    with pytest.raises(ValueError, match="斜面"):
        mesh_segments(vertices, shape.geometry.faces)
    doc.by_type("IfcSpace")[1].Representation = None
    doc.write(str(path))
    with pytest.raises(core.ValidationError, match="未完整导入"):
        model_import.ifc(path, ImportOptions(file_id="test"))


def test_ifc_defaults_refuse_unknown_boundaries_and_pending_usage(client):
    pid = project(client)
    body = model_body()
    body["rooms"][0].update(ifc_source="original", conditioned=None, include_floor_area=None)
    assert client.put(f"/api/projects/{pid}/model", json=body).status_code == 200
    check = client.get(f"/api/projects/{pid}/model/validate").json()
    assert not check["can_publish"]
    assert len(check["blockers"]) >= 2
    model = ModelDraft.model_validate(body).model_dump()
    with pytest.raises(core.ValidationError, match="边界"):
        model_export.idf(model)
    body["thermal"].update(ifc_unpaired_policy="adiabatic_scenario", basis="documented")
    with pytest.raises(ValidationError, match="假设"):
        ModelDraft.model_validate(body)


def test_physical_wall_projection_is_bounded_and_traceable():
    body = model_body()
    body["rooms"] = body["rooms"][:1]
    body["rooms"][0].update(ifc_source="space", boundary_hints=[{
        "points": [[-.2, 0, 0], [-.2, 8, 0], [-.2, 8, 3], [-.2, 0, 3]],
        "classification": "EXTERNAL", "source_id": "wall-boundary",
        "element_plane_range_m": [-.4, 0.0]}])
    body["thermal"]["ifc_unpaired_policy"] = "adiabatic_scenario"
    surfaces = model_export.geometry(ModelDraft.model_validate(body).model_dump())
    outside = [s for s in surfaces if s["boundary"] == "Outdoors"]
    assert sum(frame(s["points"])["poly"].area for s in outside) == pytest.approx(24)
    assert all("wall-boundary" in s["boundary_basis"] for s in outside)
    body["rooms"][0]["boundary_hints"][0]["element_plane_range_m"] = [-.4, -.1]
    assert not any(s["boundary"] == "Outdoors" for s in model_export.geometry(ModelDraft.model_validate(body).model_dump()))


def test_geometry_normalization_opt_in_bounds_and_unchanged_source():
    body = stepped()
    body["rooms"][0]["segments"][1]["polygon"][1][0] = 2.992
    body["rooms"][0]["segments"][1]["polygon"][2][0] = 2.992
    body["thermal"]["geometry_tolerance_m"] = .02
    model = ModelDraft.model_validate(body).model_dump()
    original = copy.deepcopy(model)
    normalized, report = thermal_geometry_model(model)
    assert model == original and len(normalized["rooms"]) == 2
    assert report["max_axis_displacement_m"] == pytest.approx(.004)
    assert report["rooms"][0]["original_volume_m3"] != report["rooms"][0]["normalized_volume_m3"]
    body["thermal"]["basis"] = "documented"
    with pytest.raises(ValidationError, match="公差"):
        ModelDraft.model_validate(body)
    body = model_body()
    body["rooms"] = body["rooms"][:1]
    body["rooms"][0].update(height_m=3, segments=[
        {"polygon": body["rooms"][0]["polygon"], "elevation_m": 0, "height_m": .005},
        {"polygon": body["rooms"][0]["polygon"], "elevation_m": .005, "height_m": 2.995}])
    body["thermal"]["geometry_tolerance_m"] = .02
    with pytest.raises(core.ValidationError, match="消除"):
        thermal_geometry_model(ModelDraft.model_validate(body).model_dump())


def test_unconditioned_roof_keeps_geometry_without_area_or_hvac():
    body = model_body()
    body["rooms"][1].update(conditioned=False, include_floor_area=False)
    text, surfaces = model_export.idf(ModelDraft.model_validate(body).model_dump())
    assert any(s["zone"] == "R2" for s in surfaces)
    assert "R1Ideal" in text and "R2Ideal" not in text and "R2People" not in text
    zone = next(block for block in text.split(";") if block.strip().startswith("Zone,\n  R2,"))
    assert zone.strip().endswith("No")


def test_normalization_validation_failure_is_a_user_error():
    body = model_body()
    body["rooms"][0]["height_m"] = .505
    body["rooms"][1]["elevation_m"] = .015
    body["thermal"]["geometry_tolerance_m"] = .02
    with pytest.raises(core.ValidationError, match="公差后的模型"):
        thermal_geometry_model(ModelDraft.model_validate(body).model_dump())
