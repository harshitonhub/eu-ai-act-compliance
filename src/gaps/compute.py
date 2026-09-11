"""Deterministic gap analysis: obligations - evidence -> gaps. No LLM anywhere in this
module (enforced by tests/test_architecture_boundaries.py).
"""

from __future__ import annotations

from dataclasses import dataclass

from schemas.enums import EvidenceStatus
from schemas.evidence import EvidenceAssessment
from src.obligations.mapping import Obligation


@dataclass(frozen=True)
class Gap:
    requirement_key: str
    citation: str
    obligation_summary: str
    evidence_status: EvidenceStatus
    rationale: str


def compute_gaps(obligations: list[Obligation], evidence_assessments: list[EvidenceAssessment]) -> list[Gap]:
    """An obligation is a gap unless its evidence status is exactly COMPLIANT."""
    assessments_by_key = {a.requirement_key: a for a in evidence_assessments}

    gaps = []
    for obligation in obligations:
        assessment = assessments_by_key.get(obligation.requirement_key)
        if assessment is not None and assessment.status == EvidenceStatus.COMPLIANT:
            continue

        gaps.append(
            Gap(
                requirement_key=obligation.requirement_key,
                citation=obligation.citation,
                obligation_summary=obligation.summary,
                evidence_status=assessment.status if assessment else EvidenceStatus.INSUFFICIENT_EVIDENCE,
                rationale=assessment.rationale if assessment else "No evidence assessment available for this obligation.",
            )
        )
    return gaps
