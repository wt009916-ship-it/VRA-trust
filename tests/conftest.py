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
