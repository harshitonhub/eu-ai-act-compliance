"""Phase 6 DoD: a past assessment can be fully reconstructed from stored version/trace
data alone.
"""

from datetime import date, datetime, UTC

from src.auth.users import create_user
from src.observability.assessment_log import list_recent_assessments, record_assessment, reconstruct_assessment
from src.observability.instrumented_client import LLMCallRecord
from src.gaps.compute import Gap
from src.obligations.mapping import Obligation
from schemas.classification import CategoryClassification, CitedRequirement, ClassificationResult
from schemas.enums import ClassificationCategory, ClassificationState, EvidenceDimension, EvidenceStatus, UserRole
from schemas.evidence import DimensionAssessment, EvidenceAssessment
from schemas.facts import ExtractedFacts
from src.review.triggers import ReviewFlag, ReviewTrigger
from tests.conftest import PRIMARY_TENANT_ID

FACTS = ExtractedFacts(system_description="A recruitment screening tool.", intended_purpose="Screen job applicants.")

CLASSIFICATION = ClassificationResult(
    assessments=[
        CategoryClassification(
            category=cat,
            state=ClassificationState.YES if cat == ClassificationCategory.HIGH_RISK else ClassificationState.NO,
            cited_requirements=(
                [CitedRequirement(requirement_key="EU-AI-ACT-ANNEXIII-4", citation="Annex III", relevance="recruitment")]
                if cat == ClassificationCategory.HIGH_RISK
                else []
            ),
            rationale="fixture",
            confidence=0.9,
        )
        for cat in ClassificationCategory
    ]
)

OBLIGATIONS = [
    Obligation(
        requirement_key="EU-AI-ACT-ART9",
        citation="Article 9",
        summary="Risk management.",
        triggered_by=ClassificationCategory.HIGH_RISK,
    )
]

EVIDENCE = [
    EvidenceAssessment(
        requirement_key="EU-AI-ACT-ART9",
        status=EvidenceStatus.NON_COMPLIANT,
        dimensions=[DimensionAssessment(dimension=d, met=False, note="n/a") for d in EvidenceDimension],
        rationale="No policy provided.",
        contradictions=["doc A vs doc B"],
    )
]

GAPS = [
    Gap(
        requirement_key="EU-AI-ACT-ART9",
        citation="Article 9",
        obligation_summary="Risk management.",
        evidence_status=EvidenceStatus.NON_COMPLIANT,
        rationale="No policy provided.",
    )
]

LLM_CALLS = [
    LLMCallRecord(
        timestamp=datetime(2026, 9, 9, 12, 0, 0, tzinfo=UTC),
        provider="anthropic",
        model="claude-sonnet-4-5",
        prompt_version="classifier-v1",
        response_model_name="CategoryClassification",
        succeeded=True,
        input_tokens=120,
        output_tokens=45,
        retried=False,
        latency_ms=812.3,
    )
]


def test_record_and_reconstruct_round_trips_every_field(session):
    review_flags = [ReviewFlag(ReviewTrigger.HIGH_IMPACT_HIGH_RISK, "high_risk: fixture")]

    assessment_id = record_assessment(
        session,
        as_of=date(2026, 9, 9),
        legal_knowledge_source_key="eu_ai_act_2024_1689",
        facts=FACTS,
        classification=CLASSIFICATION,
        obligations=OBLIGATIONS,
        evidence_assessments=EVIDENCE,
        gaps=GAPS,
        review_flags=review_flags,
        llm_calls=LLM_CALLS,
    )

    reconstructed = reconstruct_assessment(session, assessment_id)

    assert reconstructed is not None
    assert reconstructed.assessment_id == assessment_id
    assert reconstructed.as_of == date(2026, 9, 9)
    assert reconstructed.legal_knowledge_source_key == "eu_ai_act_2024_1689"
    assert reconstructed.facts == FACTS
    assert reconstructed.classification == CLASSIFICATION
    assert reconstructed.obligations == OBLIGATIONS
    assert reconstructed.evidence_assessments == EVIDENCE
    assert reconstructed.gaps == GAPS
    assert reconstructed.review_flags == review_flags
    assert reconstructed.llm_calls == LLM_CALLS
    assert reconstructed.total_input_tokens == 120
    assert reconstructed.total_output_tokens == 45
    assert reconstructed.total_latency_ms == 812.3
    assert reconstructed.error is None


def test_created_by_user_id_round_trips(session):
    user = create_user(
        session, tenant_id=PRIMARY_TENANT_ID, email="assessor@example.com",
        password="correct-horse-1", role=UserRole.MEMBER,
    )

    assessment_id = record_assessment(
        session,
        as_of=date(2026, 9, 9),
        legal_knowledge_source_key="eu_ai_act_2024_1689",
        facts=FACTS,
        classification=CLASSIFICATION,
        obligations=[],
        evidence_assessments=[],
        gaps=[],
        review_flags=[],
        llm_calls=[],
        created_by_user_id=user.id,
    )

    reconstructed = reconstruct_assessment(session, assessment_id)

    assert reconstructed.created_by_user_id == user.id
    assert list_recent_assessments(session)[0].created_by_user_id == user.id


def test_created_by_user_id_defaults_to_none(session):
    assessment_id = record_assessment(
        session, as_of=date(2026, 9, 9), legal_knowledge_source_key="eu_ai_act_2024_1689",
        facts=FACTS, classification=CLASSIFICATION, obligations=[], evidence_assessments=[],
        gaps=[], review_flags=[], llm_calls=[],
    )

    reconstructed = reconstruct_assessment(session, assessment_id)

    assert reconstructed.created_by_user_id is None


def test_reconstruct_unknown_assessment_id_returns_none(session):
    assert reconstruct_assessment(session, "does-not-exist") is None


def test_record_assessment_with_error_is_reconstructable(session):
    assessment_id = record_assessment(
        session,
        as_of=date(2026, 9, 9),
        legal_knowledge_source_key="eu_ai_act_2024_1689",
        facts=FACTS,
        classification=CLASSIFICATION,
        obligations=[],
        evidence_assessments=[],
        gaps=[],
        review_flags=[],
        llm_calls=[],
        error="Anthropic API timeout after 30s.",
    )

    reconstructed = reconstruct_assessment(session, assessment_id)

    assert reconstructed.error == "Anthropic API timeout after 30s."
    assert reconstructed.total_input_tokens == 0


def test_list_recent_assessments_orders_newest_first(session):
    older_id = record_assessment(
        session, as_of=date(2026, 1, 1), legal_knowledge_source_key="eu_ai_act_2024_1689",
        facts=FACTS, classification=CLASSIFICATION, obligations=[], evidence_assessments=[],
        gaps=[], review_flags=[], llm_calls=[],
    )
    newer_id = record_assessment(
        session, as_of=date(2026, 2, 1), legal_knowledge_source_key="eu_ai_act_2024_1689",
        facts=FACTS, classification=CLASSIFICATION, obligations=[], evidence_assessments=[],
        gaps=[], review_flags=[ReviewFlag(ReviewTrigger.HIGH_IMPACT_HIGH_RISK, "fixture")], llm_calls=[],
    )

    summaries = list_recent_assessments(session)

    assert [s.assessment_id for s in summaries][:2] == [newer_id, older_id]
    assert summaries[0].system_description == FACTS.system_description
    assert summaries[0].requires_human_review is True
    assert summaries[1].requires_human_review is False


def test_list_recent_assessments_respects_limit(session):
    for _ in range(3):
        record_assessment(
            session, as_of=date(2026, 1, 1), legal_knowledge_source_key="eu_ai_act_2024_1689",
            facts=FACTS, classification=CLASSIFICATION, obligations=[], evidence_assessments=[],
            gaps=[], review_flags=[], llm_calls=[],
        )

    assert len(list_recent_assessments(session, limit=2)) == 2
