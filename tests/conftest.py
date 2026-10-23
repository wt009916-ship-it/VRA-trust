import pytest
from fastapi.testclient import TestClient

from backend.api import create_app


@pytest.fixture(autouse=True)
def legacy_test_registration(monkeypatch):
    # Existing isolation tests register multiple owners directly. Production defaults
    # to invitation mode; dedicated admission tests explicitly remove this override.
    monkeypatch.setenv('VRA_REGISTRATION_MODE', 'open')


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path / 'data', start_worker=False)
    with TestClient(app) as client:
        login = client.post('/api/auth/register', json={'username': 'test_owner', 'display_name': 'Test owner', 'password': 'Test-only-long-pass-2026'}).json()
        client.headers['X-CSRF-Token'] = login['csrf_token']
        yield client
