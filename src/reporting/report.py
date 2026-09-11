"""Report assembly: packages already-established results into a ComplianceReport.

No LLM anywhere in this module (enforced by tests/test_architecture_boundaries.py) and
no new legal conclusions -- per the compliance-report skill, this stage only restates
what classification/obligations/evidence/review already concluded. `recommended_actions`
is a deterministic template over `gaps`, not a fresh judgment.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from schemas.classification import ClassificationResult
from schemas.evidence import EvidenceAssessment
from schemas.facts import ExtractedFacts
from src.gaps.compute import Gap
from src.obligations.mapping import Obligation
from src.review.triggers import ReviewFlag


@dataclass(frozen=True)
class ComplianceReport:
    facts: ExtractedFacts
    as_of: date
    classification: ClassificationResult
    obligations: list[Obligation]
    evidence_assessments: list[EvidenceAssessment]
    gaps: list[Gap]
    review_flags: list[ReviewFlag]
    recommended_actions: list[str] = field(default_factory=list)

    @property
    def requires_human_review(self) -> bool:
        return len(self.review_flags) > 0


def _recommended_actions(gaps: list[Gap]) -> list[str]:
    return [
        f"Provide evidence addressing {gap.citation} ({gap.requirement_key}): {gap.obligation_summary}"
        for gap in gaps
    ]


def build_report(
    facts: ExtractedFacts,
    as_of: date,
    classification: ClassificationResult,
    obligations: list[Obligation],
    evidence_assessments: list[EvidenceAssessment],
    gaps: list[Gap],
    review_flags: list[ReviewFlag],
) -> ComplianceReport:
    return ComplianceReport(
        facts=facts,
        as_of=as_of,
        classification=classification,
        obligations=obligations,
        evidence_assessments=evidence_assessments,
        gaps=gaps,
        review_flags=review_flags,
        recommended_actions=_recommended_actions(gaps),
    )
