"""Pinned buildingSMART Duplex -> API -> annual native engine, explicitly assumed.

Download the original IFC from the source linked in docs/EXTERNAL_SAMPLE_AUDIT.md.
Usage: python scripts/verify_external_duplex.py --source <IFC> --output <new folder>
The private-runtime directory contains isolated accounts and must not be published.
"""
import argparse
import copy
import json
import os
from pathlib import Path
import runpy
import secrets
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SOURCE_SHA = "b347a2c8aa8fff6db896a4417a9c50c22ac0ccd7c5cfc22b99b8d29336c606ed"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source, out = args.source.resolve(), args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    os.environ["VRA_DATA_DIR"] = str(out/"private-runtime")
    from fastapi.testclient import TestClient
    from backend import core, model_geometry, model_import
    from backend.api import create_app
    from backend.model_schema import ImportOptions
    assert core.sha(source) == SOURCE_SHA
    helpers = runpy.run_path(str(ROOT/"tests/test_model_workbench.py"))
    trace = []

    def checked(step, response, expected=200):
        data = response.json()
        trace.append({"step": step, "http_status": response.status_code, "body": data})
        core.write_json(out/"api-trace.json", trace)
        assert response.status_code == expected, response.text
        return data

    app = create_app(out/"private-runtime", start_worker=True)
    with TestClient(app) as client:
        response = client.post("/api/auth/register", json={"username": "isolated_duplex",
            "display_name": "Software acceptance only", "password": secrets.token_urlsafe(32)})
        assert response.status_code == 200
        client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
        pid = helpers["project"](client, area=375.745686)
        base = f"/api/projects/{pid}"
        fid = helpers["upload"](client, pid, source.name, source.read_bytes())
        start = time.perf_counter()
        task = checked("import_original", client.post(base+"/imports", json={"file_id": fid}), 201)
        elapsed = time.perf_counter()-start
        rooms = task["candidate"]["rooms"]
        assert len(rooms) == 21
        assert sum(len(model_geometry.parts(r)) for r in rooms) == 25
        body = {"name": "Duplex source geometry; explicit thermal scenario",
                "rooms": rooms, "expected_revision": 0, "reviewed": True,
                "review_note": "Software acceptance only, not engineering attestation. Full source spaces retained."}
        reviewed = checked("review_source_spaces", client.post(base+"/imports/"+task["import_id"]+"/review", json=body))
        check = checked("default_publish_refusal", client.get(base+"/model/validate"))
        assert not check["can_publish"]
        assert all(r["conditioned"] is None and r["include_floor_area"] is None for r in rooms)
        # Explicit test choices, never inferred heating or area classifications.
        body = copy.deepcopy(body)
        body["expected_revision"] = reviewed["model"]["revision"]
        roof = [r for r in body["rooms"] if r["name"] == "R301 · Roof"]
        assert len(roof) == 1
        for room in body["rooms"]:
            room.update(conditioned=room["id"] != roof[0]["id"], include_floor_area=room["id"] != roof[0]["id"])
        body["thermal"] = {**helpers["THERMAL"], "constructions": helpers["ASSEMBLIES"],
            "ifc_unpaired_policy": "adiabatic_scenario", "geometry_tolerance_m": .02,
            "source_note": "Software test scenario only: assumed materials, uniform glazing, schedules and Golden weather; "
                           "unpaired internal/unknown boundaries adiabatic; coordinate clustering tolerance 0.02 m; "
                           "Roof space retained but unconditioned and excluded from area. Not calibrated building performance."}
        model = checked("save_explicit_scenario", client.put(base+"/model", json=body))
        checked("sync_included_area", client.post(base+"/model/sync-area", json={"revision": model["revision"]}))
        core.write_json(out/"model.json", model)
        check = checked("scenario_validation", client.get(base+"/model/validate"))
        assert check["can_publish"]
        exported = client.get(base+"/model/export.ifc")
        assert exported.status_code == 200
        (out/"spaces.ifc").write_bytes(exported.content)
        roundtrip = model_import.ifc(out/"spaces.ifc", ImportOptions(file_id="roundtrip"))
        assert len(roundtrip["rooms"]) == 21
        assert sum(len(model_geometry.parts(r)) for r in roundtrip["rooms"]) == 25
        published = checked("publish_scenario", client.post(base+"/model/publish", json={
            "revision": model["revision"], "responsible_person": "Software acceptance only",
            "review_note": body["thermal"]["source_note"]}))
        exported = client.get(base+"/model/export.idf")
        assert exported.status_code == 200
        (out/"scenario.idf").write_bytes(exported.content)
        weather = core.relative_file(core.ROOT, core.load_case("reference_5zone")["weather"])
        weather_id = helpers["upload"](client, pid, weather.name, weather.read_bytes())
        ev = checked("register_reference_weather", client.post(base+"/evidence", json={
            "type": "epw", "name": weather.name, "source_file": weather_id,
            "source_locator": "Official EnergyPlus Golden reference weather, entire file",
            "authority": "EnergyPlus", "permission": "Reference weather with original notices",
            "acquisition_method": "Software acceptance fixture", "responsible_person": "Software acceptance only",
            "status": "ASSUMED"}), 201)
        checked("review_reference_weather", client.patch(base+"/evidence/"+ev["evidence_id"], json={
            "expected_revision": ev["revision"], "review_state": "confirmed",
            "responsible_person": "Software acceptance only",
            "review_note": "Golden weather is assumed for this test, not verified as the source building location."}))
        run = checked("queue_annual_simulation", client.post(base+"/model-runs", json={"scheme_id": "baseline"}), 202)
        deadline = time.monotonic()+240
        while run["status"] in {"queued", "running"} and time.monotonic() < deadline:
            time.sleep(.5)
            response = client.get("/api/runs/"+run["run_id"])
            assert response.status_code == 200
            run = response.json()
        core.write_json(out/"result.json", run)
        assert run["status"] == "succeeded", json.dumps(run, ensure_ascii=False)
        assert run["metrics"]["annual_days"] in (365, 366)
        assert abs(run["metrics"]["area_m2"]-240.59453) < .01
        assert run["engine_calls_executed"] == 1
        assert run["warnings_count"] == 0
        for suffix, endpoint in [("html", "report.html"), ("pdf", "report.pdf"), ("zip", "artifacts")]:
            response = client.get(f"/api/runs/{run['run_id']}/{endpoint}")
            assert response.status_code == 200
            (out/("annual-evidence."+suffix)).write_bytes(response.content)
        assert core.sha(source) == SOURCE_SHA
        summary = {"verified_at": core.now(), "source_sha256": SOURCE_SHA, "source_modified": False,
            "source_space_count": 21, "imported_space_count": 21, "height_segments": 25,
            "source_geometry_modified": False, "thermal_geometry_adjusted": True,
            "included_area_m2": model["area_m2"], "roof_space_retained": True,
            "ifc_roundtrip_spaces": 21, "ifc_roundtrip_segments": 25, "import_seconds": elapsed,
            "scope": "Explicit assumed scenario; not complete IFC thermal translation or calibrated performance",
            "default_missing_inputs_refused": True, "binding": published["binding"],
            "actual_engine_calls": 1, "live_ai_calls": 0, "annual_days": run["metrics"]["annual_days"],
            "warnings": run["warnings_count"], "metrics": run["metrics"],
            "runtime_config": {"engine": str(core.engine_path()), "weather_sha256": core.sha(weather)}}
        core.write_json(out/"acceptance.json", summary)
        print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
