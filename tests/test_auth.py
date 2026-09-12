import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from src.api.main import app
from src.persistence.db import get_session
from src.persistence.models import Base

client = TestClient(app)


@pytest.fixture(autouse=True)
def _db_override():
    """GET "/" queries the AI system registry (Phase A), so it needs a real schema --
    the default app wiring points at ./dev.db, which won't exist/be migrated in CI."""
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)

    def override_get_session():
        session = Session(engine)
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_session] = override_get_session
    try:
        yield
    finally:
        app.dependency_overrides.clear()


def test_health_is_public(monkeypatch):
    monkeypatch.delenv("APP_USERNAME", raising=False)
    monkeypatch.delenv("APP_PASSWORD", raising=False)

    response = client.get("/health")

    assert response.status_code == 200


def test_assessment_form_requires_auth_when_unauthenticated(monkeypatch):
    monkeypatch.setenv("APP_USERNAME", "alice")
    monkeypatch.setenv("APP_PASSWORD", "secret")

    response = client.get("/")

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Basic"


def test_assessment_form_accepts_correct_credentials(monkeypatch):
    monkeypatch.setenv("APP_USERNAME", "alice")
    monkeypatch.setenv("APP_PASSWORD", "secret")

    response = client.get("/", auth=("alice", "secret"))

    assert response.status_code == 200


def test_assessment_form_rejects_wrong_password(monkeypatch):
    monkeypatch.setenv("APP_USERNAME", "alice")
    monkeypatch.setenv("APP_PASSWORD", "secret")

    response = client.get("/", auth=("alice", "wrong-password"))

    assert response.status_code == 401


def test_fails_closed_when_server_not_configured(monkeypatch):
    monkeypatch.delenv("APP_USERNAME", raising=False)
    monkeypatch.delenv("APP_PASSWORD", raising=False)

    response = client.get("/", auth=("anyone", "anything"))

    assert response.status_code == 500
