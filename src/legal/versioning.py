"""Deterministic requirement versioning. No LLM involved.

A legal update never overwrites a Requirement row in place — it creates a new row
with an incremented version and points the old row's superseded_by_id at it, per
.claude/rules/data.md ("preserve ... requirements ... separately") and the
legal-source-update skill ("do not overwrite old legal versions").
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from src.persistence.models import Requirement


def supersede_requirement(
    session: Session, *, old: Requirement, new_summary: str, new_primary_provision_id: str
) -> Requirement:
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

    old.superseded_by_id = new.id
    session.flush()
    return new
