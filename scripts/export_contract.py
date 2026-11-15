"""Regenerate reviewed OpenAPI; CI checks for drift."""
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.api import app
from backend.schema import Building, Evidence, RunView
from backend.spatial import Reconstruction
from backend.trust import FactorUpdate
from backend.robustness import Search
from backend.thermal import Assembly
from backend.thermal_bridge import Section as ThermalBridgeSection
target = ROOT / "shared/schemas"
target.mkdir(parents=True, exist_ok=True)
for name, schema in [("openapi", app.openapi()), ("building", Building.model_json_schema()), ("evidence", Evidence.model_json_schema()), ("run", RunView.model_json_schema()), ("geometry", Reconstruction.model_json_schema()), ("factor-update", FactorUpdate.model_json_schema()), ("search", Search.model_json_schema()), ("thermal", Assembly.model_json_schema()), ("thermal-bridge", ThermalBridgeSection.model_json_schema())]:
    (target / (name + ".json")).write_text(json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
