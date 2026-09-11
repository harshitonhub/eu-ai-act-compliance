"""Adversarial scenario: outdated legal sources.

Scenario: a legal requirement is amended (superseded). An attacker -- or just a stale
cache/retrieval bug -- could cause the system to keep citing the old, no-longer-current
version of that requirement in a new assessment.

Expected behavior: once superseded, the old requirement version is permanently excluded
from every active-corpus query (find_requirements, retrieve), regardless of query text
or `as_of` date; only the new version is citable.

Root cause this guards against: `find_requirements`/`retrieve` filtering on
`Requirement.superseded_by_id.is_(None)` being accidentally dropped in a future change.

Regression test: this file.
"""

from datetime import date

from src.legal.ingest import ingest_seed
from src.legal.queries import find_requirement_by_key, find_requirements
from src.legal.versioning import supersede_requirement
from src.retrieval.retrieval import retrieve
from src.persistence.models import Requirement


def test_superseded_requirement_excluded_from_find_requirements(session):
    ingest_seed(session)
    old = session.query(Requirement).filter_by(requirement_key="EU-AI-ACT-ART9").one()
    supersede_requirement(
        session,
        old=old,
        new_summary="Amended risk management system requirement.",
        new_primary_provision_id=old.primary_provision_id,
    )

    results = find_requirements(session, as_of=date(2026, 9, 9))
    art9_results = [r for r in results if r.requirement_key == "EU-AI-ACT-ART9"]

    assert len(art9_results) == 1
    assert art9_results[0].summary == "Amended risk management system requirement."


def test_superseded_requirement_excluded_from_keyword_retrieval(session):
    ingest_seed(session)
    old = session.query(Requirement).filter_by(requirement_key="EU-AI-ACT-ART9").one()
    supersede_requirement(
        session, old=old, new_summary="Amended risk management text.", new_primary_provision_id=old.primary_provision_id
    )

    results = retrieve(
        session, query_text="risk management system", requirement_key_prefixes=("EU-AI-ACT-ART9",)
    )

    assert len(results) == 1
    assert results[0].summary == "Amended risk management text."


def test_find_requirement_by_key_returns_only_the_current_version(session):
    ingest_seed(session)
    old = session.query(Requirement).filter_by(requirement_key="EU-AI-ACT-ART10").one()
    new = supersede_requirement(
        session, old=old, new_summary="Amended data governance text.", new_primary_provision_id=old.primary_provision_id
    )

    result = find_requirement_by_key(session, "EU-AI-ACT-ART10")

    assert result.summary == "Amended data governance text."
    assert new.version == old.version + 1
