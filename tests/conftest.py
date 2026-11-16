import os

os.environ["JWT_SECRET_KEY"] = "test-only-secret-key-not-for-production-use"

import mongomock
import pytest
from fastapi.testclient import TestClient

from backend.app import database
from backend.app.connection_manager import manager
from backend.app.main import app


@pytest.fixture(autouse=True)
def reset_connection_manager():
    manager.active_connections.clear()
    yield
    manager.active_connections.clear()


@pytest.fixture
def test_db(monkeypatch):
    fake_db = mongomock.MongoClient().socketroom_test
    monkeypatch.setattr(database, "db", fake_db)
    database.init_db()
    return fake_db


@pytest.fixture
def client(test_db):
    with TestClient(app) as test_client:
        yield test_client
