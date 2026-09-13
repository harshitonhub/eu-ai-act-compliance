"""Cross-tenant isolation over real HTTP -- the IDOR case.

tests/test_tenant_isolation.py proves the ORM layer holds. This proves the same thing
through the actual web stack, with two genuinely logged-in users, because that is the
shape the attack really takes: not a crafted query, but tenant B pasting a URL that
belongs to tenant A. Every id in this app appears in a URL somewhere
(/systems/{id}, /assessments/{id}, /incidents/{id}/mark-reported), so "the id is an
unguessable UUID" is not the control -- it is shared in links, logs, and screenshots.
"""

import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from schemas.enums import UserRole
from src.api.dependencies import get_llm_client
from src.api.main import app
from src.api.rate_limit import login_rate_limiter, rate_limiter
from src.auth.users import create_tenant, create_user
from src.legal.ingest import ingest_seed
from src.llm.fake_client import FakeCompletionProvider
from src.llm.interface import LLMClient
from src.persistence.db import get_session
from src.persistence.models import Base

PASSWORD = "correct-horse-battery-staple"

CLASSIFICATION_RESPONSES = [
    '{"category": "prohibited_practices", "state": "NO", "cited_requirements": [], '
    '"rationale": "none", "confidence": 0.9}',
    '{"category": "high_risk", "state": "YES", '
    '"cited_requirements": [{"requirement_key": "EU-AI-ACT-ANNEXIII-4", "citation": "Annex III", '
    '"relevance": "recruitment"}], "rationale": "Annex III point 4.", "confidence": 0.9}',
]


class _Holder:
    def __init__(self):
        self.responses: list[str] = []


@pytest.fixture
def two_tenant_app(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret")
    rate_limiter.reset()
    login_rate_limiter.reset()

    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as setup:
        ingest_seed(setup)
        for label in ("alpha", "bravo"):
            tenant = create_tenant(setup, f"{label.title()} Ltd")
            create_user(
                setup, tenant_id=tenant.id, email=f"{label}@test.example",
                password=PASSWORD, role=UserRole.MEMBER,
            )

    def override_get_session():
        s = Session(engine)
        try:
            yield s
        finally:
            s.close()

    holder = _Holder()
    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_llm_client] = lambda: LLMClient(
        FakeCompletionProvider(holder.responses), model="fake-model"
    )
    try:
        yield holder
    finally:
        app.dependency_overrides.clear()


def _client_for(label: str) -> TestClient:
    client = TestClient(app)
    response = client.post(
        "/login", data={"email": f"{label}@test.example", "password": PASSWORD},
        follow_redirects=False,
    )
    assert response.status_code == 303
    return client


def _create_full_assessment(client: TestClient, holder: _Holder, system_name: str) -> dict[str, str]:
    """Drive the real form flow, returning the ids that end up in URLs."""
    holder.responses = list(CLASSIFICATION_RESPONSES)
    assess = client.post(
        "/assess",
        data={
            "ai_system_name": system_name,
            "system_description": f"{system_name} screens job applicants.",
            "intended_purpose": "Recruitment.",
            "actor_role": "deployer",
            "sector": "",
            "as_of": "2026-09-09",
        },
    )
    assert assess.status_code == 200

    def hidden(name: str) -> str:
        import html as html_mod

        match = re.search(rf"name=\"{name}\" value=['\"](.*?)['\"]", assess.text, re.DOTALL)
        assert match, name
        return html_mod.unescape(match.group(1))

    holder.responses = []
    report = client.post(
        "/report",
        data={
            "facts_json": hidden("facts_json"),
            "classification_json": hidden("classification_json"),
            "classification_llm_calls_json": hidden("classification_llm_calls_json"),
            "as_of": hidden("as_of"),
            "ai_system_name": system_name,
        },
    )
    assert report.status_code == 200
    assessment_id = re.search(r"Assessment ID:</strong>\s*<code>(.*?)</code>", report.text).group(1)

    system_id = re.search(r'/systems/([\w-]+)', client.get("/history").text).group(1)

    incident = client.post(
        f"/systems/{system_id}/incidents",
        data={
            "severity": "critical_infrastructure_disruption",
            "description": f"{system_name} incident",
            "detected_at": "2026-09-01",
        },
        follow_redirects=True,
    )
    incident_id = re.search(r'/incidents/([\w-]+)/mark-reported', incident.text).group(1)

    return {"system_id": system_id, "assessment_id": assessment_id, "incident_id": incident_id}


def test_each_tenant_sees_only_its_own_history(two_tenant_app):
    holder = two_tenant_app
    alpha, bravo = _client_for("alpha"), _client_for("bravo")
    _create_full_assessment(alpha, holder, "Alpha Screener")
    _create_full_assessment(bravo, holder, "Bravo Screener")

    alpha_history = alpha.get("/history").text
    bravo_history = bravo.get("/history").text

    assert "Alpha Screener" in alpha_history and "Bravo Screener" not in alpha_history
    assert "Bravo Screener" in bravo_history and "Alpha Screener" not in bravo_history


def test_tenant_cannot_open_another_tenants_system_page(two_tenant_app):
    holder = two_tenant_app
    alpha, bravo = _client_for("alpha"), _client_for("bravo")
    alpha_ids = _create_full_assessment(alpha, holder, "Alpha Screener")

    response = bravo.get(f"/systems/{alpha_ids['system_id']}")

    assert response.status_code == 404
    assert "Alpha Screener" not in response.text


def test_tenant_cannot_open_another_tenants_assessment(two_tenant_app):
    holder = two_tenant_app
    alpha, bravo = _client_for("alpha"), _client_for("bravo")
    alpha_ids = _create_full_assessment(alpha, holder, "Alpha Screener")

    assert bravo.get(f"/assessments/{alpha_ids['assessment_id']}").status_code == 404


def test_tenant_cannot_export_another_tenants_impact_assessment(two_tenant_app):
    holder = two_tenant_app
    alpha, bravo = _client_for("alpha"), _client_for("bravo")
    alpha_ids = _create_full_assessment(alpha, holder, "Alpha Screener")

    response = bravo.get(f"/assessments/{alpha_ids['assessment_id']}/impact-assessment")

    assert response.status_code == 404


def test_tenant_cannot_log_an_incident_against_another_tenants_system(two_tenant_app):
    holder = two_tenant_app
    alpha, bravo = _client_for("alpha"), _client_for("bravo")
    alpha_ids = _create_full_assessment(alpha, holder, "Alpha Screener")

    response = bravo.post(
        f"/systems/{alpha_ids['system_id']}/incidents",
        data={
            "severity": "widespread_infringement",
            "description": "planted by the wrong tenant",
            "detected_at": "2026-09-01",
        },
    )

    assert response.status_code == 404
    # And nothing was written: Alpha still sees only its own incident.
    alpha_page = alpha.get(f"/systems/{alpha_ids['system_id']}").text
    assert "planted by the wrong tenant" not in alpha_page


def test_tenant_cannot_resolve_another_tenants_incident(two_tenant_app):
    holder = two_tenant_app
    alpha, bravo = _client_for("alpha"), _client_for("bravo")
    alpha_ids = _create_full_assessment(alpha, holder, "Alpha Screener")

    response = bravo.post(f"/incidents/{alpha_ids['incident_id']}/mark-reported")

    assert response.status_code == 404
    # Alpha's incident is still open -- the button is still on the page.
    assert "Mark reported" in alpha.get(f"/systems/{alpha_ids['system_id']}").text


def test_deadlines_dashboard_does_not_span_tenants(two_tenant_app):
    holder = two_tenant_app
    alpha, bravo = _client_for("alpha"), _client_for("bravo")
    _create_full_assessment(alpha, holder, "Alpha Screener")
    _create_full_assessment(bravo, holder, "Bravo Screener")

    assert "Bravo Screener" not in alpha.get("/deadlines").text
    assert "Alpha Screener" not in bravo.get("/deadlines").text


def test_two_tenants_may_reuse_the_same_system_name_without_collision(two_tenant_app):
    """get_or_create_ai_system matches on exact name. Scoped per tenant, "Resume Screener"
    in one tenant must not be silently reused by another -- that would be a leak dressed
    up as a convenience feature."""
    holder = two_tenant_app
    alpha, bravo = _client_for("alpha"), _client_for("bravo")

    alpha_ids = _create_full_assessment(alpha, holder, "Resume Screener")
    bravo_ids = _create_full_assessment(bravo, holder, "Resume Screener")

    assert alpha_ids["system_id"] != bravo_ids["system_id"]
    assert "1 assessment" in alpha.get("/history").text
    assert "1 assessment" in bravo.get("/history").text
