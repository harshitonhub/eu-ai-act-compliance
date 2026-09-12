from datetime import date

from schemas.classification import CategoryClassification, CitedRequirement, ClassificationResult
from schemas.enums import ClassificationCategory, ClassificationState
from schemas.facts import ExtractedFacts
from src.legal.deadlines import compute_deadlines_for_system, list_all_deadlines
from src.legal.ingest import ingest_seed
from src.observability.assessment_log import record_assessment
from src.systems.registry import get_or_create_ai_system


def _classification(high_risk_state: ClassificationState) -> ClassificationResult:
    assessments = []
    for category in ClassificationCategory:
        if category == ClassificationCategory.HIGH_RISK:
            state = high_risk_state
            cited = (
                [CitedRequirement(requirement_key="EU-AI-ACT-ANNEXIII-4", citation="Annex III", relevance="test")]
                if state != ClassificationState.NOT_APPLICABLE
                else []
            )
        else:
            state, cited = ClassificationState.NO, []
        assessments.append(
            CategoryClassification(category=category, state=state, cited_requirements=cited, rationale="x", confidence=0.9)
        )
    return ClassificationResult(assessments=assessments)


def _record(session, ai_system_id: str, as_of: date, high_risk_state: ClassificationState) -> str:
    return record_assessment(
        session,
        as_of=as_of,
        legal_knowledge_source_key="eu_ai_act_2024_1689",
        facts=ExtractedFacts(system_description="x", intended_purpose="x"),
        classification=_classification(high_risk_state),
        obligations=[],
        evidence_assessments=[],
        gaps=[],
        review_flags=[],
        llm_calls=[],
        ai_system_id=ai_system_id,
    )


def test_no_deadlines_for_system_with_no_assessments(session):
    ingest_seed(session)
    system = get_or_create_ai_system(session, "Untouched System")

    assert compute_deadlines_for_system(session, system.id) is None


def test_reassessment_due_date_is_twelve_months_after_as_of(session):
    ingest_seed(session)
    system = get_or_create_ai_system(session, "Resume Screener")
    _record(session, system.id, date(2026, 1, 15), ClassificationState.YES)

    deadlines = compute_deadlines_for_system(session, system.id, today=date(2026, 6, 1))

    assert deadlines.latest_as_of == date(2026, 1, 15)
    assert deadlines.reassessment_due_on == date(2027, 1, 15)
    assert deadlines.is_overdue is False


def test_reassessment_marked_overdue_after_due_date_passes(session):
    ingest_seed(session)
    system = get_or_create_ai_system(session, "Resume Screener")
    _record(session, system.id, date(2025, 1, 15), ClassificationState.YES)

    deadlines = compute_deadlines_for_system(session, system.id, today=date(2026, 6, 1))

    assert deadlines.reassessment_due_on == date(2026, 1, 15)
    assert deadlines.is_overdue is True


def test_not_applicable_high_risk_reports_upcoming_applicability(session):
    ingest_seed(session)
    system = get_or_create_ai_system(session, "Early Bird System")
    # Well before any high-risk pathway is in force in the seed corpus.
    _record(session, system.id, date(2025, 1, 1), ClassificationState.NOT_APPLICABLE)

    deadlines = compute_deadlines_for_system(session, system.id, today=date(2025, 6, 1))

    assert len(deadlines.upcoming_applicability) == 1
    upcoming = deadlines.upcoming_applicability[0]
    assert upcoming.category == "high_risk"
    assert upcoming.becomes_applicable_on > date(2025, 1, 1)


def test_yes_classification_reports_no_upcoming_applicability(session):
    ingest_seed(session)
    system = get_or_create_ai_system(session, "Resume Screener")
    _record(session, system.id, date(2026, 9, 9), ClassificationState.YES)

    deadlines = compute_deadlines_for_system(session, system.id, today=date(2026, 9, 9))

    assert deadlines.upcoming_applicability == ()


def test_list_all_deadlines_sorts_soonest_due_first(session):
    ingest_seed(session)
    later = get_or_create_ai_system(session, "Later Due")
    sooner = get_or_create_ai_system(session, "Sooner Due")
    _record(session, later.id, date(2026, 6, 1), ClassificationState.YES)
    _record(session, sooner.id, date(2026, 1, 1), ClassificationState.YES)

    results = list_all_deadlines(session, today=date(2026, 9, 9))

    assert [d.ai_system_id for d in results] == [sooner.id, later.id]


def test_list_all_deadlines_skips_systems_with_no_assessments(session):
    ingest_seed(session)
    get_or_create_ai_system(session, "Untouched System")
    assessed = get_or_create_ai_system(session, "Assessed System")
    _record(session, assessed.id, date(2026, 1, 1), ClassificationState.YES)

    results = list_all_deadlines(session, today=date(2026, 9, 9))

    assert [d.ai_system_id for d in results] == [assessed.id]
