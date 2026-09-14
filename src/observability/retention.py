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

from datetime import datetime, timedelta, UTC

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.persistence.models import AssessmentRecord
from src.persistence.tenancy import cross_tenant_context

DEFAULT_RETENTION_DAYS = 90


def purge_expired_assessments(
    session: Session, *, retention_days: int = DEFAULT_RETENTION_DAYS, as_of: datetime | None = None
) -> int:
    """Delete every AssessmentRecord older than `retention_days` as of `as_of` (default:
    now). Returns the number of records deleted.

    Runs under `cross_tenant_context` deliberately: this is a cron job with no logged-in
    user, and the retention obligation applies to every tenant's data equally. It is one
    of only two sanctioned uses of that escape hatch, and it is unreachable from an HTTP
    request -- no route calls it.
    """
    cutoff = (as_of or datetime.now(UTC)) - timedelta(days=retention_days)
    with cross_tenant_context(session):
        expired = list(
            session.scalars(select(AssessmentRecord).where(AssessmentRecord.created_at < cutoff)).all()
        )
        for record in expired:
            session.delete(record)
        session.commit()
    return len(expired)


def delete_assessment(session: Session, assessment_id: str) -> bool:
    """On-demand deletion of a single assessment. Returns False if it didn't exist.

    Tenant-scoped, unlike the purge above: this is a user action, so another tenant's
    assessment must read as "doesn't exist" rather than being deletable. The scoping is
    automatic -- `session.get` is filtered by src/persistence/tenancy.py.
    """
    record = session.get(AssessmentRecord, assessment_id)
    if record is None:
        return False
    session.delete(record)
    session.commit()
    return True
