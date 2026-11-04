import json
import sqlite3
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.api import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path / 'data', start_worker=False)
    with TestClient(app) as client:
        login = client.post('/api/auth/register', json={'username': 'test_owner', 'display_name': 'Test owner', 'password': 'Test-only-long-pass-2026'}).json()
        client.headers['X-CSRF-Token'] = login['csrf_token']
        yield client


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
