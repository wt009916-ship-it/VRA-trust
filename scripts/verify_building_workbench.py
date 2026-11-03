"""Exercise DXF -> persisted review -> IFC/IDF -> native yearly EnergyPlus.

Synthetic acceptance fixture, never real-project evidence.
Usage: python scripts/verify_building_workbench.py --output <new directory>
Requires ENERGYPLUS_EXE pointing to EnergyPlus 9.0.1 and dev dependencies.
"""
import argparse
import json
import os
from pathlib import Path
import runpy
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    if out.exists():
        raise SystemExit("Use a new output directory; existing evidence is preserved")
    out.mkdir(parents=True)
    os.environ["VRA_DATA_DIR"] = str(out/"data")
    from fastapi.testclient import TestClient
    from backend import core
    from backend.api import create_app
    helpers = runpy.run_path(str(ROOT/"tests/test_model_workbench.py"))
    app = create_app(out/"data", start_worker=True)

    def checked(response, expected=200):
        if response.status_code != expected:
            raise RuntimeError(response.text)
        return response.json()

    with TestClient(app) as client:
        session = checked(client.post("/api/auth/register", json={"username": "acceptance_only",
                          "display_name": "Synthetic fixture reviewer", "password": "Acceptance-only-2026-long-pass"}))
        client.headers["X-CSRF-Token"] = session["csrf_token"]
        pid = helpers["project"](client)
        base = f"/api/projects/{pid}"
        content = helpers["drawing_bytes"]()
        (out/"synthetic-two-room.dxf").write_bytes(content)
        fid = helpers["upload"](client, pid, "synthetic-two-room.dxf", content)
        task = checked(client.post(base+"/imports", json={"file_id": fid, "layer": "ROOMS"}), 201)
        body = {**helpers["model_body"](), "rooms": task["candidate"]["rooms"]}
        body["thermal"]["constructions"] = helpers["ASSEMBLIES"]
        review = checked(client.post(base+"/imports/"+task["import_id"]+"/review", json=body))
        model = review["model"]
        (out/"building.ifc").write_bytes(client.get(base+"/model/export.ifc").content)
        published = checked(client.post(base+"/model/publish", json={"revision": model["revision"],
            "responsible_person": "Synthetic fixture reviewer",
            "review_note": "Synthetic dimensions, simplified ideal loads, and scenario inputs reviewed for software acceptance only"}))
        weather = core.relative_file(core.ROOT, core.load_case("reference_5zone")["weather"])
        weather_id = helpers["upload"](client, pid, weather.name, weather.read_bytes())
        ev = checked(client.post(base+"/evidence", json={"type": "epw", "name": weather.name, "source_file": weather_id,
             "source_locator": "EnergyPlus official Golden reference weather; whole file", "authority": "EnergyPlus",
             "permission": "Distributed reference data; notices retained in repository", "acquisition_method": "acceptance fixture",
             "responsible_person": "Synthetic fixture reviewer", "status": "IMPORTED"}), 201)
        checked(client.patch(base+"/evidence/"+ev["evidence_id"], json={"expected_revision": ev["revision"],
            "review_state": "confirmed", "responsible_person": "Synthetic fixture reviewer",
            "review_note": "Weather is the documented reference fixture, not local weather for a customer project"}))
        runs = []
        for scheme in ("baseline", "R1"):
            if scheme == "R1":
                body["expected_revision"] = model["revision"]
                body["thermal"]["wall_u"] = .4
                body["thermal"]["roof_u"] = .3
                body["thermal"]["constructions"]["wall"][1]["thickness_m"] = .08
                body["thermal"]["constructions"]["roof"][1]["thickness_m"] = .12
                model = checked(client.put(base+"/model", json=body))
                checked(client.post(base+"/model/publish", json={"revision": model["revision"], "scheme_id": scheme,
                    "responsible_person": "Synthetic fixture reviewer",
                    "review_note": "R1 differs only by assumed envelope U values; all other inputs held constant"}))
            run = checked(client.post(base+"/model-runs", json={"scheme_id": scheme}), 202)
            deadline = time.monotonic()+180
            while run["status"] in {"queued", "running"} and time.monotonic() < deadline:
                time.sleep(.5)
                run = checked(client.get("/api/runs/"+run["run_id"]))
            runs.append(run)
            core.write_json(out/(scheme+"-result.json"), run)
            if run["status"] != "succeeded":
                raise RuntimeError(json.dumps(run, ensure_ascii=False))
            assert run["metrics"]["area_m2"] == 80
            assert run["metrics"]["annual_days"] in (365, 366)
            assert run["carbon"]["operating_carbon_kg"] is None
            (out/(scheme+"-report.html")).write_bytes(client.get("/api/runs/"+run["run_id"]+"/report.html").content)
            (out/(scheme+"-report.pdf")).write_bytes(client.get("/api/runs/"+run["run_id"]+"/report.pdf").content)
            (out/(scheme+"-artifacts.zip")).write_bytes(client.get("/api/runs/"+run["run_id"]+"/artifacts").content)
        comparison = checked(client.post("/api/comparisons", json={"run_ids": [r["run_id"] for r in runs]}))
        checked(client.post(base+"/model/publish", json={"revision": model["revision"],
            "responsible_person": "Synthetic fixture reviewer",
            "review_note": "Replace baseline with the reviewed second version to verify stale input invalidation"}))
        stale = checked(client.get("/api/runs/"+runs[0]["run_id"]))
        assert stale["status"] == "stale" and stale["metrics"] is None
        summary = {"verified_at": core.now(), "fixture": "synthetic DXF; 2 adjacent rectangular rooms; 80 m2",
                   "workflow": task["import_id"], "project_id": pid, "model_binding": published["binding"],
                   "real_engine_calls": sum(r["engine_calls_executed"] for r in runs),
                   "runs": runs, "comparison": comparison, "republish_invalidates_old_run": True,
                   "live_provider_tested": False, "real_customer_drawing_tested": False}
        core.write_json(out/"acceptance.json", summary)
        print(json.dumps({"status": "passed", "real_engine_calls": 2, "runs":
              [{"scheme": r["scheme_id"], "energy_kwh": r["metrics"]["annual_energy_kwh"],
                "carriers": r["metrics"]["energy_by_carrier_kwh"], "warnings": r["warnings_count"]} for r in runs]},
              ensure_ascii=False))


if __name__ == "__main__":
    main()
