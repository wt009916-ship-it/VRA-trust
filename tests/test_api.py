import pytest
from fastapi.testclient import TestClient
from backend import core
from backend.api import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path / "data", start_worker=False)
    with TestClient(app) as client:
        yield client


def create_project(client, **changes):
    data = {"name": "Test project", "building": {"use": "office", "location": "Golden", "region": "US-CO", "area_m2": 927.2}}
    data.update(changes)
    response = client.post("/api/projects", json=data)
    assert response.status_code == 201, response.text
    return response.json()


def reference(client):
    response = client.post("/api/reference-projects")
    assert response.status_code == 201, response.text
    return response.json()


def confirm(client, project_id):
    for ev in client.get(f"/api/projects/{project_id}/evidence").json():
        response = client.patch(f"/api/projects/{project_id}/evidence/{ev['evidence_id']}", json={"expected_revision": ev["revision"], "review_state": "confirmed", "responsible_person": "Automated reference test", "review_note": "Reference fixture inspected; not field evidence"})
        assert response.status_code == 200, response.text


def test_project_persists_and_declares_missing_evidence(client):
    p = create_project(client)
    assert client.get("/api/projects").json()[0]["project_id"] == p["project_id"]
    gate = client.get(f"/api/projects/{p['project_id']}/gate").json()
    assert gate["can_simulate"] is False
    assert {b["field"] for b in gate["blockers"]} == {"idf", "epw"}
    assert client.post("/api/runs", json={"project_id": p["project_id"], "scheme_id": "baseline"}).status_code == 409


@pytest.mark.parametrize("area", [-1, 0, True, "NaN", "Infinity"])
def test_invalid_area_rejected(client, area):
    response = client.post("/api/projects", json={"name": "x", "building": {"use": "office", "location": "x", "region": "US-CO", "area_m2": area}})
    assert response.status_code == 422


def test_json_nonfinite_has_safe_error(client):
    response = client.post("/api/projects", content='{"name":"x","building":{"use":"x","location":"x","region":"x","area_m2":NaN}}', headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert "input" not in response.json()["detail"][0]


def test_unknown_fields_rejected(client):
    response = client.post("/api/projects", json={"name": "x", "building": {}, "energy": 123})
    assert response.status_code == 422


def test_reference_has_inputs_but_no_results(client):
    p = reference(client)
    assert p["data_nature"] == "engineering_reference"
    assert client.get(f"/api/projects/{p['project_id']}/runs").json() == []
    gate = client.get(f"/api/projects/{p['project_id']}/gate").json()
    assert not gate["can_simulate"]
    assert all(b["code"] == "REVIEW_REQUIRED" for b in gate["blockers"])
    confirm(client, p["project_id"])
    gate = client.get(f"/api/projects/{p['project_id']}/gate").json()
    assert gate["can_simulate"] and not gate["can_recommend"]


def test_review_conflict_and_immutable_history(client):
    p = reference(client)
    ev = client.get(f"/api/projects/{p['project_id']}/evidence").json()[0]
    path = f"/api/projects/{p['project_id']}/evidence/{ev['evidence_id']}"
    body = {"expected_revision": 1, "review_state": "confirmed", "responsible_person": "reviewer", "review_note": "Review source and scope"}
    assert client.patch(path, json=body).status_code == 200
    assert client.patch(path, json=body).status_code == 409
    history = client.get(path + "/history").json()
    assert [e["revision"] for e in history] == [1, 2]
    assert history[0]["review_state"] == "pending"


def test_cross_project_file_rejected(client):
    a, b = reference(client), create_project(client)
    ev = client.get(f"/api/projects/{a['project_id']}/evidence").json()[0]
    assert client.get(f"/api/projects/{b['project_id']}/files/{ev['source_file']}").status_code == 409
    assert client.get(f"/api/projects/{b['project_id']}/evidence/{ev['evidence_id']}/history").status_code == 409


def test_source_tamper_revokes_gate(client):
    p = reference(client)
    confirm(client, p["project_id"])
    domain = client.app.state.domain
    ev = next(e for e in domain.store.list("evidence", p["project_id"]) if e["type"] == "epw")
    record, path = domain.file_record(p["project_id"], ev["source_file"])
    path.write_bytes(path.read_bytes() + b"tamper")
    gate = client.get(f"/api/projects/{p['project_id']}/gate").json()
    assert not gate["can_simulate"]
    assert any(b["code"] == "INVALID_SOURCE" for b in gate["blockers"])


def test_upload_boundaries(client):
    p = create_project(client)
    url = f"/api/projects/{p['project_id']}/files"
    assert client.post(url, files={"file": ("x.exe", b"bad")}).status_code == 409
    assert client.post(url, files={"file": ("x.csv", b"")}).status_code == 409
    result = client.post(url, files={"file": ("../../bill.csv", b"month,kWh\nJan,100")})
    assert result.status_code == 201
    assert result.json()["name"] == "bill.csv"
    assert client.get(f"/api/projects/{p['project_id']}/files/{result.json()['file_id']}").content == b"month,kWh\nJan,100"


def test_origin_and_host_blocked(client):
    assert client.post("/api/reference-projects", headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.get("/api/health", headers={"Host": "evil.example"}).status_code == 400


def test_old_demo_json_not_served(client):
    for path in ["/dashboard_data.json", "/fixtures/demo/frontend-public/dashboard_data.json", "/.env", "/runtime/vra.sqlite3"]:
        assert client.get(path).status_code == 404


def test_contract_declares_provenance_and_nullable_metrics(client):
    schemas = client.get("/openapi.json").json()["components"]["schemas"]
    assert set(schemas["Provenance"]["required"]) == {"run_id", "project_id", "case_id", "scheme_id", "model_hash", "weather_hash", "engine_version", "code_version", "parser_version", "factor_version", "timestamp"}
    assert {"type": "null"} in schemas["RunView"]["properties"]["metrics"]["anyOf"]


def test_persistent_queue_and_restart_failure(client, monkeypatch, tmp_path):
    p = reference(client)
    confirm(client, p["project_id"])
    engine = tmp_path / "energyplus.exe"
    engine.write_bytes(b"fixture-not-executable")
    (tmp_path / "Energy+.idd").write_bytes(b"fixture-idd")
    monkeypatch.setattr(core, "engine_path", lambda: engine)
    result = client.post("/api/runs", json={"project_id": p["project_id"], "scheme_id": "baseline"})
    assert result.status_code == 202, result.text
    run = result.json()
    assert run["status"] == "queued" and run["metrics"] is None
    store = client.app.state.domain.store
    assert store.claim_job()["run_id"] == run["run_id"]
    store.recover()
    assert store.job(run["run_id"])["status"] == "failed"
    assert client.get('/api/runs/' + run["run_id"]).json()["metrics"] is None


def test_building_revision_conflict(client):
    p = create_project(client)
    url = f"/api/projects/{p['project_id']}/building"
    body = {"expected_revision": 1, "building": {**p["building"], "area_m2": 100}}
    assert client.put(url, json=body).status_code == 200
    assert client.put(url, json=body).status_code == 409


def test_health_does_not_claim_agent_or_robustness(client):
    result = client.get("/api/health").json()
    assert not result["capabilities"]["llm_tools"]
    assert not result["capabilities"]["robustness"]
    assert not result["demo_mode"]


def test_report_reuses_one_validation_snapshot(client, monkeypatch):
    domain = client.app.state.domain
    calls = []
    def view(run_id):
        calls.append(run_id)
        return {"status": "stale", "provenance": None}
    monkeypatch.setattr(domain, "view", view)
    monkeypatch.setattr(domain.store, "job", lambda rid: {"project_snapshot": {}, "evidence_snapshot": {}, "scheme_id": "baseline"})
    report = domain.report("snapshot_test")
    assert calls == ["snapshot_test"]
    assert report["certificate"]["status"] == "STALE"
    assert report["claims"]["nodes"][0]["state"] == "STALE"


def test_upload_size_limit(tmp_path, monkeypatch):
    monkeypatch.setenv("VRA_MAX_UPLOAD_MB", "1")
    with TestClient(create_app(tmp_path / "small", start_worker=False)) as client:
        p = create_project(client)
        url = f"/api/projects/{p['project_id']}/files"
        response = client.post(url, files={"file": ("large.csv", b"x" * (1024 * 1024 + 1))})
        assert response.status_code == 413
        assert client.app.state.domain.store.list("file", p["project_id"]) == []


def test_ai_inference_cannot_be_promoted_by_review(client):
    p = create_project(client)
    response = client.post(f"/api/projects/{p['project_id']}/evidence", json={"type": "ai_inference", "name": "wall candidate", "source_locator": "Drawing A17 hypothetical crop", "value": 200, "unit": "mm", "authority": "AI suggestion", "permission": "test fixture", "acquisition_method": "test_only", "responsible_person": "tester", "status": "AI_INFERRED"})
    assert response.status_code == 201
    ev = response.json()
    response = client.patch(f"/api/projects/{p['project_id']}/evidence/{ev['evidence_id']}", json={"expected_revision": 1, "review_state": "confirmed", "responsible_person": "tester", "review_note": "Try to promote suggestion"})
    assert response.status_code == 409


def test_stale_calculation_does_not_falsely_invalidate_unchanged_evidence(client, monkeypatch):
    p = reference(client)
    confirm(client, p["project_id"])
    domain = client.app.state.domain
    inputs = domain.gate(p["project_id"])["selected_evidence"]
    monkeypatch.setattr(domain.store, "job", lambda rid: {"evidence_snapshot": inputs})
    graph = domain.claims("test_calculation_changed", {"status": "stale"})
    assert all(n["state"] == "VALID" for n in graph["nodes"] if n["kind"] == "Evidence")
    assert next(n for n in graph["nodes"] if n["kind"] == "Simulation")["state"] == "STALE"
