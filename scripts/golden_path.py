"""Real API -> evidence gate -> EnergyPlus -> result/PDF -> stale and area refusal.

The reference model is not a measured building. No fake provider or engine is used.
"""
import json
import sys
import time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fastapi.testclient import TestClient
from backend.api import create_app
from backend import core

out = ROOT / "validation/phase1"
out.mkdir(parents=True, exist_ok=True)
checks = []


def check(condition, name):
    checks.append({"name": name, "passed": bool(condition)})
    if not condition:
        raise AssertionError(name)


with TestClient(create_app(ROOT / "runtime")) as client:
    response = client.post("/api/reference-projects")
    check(response.status_code == 201, "reference project created through API")
    p = response.json()
    pid = p["project_id"]
    check(client.post("/api/runs", json={"project_id": pid, "scheme_id": "baseline"}).status_code == 409, "gate rejects unreviewed evidence")
    evidence = client.get(f"/api/projects/{pid}/evidence").json()
    for ev in evidence:
        response = client.patch(f"/api/projects/{pid}/evidence/{ev['evidence_id']}", json={"expected_revision": ev["revision"], "review_state": "confirmed", "responsible_person": "自动验收（仅官方参考）", "review_note": "仅确认参考夹具绑定与 927.2 m² 声明；不是实际工程师签署或实测校准。"})
        check(response.status_code == 200, "reference review " + ev["name"])
    runs = []
    for scheme in ["baseline", "R1", "R2"]:
        response = client.post("/api/runs", json={"project_id": pid, "scheme_id": scheme, "factor_profile_id": "reference_scenario"})
        check(response.status_code == 202, "submit " + scheme)
        rid = response.json()["run_id"]
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            result = client.get("/api/runs/" + rid + "/result").json()
            if result["status"] not in {"queued", "running"}:
                break
            time.sleep(.3)
        check(result["status"] == "succeeded", "native run succeeded " + scheme + ": " + str(result.get("error")))
        check(result["engine_calls_executed"] == 1, "actual engine call " + scheme)
        check(result["metrics"]["annual_days"] == 365, "annual coverage " + scheme)
        check(result["provenance"]["project_id"] == pid, "project provenance " + scheme)
        runs.append(result)
        print(scheme, rid, result["metrics"]["annual_energy_kwh"], flush=True)
    comparison = client.post("/api/comparisons", json={"run_ids": [r["run_id"] for r in runs]})
    check(comparison.status_code == 200, "three scheme comparison")
    check(comparison.json()["recommendation"] is None, "no unsupported optimal recommendation")
    rid = runs[0]["run_id"]
    report = client.get(f"/api/runs/{rid}/report.json").json()
    check(report["run"]["metrics"] == runs[0]["metrics"], "report and API same metrics")
    pdf = client.get(f"/api/runs/{rid}/report.pdf")
    check(pdf.status_code == 200 and pdf.content.startswith(b"%PDF"), "actual PDF generated")
    (out / "reference_report.pdf").write_bytes(pdf.content)
    (out / "reference_report.html").write_text(client.get(f"/api/runs/{rid}/report.html").text, encoding="utf-8")
    core.write_json(out / "reference_report.json", report)
    archive = client.get(f"/api/runs/{rid}/artifacts")
    check(archive.content.startswith(b"PK"), "replay evidence ZIP")
    (out / "reference_evidence.zip").write_bytes(archive.content)
    # Change a consumed evidence review; retain original record and reject stale comparison/report.
    ev = next(e for e in client.get(f"/api/projects/{pid}/evidence").json() if e["type"] == "idf" and e["scheme_id"] == "baseline")
    response = client.patch(f"/api/projects/{pid}/evidence/{ev['evidence_id']}", json={"expected_revision": ev["revision"], "review_state": "pending", "responsible_person": "自动验收", "review_note": "失效传播测试：撤回确认，保留之前版本"})
    check(response.status_code == 200, "evidence revised")
    stale = client.get(f"/api/runs/{rid}/result").json()
    check(stale["status"] == "stale" and stale["metrics"] is None and stale["carbon"] is None, "stale values suppressed")
    check(client.post("/api/comparisons", json={"run_ids": [r["run_id"] for r in runs]}).status_code == 409, "stale comparison refused")
    check(client.get(f"/api/runs/{rid}/report.json").json()["certificate"]["status"] == "STALE", "stale certificate draft")
    check(client.get('/api/runs/' + runs[1]["run_id"]).json()["status"] == "succeeded", "unrelated scheme remains valid")
    # A separate reference project deliberately declares the wrong positive area.
    # It must fail the engineering result gate even when EnergyPlus itself succeeds.
    wrong = client.post("/api/reference-projects").json()
    wrong_pid = wrong["project_id"]
    client.put(f"/api/projects/{wrong_pid}/building", json={"expected_revision": 1, "building": {**wrong["building"], "area_m2": 100}}).raise_for_status()
    for item in client.get(f"/api/projects/{wrong_pid}/evidence").json():
        client.patch(f"/api/projects/{wrong_pid}/evidence/{item['evidence_id']}", json={"expected_revision": 1, "review_state": "confirmed", "responsible_person": "自动负例测试", "review_note": "故意声明错误面积，验证仿真成功不等于工程核验成功"}).raise_for_status()
    rejected = client.post("/api/runs", json={"project_id": wrong_pid, "scheme_id": "baseline"})
    rejected.raise_for_status()
    wrong_rid = rejected.json()["run_id"]
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        rejected_view = client.get("/api/runs/" + wrong_rid).json()
        if rejected_view["status"] not in {"queued", "running"}:
            break
        time.sleep(.3)
    check(rejected_view["status"] == "failed" and rejected_view["metrics"] is None, "positive area mismatch suppresses real engine metrics")
    check(rejected_view["engine_calls_executed"] == 1 and "area" in rejected_view["error"], "area failure retains actual engine evidence")
    core.write_json(out / "golden_path.json", {"generated_at": core.now(), "project_id": pid, "runs_before_invalidation": runs, "comparison": comparison.json(), "stale_run": stale, "checks": checks, "limitations": ["Official reference only", "No field calibration", "2 sizing warnings per scheme", "No robustness proof", "Baseline intentionally stale after test"]})
    core.write_json(out / "area_failure.json", rejected_view)
print("Golden path checks:", len(checks), "passed", flush=True)
