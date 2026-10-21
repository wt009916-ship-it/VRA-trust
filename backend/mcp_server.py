"""stdio MCP adapter for Codex/Claude/Desktop and other MCP clients.

Run: python -m backend.mcp_server
Environment: VRA_BASE_URL, VRA_PROJECT_ID, VRA_API_TOKEN.
The adapter talks to the authenticated API; it never reads the application's DB.
"""
import os
import re
from typing import Literal
from urllib.parse import urlsplit

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

server = MCPServer("VRA-Trust", instructions=(
    "工程证据工具。不得把 AI 推断当成实测。模型编辑、参数复核和发布在 VRA 工作区完成。"
    "提交仿真前必须获得用户明确要求，结果必须检查 status、warnings 和 limitations。"))


def call(method, suffix, body=None):
    base = os.environ.get("VRA_BASE_URL", "http://127.0.0.1:8090").rstrip("/")
    parsed = urlsplit(base)
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path:
        raise ToolError("VRA_BASE_URL 必须是无凭据的服务根地址")
    if parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}):
        raise ToolError("远程连接必须使用 HTTPS")
    project = os.environ.get("VRA_PROJECT_ID", "")
    token = os.environ.get("VRA_API_TOKEN", "")
    if not re.fullmatch(r"project_[a-f0-9]{32}", project) or not token:
        raise ToolError("请在 MCP 配置中设置项目 ID 和专属 API Token")
    path = f"/api/projects/{project}" + suffix
    try:
        with httpx.Client(timeout=90, trust_env=False, follow_redirects=False) as client:
            response = client.request(method, base+path, json=body, headers={"Authorization": "Bearer "+token})
    except httpx.HTTPError:
        raise ToolError("无法连接 VRA 服务，请检查服务地址和运行状态") from None
    if response.status_code >= 400:
        raise ToolError(f"VRA API HTTP {response.status_code}: {response.json().get('detail', '请求失败')}")
    return response.json()


@server.tool()
def project_get() -> dict:
    """读取固定项目的声明。"""
    return call("GET", "")


@server.tool()
def building_model_get() -> dict:
    """读取空间模型、热工参数、证据和版本；缺失时返回 null 模型。"""
    return {"model": call("GET", "/model")}


@server.tool()
def building_model_validate() -> dict:
    """检查模型发布条件和理想负荷边界。"""
    return call("GET", "/model/validate")


@server.tool()
def evidence_list() -> list:
    """读取项目证据，不自动上传源文件到其他服务。"""
    return call("GET", "/evidence")


@server.tool()
def evidence_gate(scheme_id: Literal["baseline", "R1", "R2"] = "baseline") -> dict:
    """检查计算准入。"""
    return call("GET", "/gate?scheme_id="+scheme_id)


@server.tool()
def model_imports_list() -> list:
    """读取持久化导入任务、候选和人工复核状态。"""
    return call("GET", "/imports")


@server.tool()
def simulation_list() -> list:
    """读取核验后的计算结果和失败/失效原因。"""
    return call("GET", "/runs")


@server.tool()
def weather_summary() -> list:
    """读取天气分析与来源；日尺度数据不能作为 EnergyPlus 逐时天气。"""
    return call("GET", "/weather")


@server.tool()
def simulation_create(scheme_id: Literal["baseline", "R1", "R2"] = "baseline",
                      confirm_compute: bool = False) -> dict:
    """用户明确要求后提交实际 EnergyPlus；需具有 compute 权限的项目 Token。"""
    if not confirm_compute:
        return {"status": "USER_COMPUTE_CONFIRMATION_REQUIRED", "engine_calls_executed": 0}
    return call("POST", "/model-runs", {"scheme_id": scheme_id, "factor_profile_id": "none"})


if __name__ == "__main__":
    server.run(transport="stdio")
