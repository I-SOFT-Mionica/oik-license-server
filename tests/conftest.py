import os

# Must be set before any app module is imported.
os.environ["JWT_SECRET"] = "test-secret-that-is-at-least-32-characters-long!!"

import pytest  # noqa: E402


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db_file = str(tmp_path / "test.db")
    monkeypatch.setenv("DB_PATH", db_file)
    from app.database import init_db
    init_db()
    return db_file


@pytest.fixture
def api_client(tmp_db):
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c
