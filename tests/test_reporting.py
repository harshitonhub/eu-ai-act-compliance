"""Per the compliance-report skill: reporting must not introduce new legal conclusions.
This is checked structurally -- every requirement_key, citation, and status appearing in
the report must trace back to an object the caller already passed in, never a new one
build_report invents.
"""

from datetime import date

from src.reporting.report import build_report
from src.review.triggers import ReviewFlag, ReviewTrigger
from src.gaps.compute import Gap
from src.obligations.mapping import Obligation
from schemas.classification import CategoryClassification, CitedRequirement, ClassificationResult
from schemas.enums import ClassificationCategory, ClassificationState, EvidenceDimension, EvidenceStatus
from schemas.evidence import DimensionAssessment, EvidenceAssessment
from schemas.facts import ExtractedFacts

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
    Obligation(requirement_key="EU-AI-ACT-ART9", citation="Article 9", summary="Risk management.", triggered_by=ClassificationCategory.HIGH_RISK)
]

EVIDENCE = [
    EvidenceAssessment(
        requirement_key="EU-AI-ACT-ART9",
        status=EvidenceStatus.NON_COMPLIANT,
        dimensions=[DimensionAssessment(dimension=d, met=False, note="n/a") for d in EvidenceDimension],
        rationale="No policy provided.",
    )
]

GAPS = [Gap(requirement_key="EU-AI-ACT-ART9", citation="Article 9", obligation_summary="Risk management.", evidence_status=EvidenceStatus.NON_COMPLIANT, rationale="No policy provided.")]

REVIEW_FLAGS = [ReviewFlag(ReviewTrigger.EVIDENCE_GAP, "EU-AI-ACT-ART9: NON_COMPLIANT")]


def test_report_assembles_all_sections():
    report = build_report(FACTS, date(2026, 9, 9), CLASSIFICATION, OBLIGATIONS, EVIDENCE, GAPS, REVIEW_FLAGS)

    assert report.facts == FACTS
    assert report.classification == CLASSIFICATION
    assert report.obligations == OBLIGATIONS
    assert report.evidence_assessments == EVIDENCE
    assert report.gaps == GAPS
    assert report.review_flags == REVIEW_FLAGS
    assert report.requires_human_review is True


def test_report_introduces_no_requirement_keys_beyond_its_inputs():
    report = build_report(FACTS, date(2026, 9, 9), CLASSIFICATION, OBLIGATIONS, EVIDENCE, GAPS, REVIEW_FLAGS)

    input_keys = (
        {c.requirement_key for a in CLASSIFICATION.assessments for c in a.cited_requirements}
        | {o.requirement_key for o in OBLIGATIONS}
        | {e.requirement_key for e in EVIDENCE}
        | {g.requirement_key for g in GAPS}
    )
    report_keys = {o.requirement_key for o in report.obligations} | {e.requirement_key for e in report.evidence_assessments} | {g.requirement_key for g in report.gaps}

    assert report_keys.issubset(input_keys)


def test_recommended_actions_are_derived_only_from_gaps_not_invented():
    report = build_report(FACTS, date(2026, 9, 9), CLASSIFICATION, OBLIGATIONS, EVIDENCE, GAPS, REVIEW_FLAGS)

    assert len(report.recommended_actions) == len(GAPS)
    for action, gap in zip(report.recommended_actions, GAPS):
        assert gap.requirement_key in action
        assert gap.obligation_summary in action


def test_no_gaps_means_no_recommended_actions_and_no_review_required():
    report = build_report(FACTS, date(2026, 9, 9), CLASSIFICATION, [], [], [], [])

    assert report.recommended_actions == []
    assert report.requires_human_review is False
