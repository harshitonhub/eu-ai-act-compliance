"""Deterministic human-review routing. No LLM anywhere in this module (enforced by
tests/test_architecture_boundaries.py).

Implements the mandate's "Human review" trigger list, minus two that don't apply given
current architecture: "classifier/critic disagreement" (no separate critic LLM exists --
see prompts/critic/README.md; its equivalent, a failed deterministic citation
verification, already surfaces as INSUFFICIENT_INFORMATION and is covered by that
trigger) and "novel scenarios" (not deterministically operationalizable without a
concrete signal -- left for a future phase if evaluation data suggests one).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

from schemas.classification import ClassificationResult
from schemas.enums import ClassificationCategory, ClassificationState, EvidenceStatus
from schemas.evidence import EvidenceAssessment

# Somewhat arbitrary starting point below which a resolved (not INSUFFICIENT_INFORMATION/
# NOT_APPLICABLE) classification is still flagged for review. Revisit once evaluation
# data shows what confidence values actually correlate with classifier errors.
LOW_CONFIDENCE_THRESHOLD = 0.6

_HIGH_IMPACT_STATES = {ClassificationState.YES, ClassificationState.POSSIBLY}
_UNRESOLVED_STATES = {ClassificationState.INSUFFICIENT_INFORMATION, ClassificationState.NOT_APPLICABLE}


class ReviewTrigger(str, enum.Enum):
    INSUFFICIENT_INFORMATION = "insufficient_information"
    LOW_CONFIDENCE = "low_confidence"
    HIGH_IMPACT_PROHIBITED_PRACTICE = "high_impact_prohibited_practice"
    HIGH_IMPACT_HIGH_RISK = "high_impact_high_risk"
    EVIDENCE_GAP = "evidence_gap"
    CONTRADICTION_DETECTED = "contradiction_detected"


@dataclass(frozen=True)
class ReviewFlag:
    trigger: ReviewTrigger
    detail: str


def _classification_flags(classification: ClassificationResult) -> list[ReviewFlag]:
    flags = []
    for assessment in classification.assessments:
        if assessment.state == ClassificationState.INSUFFICIENT_INFORMATION:
            flags.append(
                ReviewFlag(ReviewTrigger.INSUFFICIENT_INFORMATION, f"{assessment.category.value}: {assessment.rationale}")
            )
        elif assessment.state not in _UNRESOLVED_STATES and assessment.confidence < LOW_CONFIDENCE_THRESHOLD:
            flags.append(
                ReviewFlag(
                    ReviewTrigger.LOW_CONFIDENCE,
                    f"{assessment.category.value}: confidence={assessment.confidence} below "
                    f"threshold={LOW_CONFIDENCE_THRESHOLD}",
                )
            )

        if assessment.state in _HIGH_IMPACT_STATES:
            if assessment.category == ClassificationCategory.PROHIBITED_PRACTICES:
                flags.append(ReviewFlag(ReviewTrigger.HIGH_IMPACT_PROHIBITED_PRACTICE, assessment.rationale))
            elif assessment.category == ClassificationCategory.HIGH_RISK:
                flags.append(ReviewFlag(ReviewTrigger.HIGH_IMPACT_HIGH_RISK, assessment.rationale))
    return flags


_LOW_QUALITY_EVIDENCE_STATUSES = {
    EvidenceStatus.INSUFFICIENT_EVIDENCE,
    EvidenceStatus.NON_COMPLIANT,
    EvidenceStatus.PARTIALLY_COMPLIANT,  # "low-quality evidence" per the mandate's review trigger list
}


def _evidence_flags(evidence_assessments: list[EvidenceAssessment]) -> list[ReviewFlag]:
    flags = []
    for assessment in evidence_assessments:
        if assessment.status in _LOW_QUALITY_EVIDENCE_STATUSES:
            flags.append(
                ReviewFlag(ReviewTrigger.EVIDENCE_GAP, f"{assessment.requirement_key}: {assessment.status.value}")
            )
        if assessment.contradictions:
            flags.append(
                ReviewFlag(
                    ReviewTrigger.CONTRADICTION_DETECTED,
                    f"{assessment.requirement_key}: " + "; ".join(assessment.contradictions),
                )
            )
    return flags


def determine_review_flags(
    classification: ClassificationResult, evidence_assessments: list[EvidenceAssessment]
) -> list[ReviewFlag]:
    return _classification_flags(classification) + _evidence_flags(evidence_assessments)
