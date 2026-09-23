"""Replay an evidence directory into a NEW run with the current matching engine."""
import argparse
import json
import sys
import uuid
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend import core

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path, help="Directory with manifest.json and archived input files")
    args = parser.parse_args()
    source = args.source.resolve()
    original, manifest, _ = core.read_validated(source, check_current=False)
    engine = core.engine_path()
    if core.sha(engine) != manifest["fingerprints"]["engine"]:
        raise SystemExit("Engine hash differs; replay refused")
    if core.sha(engine.parent / "Energy+.idd") != manifest["engine_idd_hash"]:
        raise SystemExit("IDD hash differs; replay refused")
    case = core.read_json(source / "input/case.json")
    scheme_id = manifest["scheme_id"]
    case["weather"] = "input/weather.epw"
    case["schemes"] = [{**core.get_scheme(case, scheme_id), "model": "input/model.idf"}]
    target = ROOT / "runtime/replays" / ("run_" + uuid.uuid4().hex)
    result = core.run_simulation(case["case_id"], scheme_id, manifest["factor_profile_id"], target,
        case_override=case, profile_override=core.read_json(source / "input/carbon_profile.json"), file_root=source)
    matched = result["status"] == "succeeded" and original.get("metrics") is not None and abs(result["metrics"]["annual_energy_kwh"] - original["metrics"]["annual_energy_kwh"]) < .01
    summary = {"source_run_id": manifest["run_id"], "replay_run_id": target.name,
               "status": result["status"], "energy_matches_within_0_01_kwh": matched,
               "source_code_hash": manifest["fingerprints"]["code"], "replay_code_hash": core.code_hash(),
               "scope": "Computational replay, not independent validation or current decision approval"}
    core.write_json(target / "replay_comparison.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not matched:
        raise SystemExit(1)

if __name__ == "__main__":
    main()
