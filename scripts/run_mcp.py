"""Absolute-path MCP entry point, independent of the client's working directory."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.mcp_server import server

if __name__ == "__main__":
    server.run(transport="stdio")
