"""AI system registry (Phase A): named records that assessments attach to, so
`/history` can group by system instead of showing one flat list of unrelated runs.

Deterministic only, no LLM -- this is a plain lookup/persistence concern, not
interpretation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.persistence.models import AISystem, AssessmentRecord


@dataclass(frozen=True)
class AISystemSummary:
    id: str
    name: str
    description: str | None
    owner_note: str | None
    created_at: datetime
    assessment_count: int


def get_or_create_ai_system(session: Session, name: str) -> AISystem:
    """Case-sensitive exact-name match. Single-tenant today, so no tenant scoping yet --
    see AISystem's docstring."""
    name = name.strip()
    existing = session.scalars(select(AISystem).where(AISystem.name == name)).first()
    if existing is not None:
        return existing

    system = AISystem(name=name)
    session.add(system)
    session.commit()
    return system


def get_ai_system(session: Session, ai_system_id: str) -> AISystem | None:
    return session.get(AISystem, ai_system_id)


def list_ai_systems(session: Session) -> list[AISystemSummary]:
    systems = session.scalars(select(AISystem).order_by(AISystem.created_at.desc())).all()
    return [
        AISystemSummary(
            id=s.id,
            name=s.name,
            description=s.description,
            owner_note=s.owner_note,
            created_at=s.created_at,
            # count(AssessmentRecord.id), not query(...).count(): the latter buries the
            # entity in a subquery where the tenant filter can't attach, and would count
            # every tenant's rows. src/persistence/tenancy.py rejects that shape outright.
            assessment_count=session.scalar(
                select(func.count(AssessmentRecord.id)).where(AssessmentRecord.ai_system_id == s.id)
            ),
        )
        for s in systems
    ]
