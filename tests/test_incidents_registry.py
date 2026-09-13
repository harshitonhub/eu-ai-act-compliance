from datetime import date

from sqlalchemy import func, select

from schemas.enums import IncidentSeverity
from src.incidents.registry import (
    create_incident,
    list_all_open_incidents,
    list_incidents_for_system,
    mark_reported,
)
from src.legal.ingest import ingest_seed
from src.persistence.models import Incident
from src.systems.registry import get_or_create_ai_system


def test_create_incident_persists_row(session):
    ingest_seed(session)
    system = get_or_create_ai_system(session, "Resume Screener")

    incident = create_incident(
        session,
        ai_system_id=system.id,
        severity=IncidentSeverity.FUNDAMENTAL_RIGHTS_INFRINGEMENT,
        description="Candidate flagged the system rejected them without explanation.",
        detected_at=date(2026, 9, 1),
    )

    assert session.scalar(select(func.count(Incident.id))) == 1
    assert incident.ai_system_id == system.id


def test_deadline_is_fifteen_days_for_default_severity(session):
    ingest_seed(session)
    system = get_or_create_ai_system(session, "Resume Screener")
    create_incident(
        session,
        ai_system_id=system.id,
        severity=IncidentSeverity.FUNDAMENTAL_RIGHTS_INFRINGEMENT,
        description="x",
        detected_at=date(2026, 9, 1),
    )

    summaries = list_incidents_for_system(session, system.id, today=date(2026, 9, 5))

    assert summaries[0].deadline == date(2026, 9, 16)
    assert summaries[0].citation == "Article 73(2)"
    assert summaries[0].is_overdue is False


def test_deadline_is_two_days_for_critical_infrastructure(session):
    ingest_seed(session)
    system = get_or_create_ai_system(session, "Traffic Controller")
    create_incident(
        session,
        ai_system_id=system.id,
        severity=IncidentSeverity.CRITICAL_INFRASTRUCTURE_DISRUPTION,
        description="x",
        detected_at=date(2026, 9, 1),
    )

    summaries = list_incidents_for_system(session, system.id, today=date(2026, 9, 5))

    assert summaries[0].deadline == date(2026, 9, 3)
    assert summaries[0].citation == "Article 73(3)"
    assert summaries[0].is_overdue is True  # today (9/5) is past the 9/3 deadline


def test_deadline_is_ten_days_for_death_or_serious_health_harm(session):
    ingest_seed(session)
    system = get_or_create_ai_system(session, "Medical Triage")
    create_incident(
        session,
        ai_system_id=system.id,
        severity=IncidentSeverity.DEATH_OR_SERIOUS_HEALTH_HARM,
        description="x",
        detected_at=date(2026, 9, 1),
    )

    summaries = list_incidents_for_system(session, system.id, today=date(2026, 9, 5))

    assert summaries[0].deadline == date(2026, 9, 11)
    assert summaries[0].citation == "Article 73(4)"


def test_widespread_infringement_also_gets_two_day_deadline(session):
    ingest_seed(session)
    system = get_or_create_ai_system(session, "Ad Targeting")
    create_incident(
        session,
        ai_system_id=system.id,
        severity=IncidentSeverity.WIDESPREAD_INFRINGEMENT,
        description="x",
        detected_at=date(2026, 9, 1),
    )

    summaries = list_incidents_for_system(session, system.id, today=date(2026, 9, 2))

    assert summaries[0].deadline == date(2026, 9, 3)
    assert summaries[0].citation == "Article 73(3)"


def test_citation_text_is_verbatim_from_ingested_provision(session):
    ingest_seed(session)
    system = get_or_create_ai_system(session, "Resume Screener")
    create_incident(
        session,
        ai_system_id=system.id,
        severity=IncidentSeverity.DEATH_OR_SERIOUS_HEALTH_HARM,
        description="x",
        detected_at=date(2026, 9, 1),
    )

    summaries = list_incidents_for_system(session, system.id)

    assert "not later than 10 days" in summaries[0].citation_text


def test_mark_reported_clears_overdue_status(session):
    ingest_seed(session)
    system = get_or_create_ai_system(session, "Traffic Controller")
    incident = create_incident(
        session,
        ai_system_id=system.id,
        severity=IncidentSeverity.CRITICAL_INFRASTRUCTURE_DISRUPTION,
        description="x",
        detected_at=date(2026, 9, 1),
    )

    mark_reported(session, incident.id)

    summaries = list_incidents_for_system(session, system.id, today=date(2026, 9, 30))
    assert summaries[0].reported_at is not None
    assert summaries[0].is_overdue is False


def test_mark_reported_returns_none_for_unknown_incident(session):
    assert mark_reported(session, "not-a-real-id") is None


def test_unreported_incidents_sort_before_reported_by_soonest_deadline(session):
    ingest_seed(session)
    system = get_or_create_ai_system(session, "Resume Screener")
    reported = create_incident(
        session,
        ai_system_id=system.id,
        severity=IncidentSeverity.CRITICAL_INFRASTRUCTURE_DISRUPTION,
        description="already handled",
        detected_at=date(2026, 8, 1),
    )
    mark_reported(session, reported.id)
    later_unreported = create_incident(
        session,
        ai_system_id=system.id,
        severity=IncidentSeverity.FUNDAMENTAL_RIGHTS_INFRINGEMENT,
        description="still open",
        detected_at=date(2026, 9, 1),
    )

    summaries = list_incidents_for_system(session, system.id, today=date(2026, 9, 5))

    assert [s.id for s in summaries] == [later_unreported.id, reported.id]


def test_list_all_open_incidents_excludes_reported_and_sorts_by_deadline(session):
    ingest_seed(session)
    system_a = get_or_create_ai_system(session, "System A")
    system_b = get_or_create_ai_system(session, "System B")

    urgent = create_incident(
        session,
        ai_system_id=system_a.id,
        severity=IncidentSeverity.CRITICAL_INFRASTRUCTURE_DISRUPTION,
        description="urgent",
        detected_at=date(2026, 9, 1),
    )
    less_urgent = create_incident(
        session,
        ai_system_id=system_b.id,
        severity=IncidentSeverity.FUNDAMENTAL_RIGHTS_INFRINGEMENT,
        description="less urgent",
        detected_at=date(2026, 9, 1),
    )
    already_reported = create_incident(
        session,
        ai_system_id=system_a.id,
        severity=IncidentSeverity.DEATH_OR_SERIOUS_HEALTH_HARM,
        description="handled",
        detected_at=date(2026, 8, 1),
    )
    mark_reported(session, already_reported.id)

    open_incidents = list_all_open_incidents(session, today=date(2026, 9, 5))

    assert [i.id for i in open_incidents] == [urgent.id, less_urgent.id]
