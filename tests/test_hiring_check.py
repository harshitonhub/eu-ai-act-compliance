import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from src.api.dependencies import get_llm_client
from src.api.main import app
from src.api.rate_limit import public_rate_limiter
from src.legal.ingest import ingest_seed
from src.llm.fake_client import FakeCompletionProvider
from src.llm.interface import LLMClient
from src.persistence.db import get_session
from src.persistence.models import AssessmentRecord, Base

HIGH_RISK_RESPONSES = [
    '{"category": "prohibited_practices", "state": "NO", "cited_requirements": [], '
    '"rationale": "No prohibited practice indicators.", "confidence": 0.85}',
    '{"category": "high_risk", "state": "YES", '
    '"cited_requirements": [{"requirement_key": "EU-AI-ACT-ANNEXIII-4", "citation": "Annex III", '
    '"relevance": "recruitment"}], "rationale": "Matches Annex III point 4(a).", "confidence": 0.9}',
]


class _FakeLLMHolder:
    def __init__(self):
        self.responses: list[str] = []


@pytest.fixture
def public_client():
    public_rate_limiter.reset()
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as seed_session:
        ingest_seed(seed_session)

    def override_get_session():
        session = Session(engine)
        try:
            yield session
        finally:
            session.close()

    holder = _FakeLLMHolder()

    def override_get_llm_client():
        return LLMClient(FakeCompletionProvider(holder.responses), model="fake-model")

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_llm_client] = override_get_llm_client
    try:
        yield TestClient(app), holder, engine
    finally:
        app.dependency_overrides.clear()


def test_form_page_requires_no_auth(public_client):
    client, _holder, _engine = public_client

    response = client.get("/hiring-ai-check")

    assert response.status_code == 200
    assert "breaking EU law" in response.text


def test_check_returns_plain_answer_with_citation(public_client):
    client, holder, _engine = public_client
    holder.responses = list(HIGH_RISK_RESPONSES)

    response = client.post(
        "/hiring-ai-check",
        data={"description": "It scans resumes and ranks candidates by fit score before a recruiter reviews them."},
    )

    assert response.status_code == 200
    assert "High-risk check" in response.text
    assert "EU-AI-ACT-ANNEXIII-4" in response.text
    assert "90% confidence" in response.text
    assert "full assessment" in response.text  # points toward the full flow for obligations


def test_check_does_not_persist_an_assessment_record(public_client):
    client, holder, engine = public_client
    holder.responses = list(HIGH_RISK_RESPONSES)

    client.post("/hiring-ai-check", data={"description": "A resume screening tool."})

    with Session(engine) as verify_session:
        assert verify_session.query(AssessmentRecord).count() == 0


def test_public_rate_limit_is_stricter_than_authenticated_endpoints(public_client):
    client, holder, _engine = public_client
    holder.responses = HIGH_RISK_RESPONSES * 5

    responses = [client.post("/hiring-ai-check", data={"description": "A resume tool."}) for _ in range(4)]

    assert [r.status_code for r in responses] == [200, 200, 200, 429]
