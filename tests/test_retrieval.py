from datetime import date

from src.legal.ingest import ingest_seed
from src.retrieval.retrieval import keyword_score, retrieve, retrieve_by_key


def test_keyword_score_full_and_zero_overlap():
    assert keyword_score("recruitment employment candidates", "recruitment employment candidates") == 1.0
    assert keyword_score("recruitment employment", "totally unrelated text about weather") == 0.0


def test_keyword_score_empty_query_is_zero():
    assert keyword_score("", "anything") == 0.0


def test_retrieve_by_key_exact_lookup(session):
    ingest_seed(session)

    result = retrieve_by_key(session, "EU-AI-ACT-ANNEXIII-4")

    assert result is not None
    assert result.relevance_score == 1.0
    assert "Employment" in result.summary

    assert retrieve_by_key(session, "NOT-A-REAL-KEY") is None


def test_retrieve_ranks_by_keyword_overlap(session):
    ingest_seed(session)

    results = retrieve(
        session,
        query_text="recruitment job applications candidates hiring",
        requirement_key_prefixes=("EU-AI-ACT-ANNEXIII",),
        as_of=date(2026, 9, 1),
    )

    assert results[0].requirement_key == "EU-AI-ACT-ANNEXIII-4"
    assert results[0].relevance_score >= results[-1].relevance_score


def test_retrieve_empty_prefix_tuple_returns_nothing(session):
    ingest_seed(session)

    results = retrieve(session, query_text="anything at all", requirement_key_prefixes=())

    assert results == []


def test_retrieve_respects_temporal_filter(session):
    ingest_seed(session)

    before_high_risk_applies = retrieve(
        session,
        query_text="employment recruitment",
        requirement_key_prefixes=("EU-AI-ACT-ANNEXIII",),
        as_of=date(2025, 6, 1),
    )

    assert before_high_risk_applies == []
