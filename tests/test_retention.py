from datetime import date, datetime, timedelta, UTC

from src.observability.retention import delete_assessment, purge_expired_assessments
from src.persistence.models import AssessmentRecord

FIXED_NOW = datetime(2026, 9, 11, tzinfo=UTC)


def _make_record(session, *, created_at: datetime) -> str:
    record = AssessmentRecord(
        created_at=created_at,
        as_of=date(2026, 9, 9),
        legal_knowledge_source_key="eu_ai_act_2024_1689",
        facts_json="{}",
        classification_json="{}",
        obligations_json="[]",
        evidence_assessments_json="[]",
        gaps_json="[]",
        review_flags_json="[]",
        llm_calls_json="[]",
    )
    session.add(record)
    session.commit()
    return record.id


def test_purge_deletes_only_records_older_than_retention_window(session):
    old_id = _make_record(session, created_at=FIXED_NOW - timedelta(days=100))
    recent_id = _make_record(session, created_at=FIXED_NOW - timedelta(days=10))

    count = purge_expired_assessments(session, retention_days=90, as_of=FIXED_NOW)

    assert count == 1
    assert session.get(AssessmentRecord, old_id) is None
    assert session.get(AssessmentRecord, recent_id) is not None


def test_purge_with_no_expired_records_deletes_nothing(session):
    _make_record(session, created_at=FIXED_NOW - timedelta(days=5))

    count = purge_expired_assessments(session, retention_days=90, as_of=FIXED_NOW)

    assert count == 0


def test_delete_assessment_removes_existing_record(session):
    record_id = _make_record(session, created_at=FIXED_NOW)

    result = delete_assessment(session, record_id)

    assert result is True
    assert session.get(AssessmentRecord, record_id) is None


def test_delete_assessment_returns_false_for_unknown_id(session):
    assert delete_assessment(session, "does-not-exist") is False
