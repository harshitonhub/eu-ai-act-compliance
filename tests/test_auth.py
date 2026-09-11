from fastapi.testclient import TestClient

from src.api.main import app

client = TestClient(app)


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
