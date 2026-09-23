"""Native SQL projection fixture is test-only; it is never a production result fallback."""
import json
import sqlite3
from pathlib import Path
import pytest
from backend import core
from backend.schema import RunView


@pytest.fixture
def native_sql(tmp_path):
    fixture = json.loads((Path(__file__).resolve().parents[1] / "fixtures/test/native_annual_projection.json").read_text())
    path = tmp_path / "native.sql"
    with sqlite3.connect(path) as con:
        for table, data in fixture["tables"].items():
            columns = data["columns"]
            # Identifiers come from a reviewed repository fixture, never request input.
            con.execute('CREATE TABLE "' + table + '" (' + ','.join('"' + c + '"' for c in columns) + ')')
            con.executemany('INSERT INTO "' + table + '" VALUES (' + ','.join('?' for _ in columns) + ')', data["rows"])
    return path


def test_native_sql_to_result_schema(native_sql):
    metrics = core.parse_sql(native_sql)
    assert metrics["annual_energy_kwh"] == pytest.approx(57193.23)
    assert metrics["area_m2"] == pytest.approx(927.2)
    assert metrics["annual_days"] == 365
    view = RunView(run_id="test_fixture", project_id="fixture", case_id="fixture", scheme_id="baseline", status="succeeded",
                   data_nature="TEST_ONLY", created_at="fixture", metrics=metrics)
    assert view.model_dump()["metrics"]["locators"]["total_energy"]["unit"] == "kWh"


@pytest.mark.parametrize("mutation", [
    "UPDATE Simulations SET CompletedSuccessfully=0",
    "DELETE FROM Time WHERE Month=12",
    "UPDATE TabularDataWithStrings SET Units='m3' WHERE TableName='Building Area'",
    "UPDATE TabularDataWithStrings SET Units='unsupported' WHERE TableName='Site and Source Energy'",
    "INSERT INTO Simulations SELECT * FROM Simulations",
    "UPDATE TabularDataWithStrings SET Value='0' WHERE TableName='Building Area' AND RowName='Total Building Area'",
])
def test_native_failure_never_publishes_metrics(native_sql, mutation):
    with sqlite3.connect(native_sql) as con:
        con.execute(mutation)
    with pytest.raises(core.ValidationError):
        core.parse_sql(native_sql)
