"""Adversarial cross-tenant isolation.

`.claude/rules/security.md` ranks cross-tenant leakage as a primary risk, and
docs/security-model.md carried "tenant isolation is out of scope" as a known gap for six
phases. This file is what closes it, so it is written to attack the boundary rather than
demonstrate it.

The load-bearing property is not "the queries in src/ remember to filter by tenant" --
it is that **a query which forgets cannot leak anyway**. Several tests below therefore
call the ordinary domain functions with no tenant-specific arguments at all, and one
(`test_a_deliberately_unfiltered_query_still_cannot_leak`) issues a raw unfiltered SELECT
on purpose. If someone later rips out src/persistence/tenancy.py and reverts to manual
`.where(tenant_id == ...)` discipline, that test fails while everything else keeps
passing -- which is the point.
"""

from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from schemas.classification import CategoryClassification, CitedRequirement, ClassificationResult
from schemas.enums import ClassificationCategory, ClassificationState, IncidentSeverity
from schemas.facts import ExtractedFacts
from src.incidents.registry import create_incident, list_all_open_incidents, list_incidents_for_system
from src.legal.deadlines import list_all_deadlines
from src.legal.ingest import ingest_seed
from src.legal.queries import find_requirement_by_key
from src.legal.update_alerts import list_update_alerts
from src.observability.assessment_log import list_recent_assessments, reconstruct_assessment
from src.observability.retention import delete_assessment
from src.persistence.models import AISystem, AssessmentRecord, Incident
from src.persistence.tenancy import (
    CrossTenantWriteError,
    TenantContextError,
    bind_tenant,
    cross_tenant_context,
    tenant_context,
)
from src.systems.registry import get_ai_system, get_or_create_ai_system, list_ai_systems
from tests.conftest import OTHER_TENANT_ID, PRIMARY_TENANT_ID


def _classification() -> ClassificationResult:
    return ClassificationResult(
        assessments=[
            CategoryClassification(
                category=category,
                state=ClassificationState.YES if category == ClassificationCategory.HIGH_RISK else ClassificationState.NO,
                cited_requirements=(
                    [CitedRequirement(requirement_key="EU-AI-ACT-ANNEXIII-4", citation="Annex III", relevance="x")]
                    if category == ClassificationCategory.HIGH_RISK
                    else []
                ),
                rationale="x",
                confidence=0.9,
            )
            for category in ClassificationCategory
        ]
    )


def _populate(session: Session, tenant_id: str, label: str) -> dict[str, str]:
    """Create a full object graph (system + assessment + incident) owned by `tenant_id`."""
    from src.observability.assessment_log import record_assessment

    with tenant_context(session, tenant_id):
        system = get_or_create_ai_system(session, f"{label} System")
        assessment_id = record_assessment(
            session,
            as_of=date(2026, 9, 9),
            legal_knowledge_source_key="eu_ai_act_2024_1689",
            facts=ExtractedFacts(system_description=f"{label} description", intended_purpose="x"),
            classification=_classification(),
            obligations=[],
            evidence_assessments=[],
            gaps=[],
            review_flags=[],
            llm_calls=[],
            ai_system_id=system.id,
        )
        incident = create_incident(
            session,
            ai_system_id=system.id,
            severity=IncidentSeverity.CRITICAL_INFRASTRUCTURE_DISRUPTION,
            description=f"{label} incident",
            detected_at=date(2026, 9, 1),
        )
        return {"system_id": system.id, "assessment_id": assessment_id, "incident_id": incident.id}


@pytest.fixture
def two_tenants(session):
    """Tenant A (the fixture's primary) and Tenant B each own a full object graph."""
    ingest_seed(session)  # legal corpus is shared, not tenant-owned
    a = _populate(session, PRIMARY_TENANT_ID, "Alpha")
    b = _populate(session, OTHER_TENANT_ID, "Bravo")
    bind_tenant(session, PRIMARY_TENANT_ID)  # act as A for the assertions
    return a, b


# --- reads: the ordinary domain functions, unmodified ------------------------------

def test_listing_systems_shows_only_your_own(two_tenants, session):
    a, _b = two_tenants

    systems = list_ai_systems(session)

    assert [s.id for s in systems] == [a["system_id"]]
    assert all("Bravo" not in s.name for s in systems)


def test_listing_assessments_shows_only_your_own(two_tenants, session):
    a, _b = two_tenants

    assessments = list_recent_assessments(session)

    assert [x.assessment_id for x in assessments] == [a["assessment_id"]]


def test_listing_open_incidents_shows_only_your_own(two_tenants, session):
    a, _b = two_tenants

    incidents = list_all_open_incidents(session)

    assert [i.id for i in incidents] == [a["incident_id"]]


def test_deadlines_dashboard_covers_only_your_own_systems(two_tenants, session):
    a, _b = two_tenants

    deadlines = list_all_deadlines(session)

    assert [d.ai_system_id for d in deadlines] == [a["system_id"]]


def test_update_alerts_cover_only_your_own_systems(two_tenants, session):
    from src.legal.versioning import supersede_requirement
    from src.persistence.models import Requirement

    _a, _b = two_tenants
    old = session.query(Requirement).filter_by(
        requirement_key="EU-AI-ACT-ANNEXIII-4", superseded_by_id=None
    ).one()
    supersede_requirement(
        session, old=old, new_summary="Updated.", new_primary_provision_id=old.primary_provision_id
    )

    alerts = list_update_alerts(session)

    # Both tenants have a stale assessment, but you only ever hear about your own.
    assert [alert.ai_system_id for alert in alerts] == [two_tenants[0]["system_id"]]


def test_counts_are_scoped_not_global(two_tenants, session):
    """Both tenants have exactly one of each, so an unscoped count would read 2."""
    assert session.scalar(select(func.count(AISystem.id))) == 1
    assert session.scalar(select(func.count(AssessmentRecord.id))) == 1
    assert session.scalar(select(func.count(Incident.id))) == 1


# --- IDOR: knowing another tenant's id must not be enough --------------------------

def test_fetching_another_tenants_system_by_id_returns_nothing(two_tenants, session):
    _a, b = two_tenants

    assert get_ai_system(session, b["system_id"]) is None


def test_reconstructing_another_tenants_assessment_returns_nothing(two_tenants, session):
    _a, b = two_tenants

    assert reconstruct_assessment(session, b["assessment_id"]) is None


def test_listing_incidents_for_another_tenants_system_returns_nothing(two_tenants, session):
    _a, b = two_tenants

    assert list_incidents_for_system(session, b["system_id"]) == []


def test_deleting_another_tenants_assessment_is_a_no_op(two_tenants, session):
    _a, b = two_tenants

    assert delete_assessment(session, b["assessment_id"]) is False

    # ...and it is genuinely still there, not merely reported as absent.
    with cross_tenant_context(session):
        assert session.get(AssessmentRecord, b["assessment_id"]) is not None


# --- writes ------------------------------------------------------------------------

def test_inserting_a_row_for_another_tenant_is_refused(two_tenants, session):
    session.add(AISystem(name="Smuggled", tenant_id=OTHER_TENANT_ID))

    with pytest.raises(CrossTenantWriteError):
        session.flush()
    session.rollback()


def test_modifying_another_tenants_row_is_refused(two_tenants, session):
    _a, b = two_tenants
    with cross_tenant_context(session):
        victim = session.get(AISystem, b["system_id"])
    victim.name = "Renamed by the wrong tenant"

    with pytest.raises(CrossTenantWriteError):
        session.flush()
    session.rollback()


def test_new_rows_are_stamped_with_the_bound_tenant_automatically(two_tenants, session):
    """No caller passes tenant_id -- get_or_create_ai_system doesn't even take one."""
    created = get_or_create_ai_system(session, "Freshly Created")

    assert created.tenant_id == PRIMARY_TENANT_ID


# --- the guard itself ---------------------------------------------------------------

def test_a_deliberately_unfiltered_query_still_cannot_leak(two_tenants, session):
    """The property the whole design rests on: this query has no tenant predicate at all,
    which is exactly what a future contributor would write by mistake."""
    rows = session.scalars(select(AISystem)).all()

    assert [r.id for r in rows] == [two_tenants[0]["system_id"]]


def test_querying_with_no_tenant_bound_raises_rather_than_returning_everything(session):
    ingest_seed(session)
    unbound = Session(session.bind)

    with pytest.raises(TenantContextError):
        unbound.scalars(select(AISystem)).all()


def test_the_leaky_count_shape_is_rejected_outright(two_tenants, session):
    """select(func.count()).select_from(X) silently counts every tenant, because the
    filter has no entity to attach to. It must fail loudly instead."""
    with pytest.raises(TenantContextError, match="buried in a subquery"):
        session.scalar(select(func.count()).select_from(AISystem))

    with pytest.raises(TenantContextError, match="buried in a subquery"):
        session.query(AISystem).count()


def test_legal_corpus_is_readable_with_no_tenant_bound(session):
    """The public /ai-risk-check depends on this: shared reference data must not require
    a tenant, or the unauthenticated endpoint could not classify anything."""
    ingest_seed(session)
    unbound = Session(session.bind)

    assert find_requirement_by_key(unbound, "EU-AI-ACT-ART9") is not None
