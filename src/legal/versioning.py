"""Deterministic requirement versioning. No LLM involved.

A legal update never overwrites a Requirement row in place — it creates a new row
with an incremented version and points the old row's superseded_by_id at it, per
.claude/rules/data.md ("preserve ... requirements ... separately") and the
legal-source-update skill ("do not overwrite old legal versions").
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from src.persistence.models import ApplicabilityCondition, LegalException, Requirement


def supersede_requirement(
    session: Session, *, old: Requirement, new_summary: str, new_primary_provision_id: str
) -> Requirement:
    """Create the next version of `old`, carrying forward its applicability conditions
    and exceptions -- an amendment to a requirement's text doesn't imply its applicability
    changed too. Without this, the new version would have zero ApplicabilityCondition
    rows and become invisible to find_requirements/retrieve (both INNER JOIN on it),
    effectively vanishing the requirement instead of updating it.
    """
    if old.superseded_by_id is not None:
        raise ValueError(f"Requirement {old.requirement_key} v{old.version} is already superseded")

    new = Requirement(
        requirement_key=old.requirement_key,
        version=old.version + 1,
        summary=new_summary,
        primary_provision_id=new_primary_provision_id,
    )
    session.add(new)
    session.flush()

    for condition in old.applicability_conditions:
        session.add(
            ApplicabilityCondition(
                requirement_id=new.id,
                actor_role=condition.actor_role,
                sector=condition.sector,
                annex_iii_category=condition.annex_iii_category,
                temporal_start=condition.temporal_start,
                temporal_end=condition.temporal_end,
            )
        )
    for exception in old.exceptions:
        session.add(
            LegalException(
                requirement_id=new.id,
                description=exception.description,
                source_provision_id=exception.source_provision_id,
            )
        )

    old.superseded_by_id = new.id
    session.flush()
    return new
