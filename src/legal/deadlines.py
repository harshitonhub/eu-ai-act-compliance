"""Deadlines dashboard (Phase D). Deterministic only, no LLM.

Aggregates two kinds of dates into one view per AI system, instead of checking each
system's own history page one at a time: when it's due for re-assessment, and when a
requirement that was NOT_APPLICABLE at assessment time will actually come into force.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from schemas.classification import ClassificationResult
from schemas.enums import ClassificationState
from src.classification.category_scope import CATEGORY_KEY_PREFIXES
from src.persistence.models import AISystem, ApplicabilityCondition, AssessmentRecord, Requirement

# Not itself an AI Act requirement -- the Act doesn't mandate a re-assessment cadence.
# A 12-month default is a product policy: long enough not to spam, short enough to
# catch drift most orgs would otherwise only notice at renewal time.
REASSESSMENT_INTERVAL_MONTHS = 12


def _add_months(d: date, months: int) -> date:
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


@dataclass(frozen=True)
class UpcomingApplicability:
    category: str
    becomes_applicable_on: date


@dataclass(frozen=True)
class SystemDeadlines:
    ai_system_id: str
    ai_system_name: str
    latest_assessment_id: str
    latest_as_of: date
    reassessment_due_on: date
    is_overdue: bool
    upcoming_applicability: tuple[UpcomingApplicability, ...]


def _next_applicable_date(session: Session, prefixes: tuple[str, ...], after: date) -> date | None:
    """Earliest date a not-yet-applicable requirement in this category's prefix set
    comes into force, or None if there isn't one."""
    if not prefixes:
        return None
    stmt = (
        select(ApplicabilityCondition.temporal_start)
        .join(Requirement, Requirement.id == ApplicabilityCondition.requirement_id)
        .where(Requirement.superseded_by_id.is_(None))
        .where(ApplicabilityCondition.temporal_start > after)
        .where(or_(*(Requirement.requirement_key.like(f"{p}%") for p in prefixes)))
        .order_by(ApplicabilityCondition.temporal_start.asc())
        .limit(1)
    )
    return session.scalars(stmt).first()


def compute_deadlines_for_system(
    session: Session, ai_system_id: str, *, today: date | None = None
) -> SystemDeadlines | None:
    """None if the system has no assessments yet -- nothing to compute a deadline from."""
    latest = session.scalars(
        select(AssessmentRecord)
        .where(AssessmentRecord.ai_system_id == ai_system_id)
        .order_by(AssessmentRecord.created_at.desc())
        .limit(1)
    ).first()
    if latest is None:
        return None

    system = session.get(AISystem, ai_system_id)
    classification = ClassificationResult.model_validate_json(latest.classification_json)

    upcoming = []
    for assessment in classification.assessments:
        if assessment.state != ClassificationState.NOT_APPLICABLE:
            continue
        next_date = _next_applicable_date(session, CATEGORY_KEY_PREFIXES.get(assessment.category, ()), latest.as_of)
        if next_date is not None:
            upcoming.append(UpcomingApplicability(category=assessment.category.value, becomes_applicable_on=next_date))

    due_on = _add_months(latest.as_of, REASSESSMENT_INTERVAL_MONTHS)
    return SystemDeadlines(
        ai_system_id=ai_system_id,
        ai_system_name=system.name if system is not None else "(unknown system)",
        latest_assessment_id=latest.id,
        latest_as_of=latest.as_of,
        reassessment_due_on=due_on,
        is_overdue=due_on <= (today or date.today()),
        upcoming_applicability=tuple(upcoming),
    )


def list_all_deadlines(session: Session, *, today: date | None = None) -> list[SystemDeadlines]:
    """One entry per AI system with at least one assessment, soonest re-assessment due
    date first -- the dashboard-ready view."""
    results = []
    for (system_id,) in session.execute(select(AISystem.id)).all():
        deadlines = compute_deadlines_for_system(session, system_id, today=today)
        if deadlines is not None:
            results.append(deadlines)
    results.sort(key=lambda d: d.reassessment_due_on)
    return results
