"""Incident logging (Phase E). Deterministic only, no LLM.

Article 73 sets three reporting-deadline tiers, keyed off which Article 3(49)/(61)
category the incident falls into -- this module is the deterministic lookup table
translating "what kind of incident" into "how many days you have," per the verbatim
text ingested into legal/sources/eu_ai_act_2024_1689/article_73.txt.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from schemas.enums import IncidentSeverity
from src.legal.queries import find_provision_text_by_citation
from src.persistence.models import Incident

# Article 73(3): widespread infringement or a 3(49)(b) incident -- 2 days.
# Article 73(4): death of a person (3(49)(a)) -- 10 days.
# Article 73(2): every other case (default) -- 15 days.
SEVERITY_DEADLINE_DAYS: dict[IncidentSeverity, int] = {
    IncidentSeverity.DEATH_OR_SERIOUS_HEALTH_HARM: 10,
    IncidentSeverity.CRITICAL_INFRASTRUCTURE_DISRUPTION: 2,
    IncidentSeverity.FUNDAMENTAL_RIGHTS_INFRINGEMENT: 15,
    IncidentSeverity.PROPERTY_OR_ENVIRONMENT_HARM: 15,
    IncidentSeverity.WIDESPREAD_INFRINGEMENT: 2,
}

SEVERITY_CITATIONS: dict[IncidentSeverity, str] = {
    IncidentSeverity.DEATH_OR_SERIOUS_HEALTH_HARM: "Article 73(4)",
    IncidentSeverity.CRITICAL_INFRASTRUCTURE_DISRUPTION: "Article 73(3)",
    IncidentSeverity.FUNDAMENTAL_RIGHTS_INFRINGEMENT: "Article 73(2)",
    IncidentSeverity.PROPERTY_OR_ENVIRONMENT_HARM: "Article 73(2)",
    IncidentSeverity.WIDESPREAD_INFRINGEMENT: "Article 73(3)",
}

SEVERITY_LABELS: dict[IncidentSeverity, str] = {
    IncidentSeverity.DEATH_OR_SERIOUS_HEALTH_HARM: "Death or serious harm to a person's health",
    IncidentSeverity.CRITICAL_INFRASTRUCTURE_DISRUPTION: "Serious, irreversible disruption to critical infrastructure",
    IncidentSeverity.FUNDAMENTAL_RIGHTS_INFRINGEMENT: "Infringement of fundamental-rights obligations",
    IncidentSeverity.PROPERTY_OR_ENVIRONMENT_HARM: "Serious harm to property or the environment",
    IncidentSeverity.WIDESPREAD_INFRINGEMENT: "Widespread infringement (cross-border, multiple people affected)",
}


@dataclass(frozen=True)
class IncidentSummary:
    id: str
    ai_system_id: str
    severity: IncidentSeverity
    severity_label: str
    description: str
    detected_at: date
    deadline: date
    citation: str
    citation_text: str
    reported_at: datetime | None
    is_overdue: bool


def _to_summary(session: Session, incident: Incident, *, today: date) -> IncidentSummary:
    deadline = incident.detected_at + timedelta(days=SEVERITY_DEADLINE_DAYS[incident.severity])
    citation = SEVERITY_CITATIONS[incident.severity]
    # Article 73 is ingested as a single provision (point-level splitting deferred, same
    # as Article 5's points), so the verbatim text lookup is always against "Article 73"
    # even though `citation` displays the more specific paragraph.
    return IncidentSummary(
        id=incident.id,
        ai_system_id=incident.ai_system_id,
        severity=incident.severity,
        severity_label=SEVERITY_LABELS[incident.severity],
        description=incident.description,
        detected_at=incident.detected_at,
        deadline=deadline,
        citation=citation,
        citation_text=find_provision_text_by_citation(session, "Article 73") or "Full text unavailable.",
        reported_at=incident.reported_at,
        is_overdue=incident.reported_at is None and deadline < today,
    )


def create_incident(
    session: Session, *, ai_system_id: str, severity: IncidentSeverity, description: str, detected_at: date
) -> Incident:
    incident = Incident(
        ai_system_id=ai_system_id, severity=severity, description=description, detected_at=detected_at
    )
    session.add(incident)
    session.commit()
    return incident


def mark_reported(session: Session, incident_id: str) -> Incident | None:
    incident = session.get(Incident, incident_id)
    if incident is None:
        return None
    incident.reported_at = datetime.now(timezone.utc)
    session.commit()
    return incident


def list_incidents_for_system(
    session: Session, ai_system_id: str, *, today: date | None = None
) -> list[IncidentSummary]:
    """Unreported incidents first (soonest deadline first), then reported ones."""
    today = today or date.today()
    incidents = session.scalars(
        select(Incident).where(Incident.ai_system_id == ai_system_id)
    ).all()
    summaries = [_to_summary(session, i, today=today) for i in incidents]
    summaries.sort(key=lambda s: (s.reported_at is not None, s.deadline))
    return summaries


def list_all_open_incidents(session: Session, *, today: date | None = None) -> list[IncidentSummary]:
    """Every unreported incident across every AI system, soonest deadline first --
    for a dashboard that doesn't require opening each system individually."""
    today = today or date.today()
    incidents = session.scalars(select(Incident).where(Incident.reported_at.is_(None))).all()
    summaries = [_to_summary(session, i, today=today) for i in incidents]
    summaries.sort(key=lambda s: s.deadline)
    return summaries
