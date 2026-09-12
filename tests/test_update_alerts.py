from datetime import date

from schemas.classification import CategoryClassification, CitedRequirement, ClassificationResult
from schemas.enums import ClassificationCategory, ClassificationState
from schemas.facts import ExtractedFacts
from src.legal.ingest import ingest_seed
from src.legal.update_alerts import check_ai_system_for_updates, list_update_alerts
from src.legal.versioning import supersede_requirement
from src.observability.assessment_log import record_assessment
from src.persistence.models import Requirement
from src.systems.registry import get_or_create_ai_system


def _classification_citing_art9() -> ClassificationResult:
    assessments = []
    for category in ClassificationCategory:
        if category == ClassificationCategory.HIGH_RISK:
            state = ClassificationState.YES
            cited = [CitedRequirement(requirement_key="EU-AI-ACT-ART9", citation="Article 9", relevance="test")]
        else:
            state = ClassificationState.NO
            cited = []
        assessments.append(
            CategoryClassification(
                category=category, state=state, cited_requirements=cited, rationale="x", confidence=0.9
            )
        )
    return ClassificationResult(assessments=assessments)


def _record_assessment_citing_art9(session, ai_system_id: str) -> str:
    return record_assessment(
        session,
        as_of=date(2026, 9, 9),
        legal_knowledge_source_key="eu_ai_act_2024_1689",
        facts=ExtractedFacts(system_description="x", intended_purpose="x"),
        classification=_classification_citing_art9(),
        obligations=[],
        evidence_assessments=[],
        gaps=[],
        review_flags=[],
        llm_calls=[],
        ai_system_id=ai_system_id,
    )


def _current_art9(session) -> Requirement:
    return session.query(Requirement).filter_by(requirement_key="EU-AI-ACT-ART9", superseded_by_id=None).one()


def test_no_alert_when_nothing_superseded(session):
    ingest_seed(session)
    system = get_or_create_ai_system(session, "Resume Screener")
    _record_assessment_citing_art9(session, system.id)

    assert check_ai_system_for_updates(session, system.id) is None


def test_alert_when_requirement_superseded_after_assessment(session):
    ingest_seed(session)
    system = get_or_create_ai_system(session, "Resume Screener")
    assessment_id = _record_assessment_citing_art9(session, system.id)

    old = _current_art9(session)
    supersede_requirement(session, old=old, new_summary="Updated.", new_primary_provision_id=old.primary_provision_id)

    alert = check_ai_system_for_updates(session, system.id)

    assert alert is not None
    assert alert.ai_system_name == "Resume Screener"
    assert alert.assessment_id == assessment_id
    assert alert.outdated_requirement_keys == ("EU-AI-ACT-ART9",)


def test_no_alert_when_assessment_made_after_supersession(session):
    ingest_seed(session)
    system = get_or_create_ai_system(session, "Resume Screener")

    old = _current_art9(session)
    supersede_requirement(session, old=old, new_summary="Updated.", new_primary_provision_id=old.primary_provision_id)

    _record_assessment_citing_art9(session, system.id)

    assert check_ai_system_for_updates(session, system.id) is None


def test_no_alert_for_system_with_no_assessments(session):
    ingest_seed(session)
    system = get_or_create_ai_system(session, "Untouched System")

    assert check_ai_system_for_updates(session, system.id) is None


def test_list_update_alerts_covers_multiple_systems(session):
    ingest_seed(session)
    flagged = get_or_create_ai_system(session, "Flagged System")
    clean = get_or_create_ai_system(session, "Clean System")

    _record_assessment_citing_art9(session, flagged.id)
    _record_assessment_citing_art9(session, clean.id)

    old = _current_art9(session)
    supersede_requirement(session, old=old, new_summary="Updated.", new_primary_provision_id=old.primary_provision_id)

    # "clean" re-assesses after the update, so its new latest assessment is current.
    _record_assessment_citing_art9(session, clean.id)

    alerts = list_update_alerts(session)

    assert {a.ai_system_id for a in alerts} == {flagged.id}
