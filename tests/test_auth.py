"""Session-cookie auth, password hashing, and role gating.

Replaces the HTTP Basic tests from Phase 6 -- that scheme is gone, along with
APP_USERNAME/APP_PASSWORD.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from schemas.enums import UserRole
from src.api.main import app
from src.api.rate_limit import login_rate_limiter
from src.auth.passwords import hash_password, verify_password
from src.auth.sessions import COOKIE_NAME, issue_session, read_session
from src.auth.users import authenticate, create_tenant, create_user
from src.persistence.db import get_session
from src.persistence.models import Base

PASSWORD = "correct-horse-battery-staple"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-not-used-in-production")
    login_rate_limiter.reset()  # module-level state, would bleed across tests
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as setup:
        tenant = create_tenant(setup, "Acme")
        for role in UserRole:
            create_user(
                setup, tenant_id=tenant.id, email=f"{role.value}@acme.test",
                password=PASSWORD, role=role,
            )

    def override_get_session():
        s = Session(engine)
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_session] = override_get_session
    try:
        test_client = TestClient(app)
        test_client.engine = engine  # for the few tests that need direct DB access
        yield test_client
    finally:
        app.dependency_overrides.clear()


def _login(client: TestClient, role: UserRole) -> None:
    response = client.post(
        "/login", data={"email": f"{role.value}@acme.test", "password": PASSWORD}
    )
    assert response.status_code in (200, 303)


# --- password hashing -------------------------------------------------------------

def test_password_roundtrip():
    stored = hash_password(PASSWORD)
    assert verify_password(PASSWORD, stored)
    assert not verify_password("wrong", stored)


def test_password_hash_is_salted_so_equal_passwords_differ():
    assert hash_password(PASSWORD) != hash_password(PASSWORD)


def test_stored_hash_never_contains_the_password():
    assert PASSWORD not in hash_password(PASSWORD)


def test_verify_rejects_malformed_stored_value_instead_of_raising():
    for junk in ["", "not-a-hash", "pbkdf2_sha256$nope$aa$bb", "a$b$c$d"]:
        assert verify_password(PASSWORD, junk) is False


# --- session cookies --------------------------------------------------------------

def test_session_roundtrip(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "s3cret")
    assert read_session(issue_session("user-123")) == "user-123"


def test_tampered_session_is_rejected(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "s3cret")
    import base64

    token = base64.urlsafe_b64decode(issue_session("user-123")).decode()
    user_id, expiry, tag = token.rsplit("|", 2)
    forged = base64.urlsafe_b64encode(f"someone-else|{expiry}|{tag}".encode()).decode()

    assert read_session(forged) is None


def test_session_signed_with_a_different_secret_is_rejected(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "secret-a")
    cookie = issue_session("user-123")
    monkeypatch.setenv("SESSION_SECRET", "secret-b")

    assert read_session(cookie) is None


def test_expired_session_is_rejected(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "s3cret")
    assert read_session(issue_session("user-123", max_age_seconds=-1)) is None


def test_garbage_cookie_is_rejected(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "s3cret")
    for junk in [None, "", "!!!not-base64!!!", "YWJj"]:
        assert read_session(junk) is None


# --- authentication ---------------------------------------------------------------

def test_authenticate_accepts_correct_password(client):
    with Session(client.engine) as s:
        assert authenticate(s, "admin@acme.test", PASSWORD) is not None
        assert authenticate(s, "admin@acme.test", "wrong") is None
        assert authenticate(s, "nobody@acme.test", PASSWORD) is None


def test_authenticate_is_case_insensitive_on_email(client):
    response = client.post(
        "/login", data={"email": "ADMIN@ACME.TEST", "password": PASSWORD}, follow_redirects=False
    )
    assert response.status_code == 303


def test_login_with_wrong_password_returns_401_and_no_cookie(client):
    response = client.post("/login", data={"email": "admin@acme.test", "password": "nope"})

    assert response.status_code == 401
    assert COOKIE_NAME not in response.cookies


def test_unknown_and_wrong_password_give_the_same_message(client):
    wrong = client.post("/login", data={"email": "admin@acme.test", "password": "nope"})
    unknown = client.post("/login", data={"email": "ghost@acme.test", "password": "nope"})

    assert wrong.status_code == unknown.status_code == 401
    assert "Incorrect email or password" in wrong.text
    assert "Incorrect email or password" in unknown.text


# --- route protection -------------------------------------------------------------

def test_health_is_public(client):
    assert client.get("/health").status_code == 200


def test_protected_route_redirects_anonymous_user_to_login(client):
    response = client.get("/", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_protected_route_allows_logged_in_user(client):
    _login(client, UserRole.ADMIN)

    assert client.get("/").status_code == 200


def test_logout_clears_the_session(client):
    _login(client, UserRole.ADMIN)
    assert client.get("/").status_code == 200

    client.post("/logout")

    assert client.get("/", follow_redirects=False).status_code == 303


def test_forged_cookie_does_not_grant_access(client):
    client.cookies.set(COOKIE_NAME, "obviously-forged")

    assert client.get("/", follow_redirects=False).status_code == 303


# --- role gating ------------------------------------------------------------------

def test_viewer_can_read(client):
    _login(client, UserRole.VIEWER)

    assert client.get("/").status_code == 200
    assert client.get("/history").status_code == 200


def test_viewer_cannot_write(client):
    _login(client, UserRole.VIEWER)

    response = client.post(
        "/assess",
        data={
            "system_description": "x", "intended_purpose": "x",
            "actor_role": "", "sector": "", "as_of": "2026-09-09",
        },
    )

    assert response.status_code == 403


@pytest.mark.parametrize("role", [UserRole.ADMIN, UserRole.MEMBER])
def test_writers_are_not_blocked_by_the_role_gate(client, role):
    """Not asserting success -- /assess needs an LLM client this fixture doesn't provide.
    Asserting only that the *role* check passed, i.e. the failure isn't a 403."""
    _login(client, role)

    response = client.post(
        "/assess",
        data={
            "system_description": "x", "intended_purpose": "x",
            "actor_role": "", "sector": "", "as_of": "2026-09-09",
        },
    )

    assert response.status_code != 403
