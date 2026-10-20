"""Real stdio MCP -> authenticated local HTTP API acceptance. Synthetic projects only."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import sys

import httpx
from mcp import Client
from mcp.client.stdio import StdioServerParameters

ROOT = Path(__file__).resolve().parents[1]


async def verify(base, output):
    with httpx.Client(base_url=base, trust_env=False, timeout=20) as api:
        login = api.post("/api/auth/login", json={"username": "workbench_test", "password": "Synthetic-ui-test-2026-only"})
        login.raise_for_status()
        api.headers["X-CSRF-Token"] = login.json()["csrf_token"]
        response = api.post("/api/projects", json={"name": "MCP protocol acceptance · synthetic",
            "building": {"use": "office", "location": "Synthetic", "region": "US-CO", "area_m2": 80}})
        response.raise_for_status()
        pid = response.json()["project_id"]
        response = api.post(f"/api/projects/{pid}/tokens", json={"name": "MCP acceptance only", "days": 1, "scopes": ["read"]})
        response.raise_for_status()
        credential = response.json()
        parameters = StdioServerParameters(command=sys.executable, args=[str(ROOT/"scripts/run_mcp.py")], cwd=str(output.resolve().parent),
            env={**os.environ, "VRA_BASE_URL": base, "VRA_PROJECT_ID": pid, "VRA_API_TOKEN": credential["token"]})
        try:
            async with Client(parameters) as client:
                tools = await client.list_tools()
                names = [tool.name for tool in tools.tools]
                assert len(names) == 8 and "simulation_create" in names
                project = await client.call_tool("project_get", {})
                record = project.model_dump(mode="json")
                assert pid in json.dumps(record) and not project.is_error
                gate = await client.call_tool("evidence_gate", {})
                assert not gate.is_error and "MISSING_INPUT" in json.dumps(gate.model_dump())
                refused = await client.call_tool("simulation_create", {})
                assert "USER_COMPUTE_CONFIRMATION_REQUIRED" in json.dumps(refused.model_dump())
                forbidden = await client.call_tool("simulation_create", {"confirm_compute": True})
                assert forbidden.is_error and "403" in json.dumps(forbidden.model_dump())
                revoked = api.delete(f"/api/projects/{pid}/tokens/{credential['id']}")
                revoked.raise_for_status()
                after = await client.call_tool("project_get", {})
                assert after.is_error and "401" in json.dumps(after.model_dump())
                report = {"status": "passed", "transport": "real stdio process -> local HTTP API",
                          "tools": names, "project_id": pid, "checks": [
                              "MCP initialize and tool discovery", "project binding", "real evidence gate",
                              "compute opt-in", "read-token compute rejection", "revocation rejection"],
                          "engine_calls_executed": 0, "live_provider_tested": False}
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                print(json.dumps(report, ensure_ascii=False))
        finally:
            api.delete(f"/api/projects/{pid}/tokens/{credential['id']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8126")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.base not in {"http://127.0.0.1:8126", "http://localhost:8126"}:
        raise SystemExit("This script is limited to the isolated localhost acceptance service on port 8126.")
    asyncio.run(verify(args.base, args.output))
