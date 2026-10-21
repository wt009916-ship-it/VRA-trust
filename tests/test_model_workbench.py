import copy
import io
import json
import sqlite3
import time

import ezdxf
import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from reportlab.pdfgen.canvas import Canvas

from backend import core, model_export, model_import
from backend.api import create_app
from backend.gateway import ProviderSettings
from backend.model_schema import ImportOptions, ModelDraft
from backend.modeling import Modeling


THERMAL = dict(wall_u=.8, roof_u=.5, floor_u=.6, window_u=2.5, window_shgc=.5,
               window_wall_ratio=.2, heating_c=20, cooling_c=26, infiltration_ach=.3,
               ground_temperature_c=18, lights_w_m2=6, equipment_w_m2=8, people_m2_person=12,
               active_start=8, active_end=18, north_deg=0, basis="assumed_scenario",
               source_note="Synthetic engineering test scenario; not measured building data.")

ASSEMBLIES = {key: [
    {"name": "Assumed concrete", "thickness_m": .2, "conductivity_w_mk": 1.4, "density_kg_m3": 2300, "specific_heat_j_kgk": 900},
    {"name": "Assumed insulation", "thickness_m": depth, "conductivity_w_mk": .04, "density_kg_m3": 40, "specific_heat_j_kgk": 1400}
] for key, depth in (("wall", .04), ("roof", .08), ("floor", .05))}


def project(client, area=80):
    result = client.post("/api/projects", json={"name": "Model workflow fixture",
        "building": {"use": "office", "location": "Golden", "region": "US-CO", "area_m2": area}})
    assert result.status_code == 201, result.text
    return result.json()["project_id"]


def model_body():
    return {"name": "Synthetic 80 m2 two-room building", "expected_revision": 0, "reviewed": True,
            "review_note": "Synthetic dimensions checked against test drawing, not field measurements",
            "thermal": THERMAL.copy(), "rooms": [
                {"id": "R1", "name": "West", "polygon": [[0, 0], [5, 0], [5, 8], [0, 8]], "height_m": 3},
                {"id": "R2", "name": "East", "polygon": [[5, 0], [10, 0], [10, 8], [5, 8]], "height_m": 3}]}


def drawing_bytes():
    doc = ezdxf.new("R2010")
    doc.units = 4
    doc.modelspace().add_lwpolyline([(0, 0), (5000, 0), (5000, 8000), (0, 8000)], close=True,
                                  dxfattribs={"layer": "ROOMS"})
    doc.modelspace().add_lwpolyline([(5000, 0), (10000, 0), (10000, 8000), (5000, 8000)], close=True,
                                  dxfattribs={"layer": "ROOMS"})
    stream = io.StringIO()
    doc.write(stream)
    return stream.getvalue().encode()


def upload(client, pid, name, content):
    result = client.post(f"/api/projects/{pid}/files", files={"file": (name, content)})
    assert result.status_code == 201, result.text
    return result.json()["file_id"]


def test_dxf_workflow_pause_restart_review_idempotence(client):
    pid = project(client)
    fid = upload(client, pid, "rooms.dxf", drawing_bytes())
    response = client.post(f"/api/projects/{pid}/imports", json={"file_id": fid, "layer": "ROOMS"})
    assert response.status_code == 201, response.text
    task = response.json()
    assert task["status"] == "awaiting_review" and len(task["candidate"]["rooms"]) == 2
    assert task["candidate"]["metadata"]["units_to_m"] == .001
    assert client.get(f"/api/projects/{pid}/model").json() is None
    # Simulate a new process's service objects while retaining SQLite checkpoints.
    service = Modeling(client.app.state.domain, client.app.state.gateway)
    service.recover()
    body = ModelDraft.model_validate({**model_body(), "rooms": task["candidate"]["rooms"]})
    result = service.resume(pid, task["import_id"], body, "Test reviewer")
    assert result["status"] == "completed" and result["model"]["area_m2"] == 80
    again = service.resume(pid, task["import_id"], body, "Test reviewer")
    assert again["model"]["revision"] == 1
    assert len(service.history(pid)) == 1
    with sqlite3.connect(service.checkpoints) as con:
        assert con.execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0] >= 3


def test_cross_project_import_and_file_are_denied(client):
    pid, other = project(client), project(client)
    fid = upload(client, pid, "rooms.dxf", drawing_bytes())
    assert client.post(f"/api/projects/{other}/imports", json={"file_id": fid}).status_code == 409
    task = client.post(f"/api/projects/{pid}/imports", json={"file_id": fid}).json()
    assert client.post(f"/api/projects/{other}/imports/{task['import_id']}/review", json=model_body()).status_code == 404


def test_pdf_requires_scale_and_extracts_actual_vectors(tmp_path):
    path = tmp_path/"plan.pdf"
    canvas = Canvas(str(path), pagesize=(200, 200))
    canvas.rect(10, 20, 100, 80)
    canvas.showPage()
    canvas.save()
    options = ImportOptions(file_id="unused")
    with pytest.raises(core.ValidationError, match="比例"):
        model_import.pdf(path, options)
    options.scale_to_m = .1
    result = model_import.pdf(path, options)
    assert len(result["rooms"]) == 1
    assert ModelDraft.model_validate({**model_body(), "rooms": result["rooms"]}).rooms[0].polygon
    assert PolygonArea(result["rooms"][0]["polygon"]) == pytest.approx(80)


def PolygonArea(points):
    from shapely.geometry import Polygon
    return Polygon(points).area


def test_pdf_keeps_diagonal_endpoints_and_skips_curves(tmp_path):
    path = tmp_path/"diagonal.pdf"
    canvas = Canvas(str(path), pagesize=(200, 200))
    for a, b in [((10, 20), (110, 20)), ((110, 20), (40, 100)), ((40, 100), (10, 20))]:
        canvas.line(*a, *b)
    canvas.circle(150, 150, 20)
    canvas.save()
    parsed = model_import.pdf(path, ImportOptions(file_id="unused", scale_to_m=.1))
    assert len(parsed["rooms"]) == 1
    assert PolygonArea(parsed["rooms"][0]["polygon"]) == pytest.approx(40)
    assert sorted(parsed["rooms"][0]["polygon"]) == sorted([(1, 2), (11, 2), (4, 10)])


def test_ifc_roundtrip_preserves_space_geometry_and_elevation(tmp_path):
    data = ModelDraft.model_validate(model_body()).model_dump()
    data["rooms"][0]["elevation_m"] = 3
    path = tmp_path/"building.ifc"
    path.write_text(model_export.ifc(data), encoding="utf-8")
    parsed = model_import.ifc(path, ImportOptions(file_id="unused"))
    assert len(parsed["rooms"]) == 2
    west = next(r for r in parsed["rooms"] if r["name"] == "West")
    assert west["elevation_m"] == pytest.approx(3)
    assert west["height_m"] == pytest.approx(3)
    assert PolygonArea(west["polygon"]) == pytest.approx(40)


@pytest.mark.parametrize("change", ["overlap", "self_intersection", "duplicate", "case_duplicate",
                                  "boolean_geometry", "boolean_thermal", "nan", "thermal_order"])
def test_model_rejects_bad_geometry_and_parameters(change):
    body = model_body()
    if change == "overlap":
        body["rooms"][1]["polygon"] = body["rooms"][0]["polygon"]
    elif change == "self_intersection":
        body["rooms"][0]["polygon"] = [[0, 0], [5, 8], [5, 0], [0, 8]]
    elif change == "duplicate":
        body["rooms"][1]["id"] = "R1"
    elif change == "case_duplicate":
        body["rooms"][1]["id"] = "r1"
    elif change == "boolean_geometry":
        body["rooms"][0]["polygon"][0][0] = True
    elif change == "boolean_thermal":
        body["thermal"]["infiltration_ach"] = True
    elif change == "nan":
        body["rooms"][0]["height_m"] = float("nan")
    else:
        body["thermal"]["heating_c"] = 28
        body["thermal"]["cooling_c"] = 22
    with pytest.raises(ValidationError):
        ModelDraft.model_validate(body)


def test_compiler_shared_walls_and_partial_stacked_contacts():
    model = ModelDraft.model_validate(model_body()).model_dump()
    text, surfaces = model_export.idf(model)
    shared = [s for s in surfaces if s["boundary"] == "Surface"]
    assert len(shared) == 2
    assert shared[0]["other"] == shared[1]["name"]
    assert all(s["kind"] == "Wall" for s in shared)
    assert "IdealLoadsAirSystem" in text and "Output:SQLite" in text
    upstairs = copy.deepcopy(model["rooms"][0])
    upstairs.update(id="R3", elevation_m=3, polygon=[[0, 0], [3, 0], [3, 8], [0, 8]])
    model["rooms"].append(upstairs)
    from backend.model_geometry import frame
    surfaces = model_export.geometry(model)
    lookup = {s["name"]: s for s in surfaces}
    shared_roof = [s for s in surfaces if s["zone"] == "R1" and s["kind"] == "Roof" and s["boundary"] == "Surface"]
    outdoor_roof = [s for s in surfaces if s["zone"] == "R1" and s["kind"] == "Roof" and s["boundary"] == "Outdoors"]
    assert sum(frame(s["points"])["poly"].area for s in shared_roof) == pytest.approx(24)
    assert sum(frame(s["points"])["poly"].area for s in outdoor_roof) == pytest.approx(16)
    for s in surfaces:
        if s["boundary"] == "Surface":
            other = lookup[s["other"]]
            assert other["other"] == s["name"] and other["zone"] != s["zone"]
            assert frame(s["points"])["side"] == -frame(other["points"])["side"]


def test_layered_envelope_derives_u_and_exports_mass():
    body = model_body()
    body["thermal"]["constructions"] = copy.deepcopy(ASSEMBLIES)
    model = ModelDraft.model_validate(body).model_dump()
    assert model["thermal"]["wall_u"] == pytest.approx(1/(.2/1.4+.04/.04+.17))
    text, _ = model_export.idf(model)
    assert "Material:NoMass" not in text
    assert "Wall_L1" in text and "2300.0" in text
    # Persisting and reloading the derived U must remain valid.
    assert ModelDraft.model_validate(model).model_dump() == model
    body["thermal"]["constructions"]["wall"][1].update(thickness_m=2, conductivity_w_mk=.006)
    with pytest.raises(ValidationError, match="U 值"):
        ModelDraft.model_validate(body)


def test_model_publication_version_binding_and_idempotence(client):
    pid = project(client)
    base = f"/api/projects/{pid}"
    body = model_body()
    response = client.put(base+"/model", json=body)
    assert response.status_code == 200, response.text
    publish = {"revision": 1, "responsible_person": "Fixture reviewer", "review_note": "Parameters are synthetic and ideal load scope reviewed"}
    first = client.post(base+"/model/publish", json=publish)
    assert first.status_code == 200, first.text
    assert client.post(base+"/model/publish", json=publish).json()["reused"]
    ev = first.json()["evidence"]
    assert ev["status"] == "ASSUMED" and ev["review_state"] == "confirmed"
    assert ev["value"]["revision"] == 1 and ev["value"]["scope"] == "ideal_thermal_loads"
    assert client.put(base+"/model", json=body).status_code == 409
    body.update(expected_revision=1)
    body["thermal"]["wall_u"] = .5
    assert client.put(base+"/model", json=body).status_code == 200
    # Published scheme snapshots remain usable while new candidates are edited.
    gate = client.get(base+"/gate").json()
    assert not any(b["field"] == "idf" for b in gate["blockers"])
    assert client.post(base+"/model/publish", json=publish).status_code == 409
    publish["revision"] = 2
    second = client.post(base+"/model/publish", json=publish).json()
    assert second["evidence"]["evidence_id"] != ev["evidence_id"]
    records = client.get(base+"/evidence").json()
    assert next(e for e in records if e["evidence_id"] == ev["evidence_id"])["review_state"] == "rejected"
    assert client.get(base+"/model/export.ifc").content.startswith(b"ISO-10303-21")


def test_model_requires_review_thermal_and_matching_area(client):
    pid = project(client, area=90)
    body = model_body()
    body.update(reviewed=False, thermal=None)
    base = f"/api/projects/{pid}"
    assert client.put(base+"/model", json=body).status_code == 200
    check = client.get(base+"/model/validate").json()
    assert not check["can_publish"] and len(check["blockers"]) == 3
    assert client.post(base+"/model/sync-area", json={"revision": 2}).status_code == 409
    assert client.post(base+"/model/sync-area", json={"revision": 1}).json()["building"]["area_m2"] == 80


def test_project_tokens_enforce_scope_expiry_and_revocation(client):
    pid, other = project(client), project(client)
    base = f"/api/projects/{pid}"
    created = client.post(base+"/tokens", json={"name": "Read only"}).json()
    headers = {"Authorization": "Bearer "+created["token"]}
    assert client.get(base+"/model", headers=headers).status_code == 200
    assert client.get(f"/api/projects/{other}/model", headers=headers).status_code == 403
    assert client.get("/api/developer/provider", headers=headers).status_code == 403
    assert client.get(base+"/tokens", headers=headers).status_code == 403
    assert client.put(base+"/model", json=model_body(), headers=headers).status_code == 403
    assert client.post(base+"/model-runs", json={}, headers=headers).status_code == 403
    with client.app.state.domain.store.connect() as con:
        row = con.execute("SELECT * FROM api_tokens WHERE id=?", (created["id"],)).fetchone()
        assert created["token"] not in str(dict(row))
        con.execute("UPDATE api_tokens SET expires=? WHERE id=?", (time.time()-1, created["id"]))
    assert client.get(base+"/model", headers=headers).status_code == 401
    second = client.post(base+"/tokens", json={"name": "Write", "scopes": ["read", "write"]}).json()
    headers = {"Authorization": "Bearer "+second["token"]}
    assert client.put(base+"/model", json=model_body(), headers=headers).status_code == 200
    assert client.post(base+"/studies", json={}, headers=headers).status_code == 403
    assert client.delete(base+"/tokens/"+second["id"]).status_code == 200
    assert client.get(base+"/model", headers=headers).status_code == 401


def test_bearer_works_without_session_or_csrf(client):
    pid = project(client)
    token = client.post(f"/api/projects/{pid}/tokens", json={"name": "Machine client", "scopes": ["read", "write"]}).json()["token"]
    with TestClient(client.app) as external:
        headers = {"Authorization": "Bearer "+token}
        assert external.get(f"/api/projects/{pid}", headers=headers).status_code == 200
        assert external.put(f"/api/projects/{pid}/model", json=model_body(), headers=headers).status_code == 200
        assert external.get("/api/projects", headers=headers).status_code == 403


def test_generic_vision_provider_protocol_and_key_isolation(client, monkeypatch):
    gateway = client.app.state.gateway
    monkeypatch.setenv("DEEPSEEK_API_KEY", "not-for-another-host")
    settings = ProviderSettings(enabled=True, endpoint="https://example.org/v1/chat/completions",
                                model="vendor/text", vision_model="vendor/vision")
    gateway.save(settings)
    assert not gateway.public()["key_configured"]
    monkeypatch.setenv("VRA_API_KEY", "synthetic-protocol-key")
    def handle(req):
        body = json.loads(req.content)
        assert body["model"] == "vendor/vision" and "tools" not in body and "thinking" not in body
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": '{"rooms":[]}'}}]})
    assert gateway.complete([], [], vision=True, transport=httpx.MockTransport(handle))["content"] == '{"rooms":[]}'
    assert client.put("/api/developer/provider", json={"enabled": True, "endpoint": "http://remote.test/chat/completions"}).status_code == 422


def test_vision_requires_explicit_send_and_scale(tmp_path):
    from PIL import Image
    path = tmp_path/"scan.png"
    Image.new("RGB", (100, 80)).save(path)
    options = ImportOptions(file_id="unused", mode="vision", scale_to_m=.1)
    with pytest.raises(core.ValidationError, match="明确"):
        model_import.vision(path, options, None)
    options.send_to_provider = True
    class FakeProvider:
        def complete(self, messages, tools, vision=False):
            assert vision and messages[1]["content"][1]["image_url"]["url"].startswith("data:image/png")
            return {"content": '{"rooms":[{"name":"room","polygon":[[0,0],[100,0],[100,80],[0,80]]}]}'}
        def public(self):
            return {"vision_model": "protocol-fixture-only"}
    candidate = model_import.vision(path, options, FakeProvider())
    assert PolygonArea(candidate["rooms"][0]["polygon"]) == pytest.approx(80)
    assert "AI_INFERRED" in candidate["rooms"][0]["source_locator"]


def test_persisted_model_survives_app_restart(client):
    pid = project(client)
    client.put(f"/api/projects/{pid}/model", json=model_body())
    app = create_app(client.app.state.domain.store.root, start_worker=False)
    assert app.state.modeling.get(pid)["revision"] == 1
    assert app.state.modeling.get(pid)["area_m2"] == 80
