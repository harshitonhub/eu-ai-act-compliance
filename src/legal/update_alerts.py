"""Regulatory update alerts (Phase B). Deterministic only, no LLM.

Reuses Phase 1's versioning infrastructure (`supersede_requirement`,
`Requirement.superseded_by_id`) for something user-facing: when a requirement a system
was assessed against later gets superseded, that system's latest conclusion may be
outdated.

No assessment stores which exact Requirement *version* it cited -- only the stable
`requirement_key` (citations only ever come from `find_requirement_by_key`/`retrieve`,
which filter to the live, non-superseded version at query time). So "outdated" is
inferred from timestamps instead of a stored version pointer: if a requirement_key now
has a version created *after* the assessment ran, whatever version the assessment saw
was necessarily the one that got superseded.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from schemas.classification import ClassificationResult
from src.persistence.models import AISystem, AssessmentRecord, Requirement


@dataclass(frozen=True)
class UpdateAlert:
    ai_system_id: str
    ai_system_name: str
    assessment_id: str
    outdated_requirement_keys: tuple[str, ...]


def _requirement_keys_cited_by(record: AssessmentRecord) -> set[str]:
    keys = {
        c.requirement_key
        for a in ClassificationResult.model_validate_json(record.classification_json).assessments
        for c in a.cited_requirements
    }
    keys.update(o["requirement_key"] for o in json.loads(record.obligations_json))
    return keys


def find_outdated_requirement_keys(
    session: Session, requirement_keys: set[str], as_of: datetime
) -> set[str]:
    """Which of `requirement_keys` have a version created after `as_of` -- i.e. were
    amended since. Requirement.created_at, not the legal effective_date: this tracks
    when *this system* learned about the change, not when the law took effect."""
    if not requirement_keys:
        return set()
    stmt = select(Requirement.requirement_key).where(
        Requirement.requirement_key.in_(requirement_keys),
        Requirement.created_at > as_of,
    )
    return set(session.scalars(stmt).all())


def check_ai_system_for_updates(session: Session, ai_system_id: str) -> UpdateAlert | None:
    """None if the system has no assessments, or its latest one is fully current."""
    latest = session.scalars(
        select(AssessmentRecord)
        .where(AssessmentRecord.ai_system_id == ai_system_id)
        .order_by(AssessmentRecord.created_at.desc())
        .limit(1)
    ).first()
    if latest is None:
        return None

    cited_keys = _requirement_keys_cited_by(latest)
    outdated = find_outdated_requirement_keys(session, cited_keys, latest.created_at)
    if not outdated:
        return None

    system = session.get(AISystem, ai_system_id)
    return UpdateAlert(
        ai_system_id=ai_system_id,
        ai_system_name=system.name if system is not None else "(unknown system)",
        assessment_id=latest.id,
        outdated_requirement_keys=tuple(sorted(outdated)),
    )


def list_update_alerts(session: Session) -> list[UpdateAlert]:
    """One alert per AI system whose latest assessment cites a since-superseded
    requirement -- the dashboard-ready view. Empty for a system with no assessments or a
    fully current latest one."""
    alerts = []
    for (system_id,) in session.execute(select(AISystem.id)).all():
        alert = check_ai_system_for_updates(session, system_id)
        if alert is not None:
            alerts.append(alert)
    return alerts
