"""Data retention and on-demand deletion for AssessmentRecord.

Per .claude/rules/data.md ("apply data minimization and retention policies") --
AssessmentRecord can carry sensitive evidence text (see docs/security-model.md), so it
must not be kept indefinitely by default.

No scheduler is built here: `purge_expired_assessments` is a plain function, invoked
periodically via cron or manually (see scripts/purge_expired_assessments.py). Building
an in-process scheduler would be exactly the kind of premature infrastructure
docs/architecture.md says to avoid.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from src.persistence.models import AssessmentRecord

DEFAULT_RETENTION_DAYS = 90


def purge_expired_assessments(
    session: Session, *, retention_days: int = DEFAULT_RETENTION_DAYS, as_of: datetime | None = None
) -> int:
    """Delete every AssessmentRecord older than `retention_days` as of `as_of` (default:
    now). Returns the number of records deleted."""
    cutoff = (as_of or datetime.now(timezone.utc)) - timedelta(days=retention_days)
    expired = session.query(AssessmentRecord).filter(AssessmentRecord.created_at < cutoff).all()
    for record in expired:
        session.delete(record)
    session.commit()
    return len(expired)


def delete_assessment(session: Session, assessment_id: str) -> bool:
    """On-demand deletion of a single assessment. Returns False if it didn't exist."""
    record = session.get(AssessmentRecord, assessment_id)
    if record is None:
        return False
    session.delete(record)
    session.commit()
    return True
