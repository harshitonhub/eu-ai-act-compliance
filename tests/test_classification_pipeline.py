from datetime import date

from src.classification.classify import classify_category, classify_system
from src.legal.ingest import ingest_seed
from src.llm.fake_client import FakeCompletionProvider
from src.llm.interface import LLMClient
from src.retrieval.retrieval import retrieve
from schemas.enums import ClassificationCategory, ClassificationState
from schemas.facts import ExtractedFacts

RECRUITMENT_FACTS = ExtractedFacts(
    system_description="An AI tool that screens and ranks job applicant resumes.",
    intended_purpose="Recruitment and candidate evaluation for employers.",
)


def _client(responses: list[str]) -> tuple[LLMClient, FakeCompletionProvider]:
    provider = FakeCompletionProvider(responses)
    return LLMClient(provider, model="fake-model"), provider


def test_category_with_no_candidates_skips_llm_call(session):
    ingest_seed(session)
    client, provider = _client([])  # no responses programmed -- would raise if called

    result = classify_category(client, ClassificationCategory.SCOPE, RECRUITMENT_FACTS, candidates=[])

    assert result.state == ClassificationState.INSUFFICIENT_INFORMATION
    assert len(provider.calls) == 0


def test_valid_llm_response_with_verifiable_citation_passes_through(session):
    ingest_seed(session)
    valid_response = (
        '{"category": "high_risk", "state": "YES", '
        '"cited_requirements": [{"requirement_key": "EU-AI-ACT-ANNEXIII-4", '
        '"citation": "Annex III", "relevance": "recruitment tool"}], '
        '"rationale": "Used for recruitment, matches Annex III point 4(a).", "confidence": 0.9}'
    )
    client, _ = _client([valid_response])
    candidates = retrieve(
        session, query_text="recruitment", requirement_key_prefixes=("EU-AI-ACT-ANNEXIII",), as_of=date(2026, 9, 1)
    )

    result = classify_category(client, ClassificationCategory.HIGH_RISK, RECRUITMENT_FACTS, candidates)

    assert result.state == ClassificationState.YES
    assert result.cited_requirements[0].requirement_key == "EU-AI-ACT-ANNEXIII-4"


def test_hallucinated_citation_fails_closed(session):
    ingest_seed(session)
    hallucinated_response = (
        '{"category": "high_risk", "state": "YES", '
        '"cited_requirements": [{"requirement_key": "EU-AI-ACT-MADE-UP", '
        '"citation": "Article 999", "relevance": "invented"}], '
        '"rationale": "Fabricated basis.", "confidence": 0.9}'
    )
    client, _ = _client([hallucinated_response])
    candidates = retrieve(
        session, query_text="recruitment", requirement_key_prefixes=("EU-AI-ACT-ANNEXIII",), as_of=date(2026, 9, 1)
    )

    result = classify_category(client, ClassificationCategory.HIGH_RISK, RECRUITMENT_FACTS, candidates)

    assert result.state == ClassificationState.INSUFFICIENT_INFORMATION
    assert "citation verification failed" in result.rationale


def test_mismatched_category_in_response_fails_closed(session):
    ingest_seed(session)
    wrong_category_response = (
        '{"category": "prohibited_practices", "state": "NO", '
        '"cited_requirements": [], "rationale": "n/a", "confidence": 0.5}'
    )
    client, _ = _client([wrong_category_response])
    candidates = retrieve(
        session, query_text="recruitment", requirement_key_prefixes=("EU-AI-ACT-ANNEXIII",), as_of=date(2026, 9, 1)
    )

    result = classify_category(client, ClassificationCategory.HIGH_RISK, RECRUITMENT_FACTS, candidates)

    assert result.state == ClassificationState.INSUFFICIENT_INFORMATION
    assert "expected high_risk" in result.rationale


def test_classify_system_covers_all_five_categories_with_no_candidates_for_three(session):
    ingest_seed(session)
    prohibited_response = (
        '{"category": "prohibited_practices", "state": "NO", '
        '"cited_requirements": [], "rationale": "No prohibited practice indicators.", "confidence": 0.8}'
    )
    high_risk_response = (
        '{"category": "high_risk", "state": "YES", '
        '"cited_requirements": [{"requirement_key": "EU-AI-ACT-ANNEXIII-4", '
        '"citation": "Annex III", "relevance": "recruitment"}], '
        '"rationale": "Matches Annex III point 4(a).", "confidence": 0.9}'
    )
    client, provider = _client([prohibited_response, high_risk_response])

    result = classify_system(client, session, RECRUITMENT_FACTS, as_of=date(2026, 9, 1))

    assert len(provider.calls) == 2  # only prohibited_practices and high_risk have candidates
    assert result.for_category(ClassificationCategory.SCOPE).state == ClassificationState.INSUFFICIENT_INFORMATION
    assert result.for_category(ClassificationCategory.GPAI).state == ClassificationState.INSUFFICIENT_INFORMATION
    assert (
        result.for_category(ClassificationCategory.TRANSPARENCY).state
        == ClassificationState.INSUFFICIENT_INFORMATION
    )
    assert result.for_category(ClassificationCategory.PROHIBITED_PRACTICES).state == ClassificationState.NO
    assert result.for_category(ClassificationCategory.HIGH_RISK).state == ClassificationState.YES


def test_classify_system_before_entry_into_force_is_not_applicable_not_insufficient(session):
    ingest_seed(session)
    client, provider = _client([])  # no LLM calls expected at all

    result = classify_system(client, session, RECRUITMENT_FACTS, as_of=date(2024, 6, 1))

    assert len(provider.calls) == 0
    assert result.for_category(ClassificationCategory.PROHIBITED_PRACTICES).state == ClassificationState.NOT_APPLICABLE
    assert result.for_category(ClassificationCategory.HIGH_RISK).state == ClassificationState.NOT_APPLICABLE
    # categories with no ingested legal knowledge at all remain INSUFFICIENT_INFORMATION, not NOT_APPLICABLE
    assert result.for_category(ClassificationCategory.SCOPE).state == ClassificationState.INSUFFICIENT_INFORMATION


def test_classify_system_partial_temporal_application(session):
    ingest_seed(session)
    prohibited_response = (
        '{"category": "prohibited_practices", "state": "NO", '
        '"cited_requirements": [], "rationale": "No prohibited practice indicators.", "confidence": 0.8}'
    )
    client, provider = _client([prohibited_response])

    # 2025-06-01: Chapter II (Article 5) is in force; the high-risk pathway (Article 6 /
    # Annex III) is not yet -- general application date is 2026-08-02.
    result = classify_system(client, session, RECRUITMENT_FACTS, as_of=date(2025, 6, 1))

    assert len(provider.calls) == 1  # only prohibited_practices calls the LLM
    assert result.for_category(ClassificationCategory.PROHIBITED_PRACTICES).state == ClassificationState.NO
    assert result.for_category(ClassificationCategory.HIGH_RISK).state == ClassificationState.NOT_APPLICABLE
