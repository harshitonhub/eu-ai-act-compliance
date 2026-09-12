"""Deterministic classification -> obligations mapping. No LLM anywhere in this module
(enforced by tests/test_architecture_boundaries.py).

Obligations attach on YES or POSSIBLY (not just YES): a POSSIBLY high-risk classification
still needs to show the org what it would owe if the uncertainty resolves affirmatively --
review routing (Phase 5) is what flags the uncertainty itself, not this mapping.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from schemas.classification import ClassificationResult
from schemas.enums import ClassificationCategory, ClassificationState
from src.legal.queries import find_requirement_by_key

TRIGGERING_STATES = {ClassificationState.YES, ClassificationState.POSSIBLY}

# Chapter III, Section 2 -- see docs/legal-methodology.md's "Obligation mapping basis".
HIGH_RISK_OBLIGATION_KEYS = (
    "EU-AI-ACT-ART9",
    "EU-AI-ACT-ART10",
    "EU-AI-ACT-ART11",
    "EU-AI-ACT-ART12",
    "EU-AI-ACT-ART13",
    "EU-AI-ACT-ART14",
    "EU-AI-ACT-ART15",
    # GDPR obligations that attach alongside the AI Act's: a high-risk AI decision about a
    # person is almost always also GDPR "automated decision-making" (ROADMAP.md Phase M).
    "GDPR-ART22",
    "GDPR-ART35",
)

PROHIBITED_PRACTICE_CEASE_KEY = "EU-AI-ACT-CEASE-PROHIBITED-PRACTICE"


@dataclass(frozen=True)
class Obligation:
    requirement_key: str
    citation: str
    summary: str
    triggered_by: ClassificationCategory


def map_obligations(session: Session, classification_result: ClassificationResult) -> list[Obligation]:
    obligations: list[Obligation] = []

    high_risk = classification_result.for_category(ClassificationCategory.HIGH_RISK)
    if high_risk.state in TRIGGERING_STATES:
        for key in HIGH_RISK_OBLIGATION_KEYS:
            requirement = find_requirement_by_key(session, key)
            if requirement is not None:
                obligations.append(
                    Obligation(
                        requirement_key=requirement.requirement_key,
                        citation=requirement.citation,
                        summary=requirement.summary,
                        triggered_by=ClassificationCategory.HIGH_RISK,
                    )
                )

    prohibited = classification_result.for_category(ClassificationCategory.PROHIBITED_PRACTICES)
    if prohibited.state in TRIGGERING_STATES:
        obligations.append(
            Obligation(
                requirement_key=PROHIBITED_PRACTICE_CEASE_KEY,
                citation=prohibited.cited_requirements[0].citation if prohibited.cited_requirements else "Article 5",
                summary="This AI practice is prohibited: it must not be placed on the market, "
                "put into service, or used.",
                triggered_by=ClassificationCategory.PROHIBITED_PRACTICES,
            )
        )

    return obligations
