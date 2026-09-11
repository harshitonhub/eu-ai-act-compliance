import pytest

from src.legal.ingest import ingest_seed
from src.legal.queries import find_requirement_by_key
from src.legal.versioning import supersede_requirement
from src.persistence.models import Requirement


def test_supersede_creates_new_version_and_preserves_old(session):
    ingest_seed(session)
    old = session.query(Requirement).filter_by(requirement_key="EU-AI-ACT-ART5-1-A").one()
    old_id, old_summary = old.id, old.summary

    new = supersede_requirement(
        session,
        old=old,
        new_summary="Updated summary text.",
        new_primary_provision_id=old.primary_provision_id,
    )

    session.refresh(old)
    assert old.id == old_id
    assert old.summary == old_summary  # old row untouched
    assert old.superseded_by_id == new.id

    assert new.requirement_key == old.requirement_key
    assert new.version == old.version + 1
    assert new.summary == "Updated summary text."
    assert new.superseded_by_id is None


def test_supersede_carries_forward_applicability_conditions_and_exceptions(session):
    """Regression test: without copying ApplicabilityCondition rows forward, the new
    version has none, and find_requirement_by_key/find_requirements (both INNER JOIN on
    ApplicabilityCondition) would return nothing for it -- the requirement would
    effectively vanish after being superseded rather than being updated.
    """
    ingest_seed(session)
    old = session.query(Requirement).filter_by(requirement_key="EU-AI-ACT-ART5-1-D").one()  # has an exception

    supersede_requirement(
        session, old=old, new_summary="Updated summary.", new_primary_provision_id=old.primary_provision_id
    )

    result = find_requirement_by_key(session, "EU-AI-ACT-ART5-1-D")
    assert result is not None
    assert result.summary == "Updated summary."
    assert len(result.exceptions) == 1  # the original exception carried forward too


def test_cannot_supersede_an_already_superseded_requirement(session):
    ingest_seed(session)
    old = session.query(Requirement).filter_by(requirement_key="EU-AI-ACT-ART5-1-A").one()
    supersede_requirement(
        session, old=old, new_summary="v2", new_primary_provision_id=old.primary_provision_id
    )

    with pytest.raises(ValueError):
        supersede_requirement(
            session, old=old, new_summary="v3", new_primary_provision_id=old.primary_provision_id
        )
