"""Phase 5 DoD: a user can submit a system description + evidence through the web form
and receive a report with citations, gaps, and review flags, end-to-end.

Drives the real FastAPI app via TestClient, overriding only the DB session (in-memory,
seeded) and the LLM client (fake, programmed) -- the same override mechanism a real
browser session would never see; everything else (routing, templates, hidden-field
round-tripping, form parsing) is exercised exactly as production would run it.
"""

import html
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
from src.legal.versioning import supersede_requirement
from src.llm.fake_client import FakeCompletionProvider
from src.llm.interface import LLMClient
from src.observability.assessment_log import reconstruct_assessment
from src.persistence.db import get_session
from src.persistence.models import Base, Requirement
from src.persistence.tenancy import bind_tenant
from schemas.classification import ClassificationResult

HIGH_RISK_CLASSIFICATION_RESPONSES = [
    '{"category": "prohibited_practices", "state": "NO", "cited_requirements": [], '
    '"rationale": "No prohibited practice indicators.", "confidence": 0.85}',
    '{"category": "high_risk", "state": "YES", '
    '"cited_requirements": [{"requirement_key": "EU-AI-ACT-ANNEXIII-4", "citation": "Annex III", '
    '"relevance": "recruitment"}], "rationale": "Matches Annex III point 4(a).", "confidence": 0.9}',
]

NON_COMPLIANT_EVIDENCE_RESPONSE = (
    '{"requirement_key": "EU-AI-ACT-ART9", "status": "NON_COMPLIANT", "dimensions": ['
    '{"dimension": "relevance", "met": false, "note": "Not specific."},'
    '{"dimension": "completeness", "met": false, "note": "Missing sections."},'
    '{"dimension": "specificity", "met": false, "note": "Too generic."},'
    '{"dimension": "currency", "met": true, "note": "Recent."},'
    '{"dimension": "traceability", "met": false, "note": "No owner named."},'
    '{"dimension": "consistency", "met": true, "note": "No conflicts found."},'
    '{"dimension": "sufficiency", "met": false, "note": "Insufficient detail."}'
    '], "rationale": "Policy is generic and lacks specificity.", "contradictions": []}'
)


class _FakeLLMHolder:
    def __init__(self):
        self.responses: list[str] = []


TEST_PASSWORD = "correct-horse-battery-staple"


@pytest.fixture
def web_client(monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-secret-not-used-in-production")
    rate_limiter.reset()  # each test gets a fresh rate-limit window, not the module-shared one
    login_rate_limiter.reset()

    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as seed_session:
        ingest_seed(seed_session)  # legal corpus: not tenant-owned, so needs no tenant
        tenant = create_tenant(seed_session, "Test Tenant")
        tenant_id = tenant.id  # read before the session closes and detaches the instance
        create_user(
            seed_session, tenant_id=tenant_id, email="user@test.example",
            password=TEST_PASSWORD, role=UserRole.MEMBER,
        )

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
        client = TestClient(app)
        login = client.post(
            "/login", data={"email": "user@test.example", "password": TEST_PASSWORD},
            follow_redirects=False,
        )
        assert login.status_code == 303, "fixture could not log in"
        # Direct-DB assertions need a tenant to bind; the app binds its own per request.
        client.tenant_id = tenant_id
        yield client, holder, engine
    finally:
        app.dependency_overrides.clear()


def _extract_hidden_value(name: str, html_text: str) -> str:
    match = re.search(rf"name=\"{name}\" value=['\"](.*?)['\"]", html_text, re.DOTALL)
    assert match, f"hidden field {name!r} not found in response HTML"
    return html.unescape(match.group(1))


def _extract_assessment_id(html_text: str) -> str:
    match = re.search(r"Assessment ID.*?<code>(.*?)</code>", html_text, re.DOTALL)
    assert match, "assessment ID not found in report HTML"
    return html.unescape(match.group(1))


def test_full_web_flow_facts_to_report_with_citations_gaps_and_review_flags(web_client):
    client, holder, engine = web_client

    form_page = client.get("/")
    assert form_page.status_code == 200
    assert "System description" in form_page.text

    holder.responses = list(HIGH_RISK_CLASSIFICATION_RESPONSES)
    assess_response = client.post(
        "/assess",
        data={
            "system_description": "An AI tool that screens and ranks job applicant resumes for an employer.",
            "intended_purpose": "Recruitment and candidate evaluation for employers.",
            "actor_role": "deployer",
            "sector": "",
            "as_of": "2026-09-09",
        },
    )
    assert assess_response.status_code == 200
    obligations_html = assess_response.text
    assert "EU-AI-ACT-ANNEXIII-4" in obligations_html  # the classification's citation is shown
    assert "EU-AI-ACT-ART9" in obligations_html  # obligation triggered by high_risk=YES

    facts_json = _extract_hidden_value("facts_json", obligations_html)
    classification_json = _extract_hidden_value("classification_json", obligations_html)
    classification_llm_calls_json = _extract_hidden_value("classification_llm_calls_json", obligations_html)
    as_of_value = _extract_hidden_value("as_of", obligations_html)

    holder.responses = [NON_COMPLIANT_EVIDENCE_RESPONSE]
    report_response = client.post(
        "/report",
        data={
            "facts_json": facts_json,
            "classification_json": classification_json,
            "classification_llm_calls_json": classification_llm_calls_json,
            "as_of": as_of_value,
            "evidence__EU-AI-ACT-ART9": "Generic risk policy: we manage risk appropriately.",
            # ART10-15 and GDPR-ART22/35 deliberately left blank -> INSUFFICIENT_EVIDENCE, zero LLM calls for them
        },
    )
    assert report_response.status_code == 200
    report_html = report_response.text

    assert "EU-AI-ACT-ANNEXIII-4" in report_html  # classification citation carried through
    assert "EU-AI-ACT-ART9" in report_html  # obligation + evidence status shown
    assert "NON_COMPLIANT" in report_html  # evidence status
    assert "Gaps (9)" in report_html  # all 9 obligations are gaps (1 non-compliant + 8 insufficient)
    assert "high_impact_high_risk" in report_html  # review flag for high_risk=YES
    assert "evidence_gap" in report_html  # review flag for the non-compliant/insufficient obligations
    assert "GOVERN 1.4" in report_html  # NIST AI RMF crosswalk shown alongside EU-AI-ACT-ART9

    # Phase 6 DoD: the assessment just produced is fully reconstructable from stored data.
    assessment_id = _extract_assessment_id(report_html)
    with Session(engine) as verify_session:
        bind_tenant(verify_session, client.tenant_id)
        reconstructed = reconstruct_assessment(verify_session, assessment_id)
    assert reconstructed is not None
    assert reconstructed.classification == ClassificationResult.model_validate_json(classification_json)
    assert len(reconstructed.obligations) == 9
    assert len(reconstructed.evidence_assessments) == 9
    assert len(reconstructed.gaps) == 9
    assert len(reconstructed.review_flags) >= 2
    assert len(reconstructed.llm_calls) == 3  # 2 classification calls + 1 evidence call
    assert reconstructed.total_input_tokens > 0
    assert reconstructed.error is None


def test_uploaded_file_takes_precedence_over_pasted_text(web_client):
    client, holder, _engine = web_client

    holder.responses = list(HIGH_RISK_CLASSIFICATION_RESPONSES)
    assess_response = client.post(
        "/assess",
        data={
            "system_description": "An AI tool that screens and ranks job applicant resumes for an employer.",
            "intended_purpose": "Recruitment and candidate evaluation for employers.",
            "actor_role": "deployer",
            "sector": "",
            "as_of": "2026-09-09",
        },
    )
    obligations_html = assess_response.text
    facts_json = _extract_hidden_value("facts_json", obligations_html)
    classification_json = _extract_hidden_value("classification_json", obligations_html)
    classification_llm_calls_json = _extract_hidden_value("classification_llm_calls_json", obligations_html)
    as_of_value = _extract_hidden_value("as_of", obligations_html)

    compliant_response = (
        '{"requirement_key": "EU-AI-ACT-ART9", "status": "COMPLIANT", "dimensions": ['
        '{"dimension": "relevance", "met": true, "note": "ok"},'
        '{"dimension": "completeness", "met": true, "note": "ok"},'
        '{"dimension": "specificity", "met": true, "note": "ok"},'
        '{"dimension": "currency", "met": true, "note": "ok"},'
        '{"dimension": "traceability", "met": true, "note": "ok"},'
        '{"dimension": "consistency", "met": true, "note": "ok"},'
        '{"dimension": "sufficiency", "met": true, "note": "ok"}'
        '], "rationale": "Uploaded policy file is thorough.", "contradictions": []}'
    )
    holder.responses = [compliant_response]
    report_response = client.post(
        "/report",
        data={
            "facts_json": facts_json,
            "classification_json": classification_json,
            "classification_llm_calls_json": classification_llm_calls_json,
            "as_of": as_of_value,
            "evidence__EU-AI-ACT-ART9": "this text should be ignored because a file is also uploaded",
        },
        files={"evidence_file__EU-AI-ACT-ART9": ("policy.txt", b"Our thorough risk management policy...", "text/plain")},
    )

    assert report_response.status_code == 200
    assert "COMPLIANT" in report_response.text
    assert "File upload errors" not in report_response.text


def test_invalid_file_upload_surfaces_error_and_falls_back_to_insufficient_evidence(web_client):
    client, holder, _engine = web_client

    holder.responses = list(HIGH_RISK_CLASSIFICATION_RESPONSES)
    assess_response = client.post(
        "/assess",
        data={
            "system_description": "An AI tool that screens and ranks job applicant resumes for an employer.",
            "intended_purpose": "Recruitment and candidate evaluation for employers.",
            "actor_role": "deployer",
            "sector": "",
            "as_of": "2026-09-09",
        },
    )
    obligations_html = assess_response.text
    facts_json = _extract_hidden_value("facts_json", obligations_html)
    classification_json = _extract_hidden_value("classification_json", obligations_html)
    classification_llm_calls_json = _extract_hidden_value("classification_llm_calls_json", obligations_html)
    as_of_value = _extract_hidden_value("as_of", obligations_html)

    holder.responses = []  # no evidence LLM call expected: the file is rejected before assessment
    report_response = client.post(
        "/report",
        data={
            "facts_json": facts_json,
            "classification_json": classification_json,
            "classification_llm_calls_json": classification_llm_calls_json,
            "as_of": as_of_value,
        },
        files={"evidence_file__EU-AI-ACT-ART9": ("malware.exe", b"not a real policy", "application/octet-stream")},
    )

    assert report_response.status_code == 200
    report_html = report_response.text
    assert "File upload errors" in report_html
    assert "not allowed" in report_html
    assert "INSUFFICIENT_EVIDENCE" in report_html


def test_no_high_risk_no_prohibited_yields_no_obligations_and_no_review(web_client):
    client, holder, _engine = web_client

    holder.responses = [
        '{"category": "prohibited_practices", "state": "NO", "cited_requirements": [], '
        '"rationale": "No indicators.", "confidence": 0.9}',
        '{"category": "high_risk", "state": "NO", "cited_requirements": [], '
        '"rationale": "No Annex III match.", "confidence": 0.9}',
    ]
    assess_response = client.post(
        "/assess",
        data={
            "system_description": "A customer service chatbot for order status inquiries.",
            "intended_purpose": "Automate routine customer support.",
            "actor_role": "",
            "sector": "",
            "as_of": "2026-09-09",
        },
    )
    assert "No obligations triggered" in assess_response.text

    facts_json = _extract_hidden_value("facts_json", assess_response.text)
    classification_json = _extract_hidden_value("classification_json", assess_response.text)
    classification_llm_calls_json = _extract_hidden_value("classification_llm_calls_json", assess_response.text)
    as_of_value = _extract_hidden_value("as_of", assess_response.text)

    holder.responses = []
    report_response = client.post(
        "/report",
        data={
            "facts_json": facts_json,
            "classification_json": classification_json,
            "classification_llm_calls_json": classification_llm_calls_json,
            "as_of": as_of_value,
        },
    )

    assert "No obligations apply" in report_response.text
    assert "No gaps identified" in report_response.text
    # scope/gpai/transparency have no ingested legal corpus (see docs/legal-methodology.md),
    # so they always resolve INSUFFICIENT_INFORMATION and always trigger review -- this is
    # correct, honest behavior, not a bug: an assessment ungrounded for 3 of 5 categories
    # should always be flagged, not silently treated as "clean."
    assert "insufficient_information" in report_response.text
    assert "No review flags raised" not in report_response.text


def test_rate_limit_blocks_excessive_requests_to_assess(web_client, monkeypatch):
    client, holder, _engine = web_client
    monkeypatch.setattr(rate_limiter, "max_requests", 2)

    payload = {
        "system_description": "A customer service chatbot for order status inquiries.",
        "intended_purpose": "Automate routine customer support.",
        "actor_role": "",
        "sector": "",
        "as_of": "2026-09-09",
    }
    holder.responses = [
        '{"category": "prohibited_practices", "state": "NO", "cited_requirements": [], "rationale": "x", "confidence": 0.9}',
        '{"category": "high_risk", "state": "NO", "cited_requirements": [], "rationale": "x", "confidence": 0.9}',
    ] * 2

    first = client.post("/assess", data=payload)
    second = client.post("/assess", data=payload)
    third = client.post("/assess", data=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429


def test_history_lists_past_assessments_and_links_to_report(web_client):
    client, holder, _engine = web_client

    assert "No AI systems assessed yet" in client.get("/history").text

    holder.responses = list(HIGH_RISK_CLASSIFICATION_RESPONSES)
    assess_response = client.post(
        "/assess",
        data={
            "system_description": "An AI tool that screens and ranks job applicant resumes for an employer.",
            "intended_purpose": "Recruitment and candidate evaluation for employers.",
            "actor_role": "deployer",
            "sector": "",
            "as_of": "2026-09-09",
        },
    )
    facts_json = _extract_hidden_value("facts_json", assess_response.text)
    classification_json = _extract_hidden_value("classification_json", assess_response.text)
    classification_llm_calls_json = _extract_hidden_value("classification_llm_calls_json", assess_response.text)
    as_of_value = _extract_hidden_value("as_of", assess_response.text)

    holder.responses = []
    client.post(
        "/report",
        data={
            "facts_json": facts_json,
            "classification_json": classification_json,
            "classification_llm_calls_json": classification_llm_calls_json,
            "as_of": as_of_value,
        },
    )

    history_html = client.get("/history").text
    assert "recruitment" in history_html.lower() or "job applicant" in history_html.lower()
    assert "Review needed" in history_html  # high_risk=YES triggers a review flag

    link_match = re.search(r'/assessments/([\w-]+)', history_html)
    assert link_match, "no assessment link found in history page"
    assessment_id = link_match.group(1)

    past_report = client.get(f"/assessments/{assessment_id}")
    assert past_report.status_code == 200
    assert "Compliance report" in past_report.text
    assert "EU-AI-ACT-ANNEXIII-4" in past_report.text


def test_view_unknown_assessment_returns_404(web_client):
    client, _holder, _engine = web_client

    response = client.get("/assessments/does-not-exist")

    assert response.status_code == 404


def test_named_ai_system_groups_assessments_on_history_and_has_own_detail_page(web_client):
    client, holder, _engine = web_client

    holder.responses = list(HIGH_RISK_CLASSIFICATION_RESPONSES)
    assess_response = client.post(
        "/assess",
        data={
            "ai_system_name": "Resume Screener",
            "system_description": "An AI tool that screens and ranks job applicant resumes for an employer.",
            "intended_purpose": "Recruitment and candidate evaluation for employers.",
            "actor_role": "deployer",
            "sector": "",
            "as_of": "2026-09-09",
        },
    )
    assert 'name="ai_system_name" value="Resume Screener"' in assess_response.text

    holder.responses = []
    client.post(
        "/report",
        data={
            "facts_json": _extract_hidden_value("facts_json", assess_response.text),
            "classification_json": _extract_hidden_value("classification_json", assess_response.text),
            "classification_llm_calls_json": _extract_hidden_value(
                "classification_llm_calls_json", assess_response.text
            ),
            "as_of": _extract_hidden_value("as_of", assess_response.text),
            "ai_system_name": "Resume Screener",
        },
    )

    history_html = client.get("/history").text
    assert "Resume Screener" in history_html
    assert "Ungrouped" not in history_html  # nothing ungrouped yet

    system_link_match = re.search(r'/systems/([\w-]+)', history_html)
    assert system_link_match, "no AI system link found in history page"
    system_id = system_link_match.group(1)

    detail_response = client.get(f"/systems/{system_id}")
    assert detail_response.status_code == 200
    assert "Resume Screener" in detail_response.text
    assert "Assessment history (1)" in detail_response.text

    # A second assessment for the same system (by name) lands on the same detail page.
    holder.responses = list(HIGH_RISK_CLASSIFICATION_RESPONSES)
    second_assess = client.post(
        "/assess",
        data={
            "ai_system_name": "Resume Screener",
            "system_description": "Same resume screener, re-assessed after a model update.",
            "intended_purpose": "Recruitment and candidate evaluation for employers.",
            "actor_role": "deployer",
            "sector": "",
            "as_of": "2026-09-09",
        },
    )
    holder.responses = []
    client.post(
        "/report",
        data={
            "facts_json": _extract_hidden_value("facts_json", second_assess.text),
            "classification_json": _extract_hidden_value("classification_json", second_assess.text),
            "classification_llm_calls_json": _extract_hidden_value(
                "classification_llm_calls_json", second_assess.text
            ),
            "as_of": _extract_hidden_value("as_of", second_assess.text),
            "ai_system_name": "Resume Screener",
        },
    )

    detail_response = client.get(f"/systems/{system_id}")
    assert "Assessment history (2)" in detail_response.text


def test_unknown_ai_system_returns_404(web_client):
    client, _holder, _engine = web_client

    response = client.get("/systems/does-not-exist")

    assert response.status_code == 404


def test_superseded_requirement_flags_system_as_outdated(web_client):
    client, holder, engine = web_client

    holder.responses = list(HIGH_RISK_CLASSIFICATION_RESPONSES)
    assess_response = client.post(
        "/assess",
        data={
            "ai_system_name": "Resume Screener",
            "system_description": "An AI tool that screens and ranks job applicant resumes for an employer.",
            "intended_purpose": "Recruitment and candidate evaluation for employers.",
            "actor_role": "deployer",
            "sector": "",
            "as_of": "2026-09-09",
        },
    )
    holder.responses = []
    client.post(
        "/report",
        data={
            "facts_json": _extract_hidden_value("facts_json", assess_response.text),
            "classification_json": _extract_hidden_value("classification_json", assess_response.text),
            "classification_llm_calls_json": _extract_hidden_value(
                "classification_llm_calls_json", assess_response.text
            ),
            "as_of": _extract_hidden_value("as_of", assess_response.text),
            "ai_system_name": "Resume Screener",
        },
    )

    history_html = client.get("/history").text
    assert "Update available" not in history_html

    system_id = re.search(r'/systems/([\w-]+)', history_html).group(1)
    assert "This conclusion may be outdated" not in client.get(f"/systems/{system_id}").text

    with Session(engine) as write_session:
        old = write_session.query(Requirement).filter_by(
            requirement_key="EU-AI-ACT-ANNEXIII-4", superseded_by_id=None
        ).one()
        supersede_requirement(
            write_session, old=old, new_summary="Updated.", new_primary_provision_id=old.primary_provision_id
        )
        write_session.commit()

    history_html = client.get("/history").text
    assert "Update available" in history_html

    detail_html = client.get(f"/systems/{system_id}").text
    assert "This conclusion may be outdated" in detail_html
    assert "EU-AI-ACT-ANNEXIII-4" in detail_html


def test_impact_assessment_document_view_renders_all_sections(web_client):
    client, holder, _engine = web_client

    holder.responses = list(HIGH_RISK_CLASSIFICATION_RESPONSES)
    assess_response = client.post(
        "/assess",
        data={
            "ai_system_name": "Resume Screener",
            "system_description": "An AI tool that screens and ranks job applicant resumes for an employer.",
            "intended_purpose": "Recruitment and candidate evaluation for employers.",
            "actor_role": "deployer",
            "sector": "",
            "as_of": "2026-09-09",
        },
    )
    holder.responses = []
    report_response = client.post(
        "/report",
        data={
            "facts_json": _extract_hidden_value("facts_json", assess_response.text),
            "classification_json": _extract_hidden_value("classification_json", assess_response.text),
            "classification_llm_calls_json": _extract_hidden_value(
                "classification_llm_calls_json", assess_response.text
            ),
            "as_of": _extract_hidden_value("as_of", assess_response.text),
            "ai_system_name": "Resume Screener",
        },
    )
    assessment_id = _extract_assessment_id(report_response.text)

    doc_response = client.get(f"/assessments/{assessment_id}/impact-assessment")

    assert doc_response.status_code == 200
    doc_html = doc_response.text
    assert "AI Impact Assessment" in doc_html
    assert "Resume Screener" in doc_html  # AI system name in the document title
    assert "job applicant" in doc_html.lower()  # system description carried through
    assert "EU-AI-ACT-ANNEXIII-4" in doc_html  # classification citation
    assert "EU-AI-ACT-ART9" in doc_html  # obligation
    assert "Gaps Identified" in doc_html
    assert "Recommended Actions" in doc_html
    assert "substitute for legal advice" in doc_html


def test_impact_assessment_unknown_assessment_returns_404(web_client):
    client, _holder, _engine = web_client

    response = client.get("/assessments/does-not-exist/impact-assessment")

    assert response.status_code == 404


def test_impact_assessment_shows_untitled_when_no_ai_system_named(web_client):
    client, holder, _engine = web_client

    holder.responses = list(HIGH_RISK_CLASSIFICATION_RESPONSES)
    assess_response = client.post(
        "/assess",
        data={
            "system_description": "A customer service chatbot for order status inquiries.",
            "intended_purpose": "Automate routine customer support.",
            "actor_role": "",
            "sector": "",
            "as_of": "2026-09-09",
        },
    )
    holder.responses = []
    report_response = client.post(
        "/report",
        data={
            "facts_json": _extract_hidden_value("facts_json", assess_response.text),
            "classification_json": _extract_hidden_value("classification_json", assess_response.text),
            "classification_llm_calls_json": _extract_hidden_value(
                "classification_llm_calls_json", assess_response.text
            ),
            "as_of": _extract_hidden_value("as_of", assess_response.text),
        },
    )
    assessment_id = _extract_assessment_id(report_response.text)

    doc_html = client.get(f"/assessments/{assessment_id}/impact-assessment").text

    assert "Untitled AI System" in doc_html


def test_deadlines_page_shows_reassessment_due_date_for_named_system(web_client):
    client, holder, _engine = web_client

    assert "Nothing to track yet" in client.get("/deadlines").text

    holder.responses = list(HIGH_RISK_CLASSIFICATION_RESPONSES)
    assess_response = client.post(
        "/assess",
        data={
            "ai_system_name": "Resume Screener",
            "system_description": "An AI tool that screens and ranks job applicant resumes for an employer.",
            "intended_purpose": "Recruitment and candidate evaluation for employers.",
            "actor_role": "deployer",
            "sector": "",
            "as_of": "2026-01-15",
        },
    )
    holder.responses = []
    client.post(
        "/report",
        data={
            "facts_json": _extract_hidden_value("facts_json", assess_response.text),
            "classification_json": _extract_hidden_value("classification_json", assess_response.text),
            "classification_llm_calls_json": _extract_hidden_value(
                "classification_llm_calls_json", assess_response.text
            ),
            "as_of": _extract_hidden_value("as_of", assess_response.text),
            "ai_system_name": "Resume Screener",
        },
    )

    deadlines_html = client.get("/deadlines").text

    assert "Resume Screener" in deadlines_html
    assert "2026-01-15" in deadlines_html  # last assessed
    assert "2027-01-15" in deadlines_html  # due 12 months later


def test_report_and_resolve_incident_on_system_detail_page(web_client):
    client, holder, _engine = web_client

    holder.responses = list(HIGH_RISK_CLASSIFICATION_RESPONSES)
    assess_response = client.post(
        "/assess",
        data={
            "ai_system_name": "Traffic Controller",
            "system_description": "An AI tool that manages traffic light timing.",
            "intended_purpose": "Traffic flow optimization.",
            "actor_role": "deployer",
            "sector": "",
            "as_of": "2026-09-09",
        },
    )
    holder.responses = []
    client.post(
        "/report",
        data={
            "facts_json": _extract_hidden_value("facts_json", assess_response.text),
            "classification_json": _extract_hidden_value("classification_json", assess_response.text),
            "classification_llm_calls_json": _extract_hidden_value(
                "classification_llm_calls_json", assess_response.text
            ),
            "as_of": _extract_hidden_value("as_of", assess_response.text),
            "ai_system_name": "Traffic Controller",
        },
    )
    history_html = client.get("/history").text
    system_id = re.search(r'/systems/([\w-]+)', history_html).group(1)

    report_response = client.post(
        f"/systems/{system_id}/incidents",
        data={
            "severity": "critical_infrastructure_disruption",
            "description": "Traffic lights stuck green on a major intersection for 20 minutes.",
            "detected_at": "2026-09-01",
        },
        follow_redirects=True,
    )

    assert report_response.status_code == 200
    detail_html = report_response.text
    assert "Serious, irreversible disruption to critical infrastructure" in detail_html
    assert "2026-09-03" in detail_html  # 2-day deadline from detection
    assert "Overdue" in detail_html  # server clock is long past 2026-09-03
    assert "Article 73(3)" in detail_html

    incident_id = re.search(r'/incidents/([\w-]+)/mark-reported', detail_html).group(1)
    resolved_response = client.post(f"/incidents/{incident_id}/mark-reported", follow_redirects=True)

    assert resolved_response.status_code == 200
    assert "Reported" in resolved_response.text
    assert "Mark reported" not in resolved_response.text


def test_report_incident_for_unknown_system_returns_404(web_client):
    client, _holder, _engine = web_client

    response = client.post(
        "/systems/does-not-exist/incidents",
        data={"severity": "widespread_infringement", "description": "x", "detected_at": "2026-09-01"},
    )

    assert response.status_code == 404


def test_mark_unknown_incident_reported_returns_404(web_client):
    client, _holder, _engine = web_client

    response = client.post("/incidents/does-not-exist/mark-reported")

    assert response.status_code == 404


def test_actor_email_appears_on_every_surface_after_report_and_incident(web_client):
    """docs/production-audit.md finding H2: no record said which user performed an
    action. This confirms the logged-in user's email actually reaches every page that
    displays attribution, not just the DB columns behind them."""
    client, holder, _engine = web_client

    holder.responses = list(HIGH_RISK_CLASSIFICATION_RESPONSES)
    assess_response = client.post(
        "/assess",
        data={
            "ai_system_name": "Resume Screener",
            "system_description": "An AI tool that screens and ranks job applicant resumes for an employer.",
            "intended_purpose": "Recruitment and candidate evaluation for employers.",
            "actor_role": "deployer",
            "sector": "",
            "as_of": "2026-09-09",
        },
    )
    holder.responses = []
    report_response = client.post(
        "/report",
        data={
            "facts_json": _extract_hidden_value("facts_json", assess_response.text),
            "classification_json": _extract_hidden_value("classification_json", assess_response.text),
            "classification_llm_calls_json": _extract_hidden_value(
                "classification_llm_calls_json", assess_response.text
            ),
            "as_of": _extract_hidden_value("as_of", assess_response.text),
            "ai_system_name": "Resume Screener",
        },
    )
    assert "user@test.example" in report_response.text  # report.html

    assessment_id = _extract_assessment_id(report_response.text)
    assert "user@test.example" in client.get(f"/assessments/{assessment_id}/impact-assessment").text
    assert "user@test.example" in client.get("/history").text

    history_html = client.get("/history").text
    system_id = re.search(r'/systems/([\w-]+)', history_html).group(1)

    incident_response = client.post(
        f"/systems/{system_id}/incidents",
        data={
            "severity": "critical_infrastructure_disruption",
            "description": "x",
            "detected_at": "2026-09-01",
        },
        follow_redirects=True,
    )
    assert incident_response.text.count("user@test.example") >= 2  # assessment table + "Logged by"

    incident_id = re.search(r'/incidents/([\w-]+)/mark-reported', incident_response.text).group(1)
    resolved_response = client.post(f"/incidents/{incident_id}/mark-reported", follow_redirects=True)
    assert "by user@test.example" in resolved_response.text  # resolved_by shown next to "Reported"
