"""Deterministic read queries over the legal knowledge tables. No LLM calls in this module."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from schemas.enums import ActorRole
from src.persistence.models import (
    ApplicabilityCondition,
    FrameworkCrosswalk,
    LegalException,
    LegalProvision,
    Requirement,
)


@dataclass(frozen=True)
class RequirementResult:
    requirement_key: str
    summary: str
    citation: str
    provision_text: str
    exceptions: tuple[str, ...]


@dataclass(frozen=True)
class CrosswalkResult:
    framework_name: str
    citation: str
    citation_text: str
    source_url: str


def find_requirements(
    session: Session,
    *,
    annex_iii_category: str | None = None,
    actor_role: ActorRole | None = None,
    as_of: date | None = None,
) -> list[RequirementResult]:
    """Return requirements matching the given applicability filters, with citations.

    A filter set to None is not applied. `as_of` restricts to requirements whose
    applicability window (temporal_start <= as_of <= temporal_end-or-open) covers that date.
    """
    stmt = (
        select(Requirement, ApplicabilityCondition, LegalProvision)
        .join(ApplicabilityCondition, ApplicabilityCondition.requirement_id == Requirement.id)
        .join(LegalProvision, LegalProvision.id == Requirement.primary_provision_id)
        .where(Requirement.superseded_by_id.is_(None))
    )
    if annex_iii_category is not None:
        stmt = stmt.where(ApplicabilityCondition.annex_iii_category == annex_iii_category)
    if actor_role is not None:
        stmt = stmt.where(
            (ApplicabilityCondition.actor_role == actor_role)
            | (ApplicabilityCondition.actor_role == ActorRole.ANY)
        )
    if as_of is not None:
        stmt = stmt.where(ApplicabilityCondition.temporal_start <= as_of).where(
            (ApplicabilityCondition.temporal_end.is_(None)) | (ApplicabilityCondition.temporal_end >= as_of)
        )

    results = []
    for requirement, _condition, provision in session.execute(stmt).all():
        exceptions = session.scalars(
            select(LegalException.description).where(LegalException.requirement_id == requirement.id)
        ).all()
        results.append(
            RequirementResult(
                requirement_key=requirement.requirement_key,
                summary=requirement.summary,
                citation=provision.citation,
                provision_text=provision.text,
                exceptions=tuple(exceptions),
            )
        )
    return results


def find_requirement_by_key(session: Session, requirement_key: str) -> RequirementResult | None:
    """Exact lookup of the current (non-superseded) version of a requirement, by its stable key."""
    stmt = (
        select(Requirement, LegalProvision)
        .join(LegalProvision, LegalProvision.id == Requirement.primary_provision_id)
        .where(Requirement.requirement_key == requirement_key)
        .where(Requirement.superseded_by_id.is_(None))
    )
    row = session.execute(stmt).first()
    if row is None:
        return None
    requirement, provision = row
    exceptions = session.scalars(
        select(LegalException.description).where(LegalException.requirement_id == requirement.id)
    ).all()
    return RequirementResult(
        requirement_key=requirement.requirement_key,
        summary=requirement.summary,
        citation=provision.citation,
        provision_text=provision.text,
        exceptions=tuple(exceptions),
    )


def find_crosswalks_by_requirement_key(session: Session, requirement_key: str) -> list[CrosswalkResult]:
    """Voluntary-framework crosswalks (e.g. NIST AI RMF) for the current version of a
    requirement, by its stable key. Empty list if the requirement has none or doesn't exist."""
    stmt = (
        select(FrameworkCrosswalk)
        .join(Requirement, Requirement.id == FrameworkCrosswalk.requirement_id)
        .where(Requirement.requirement_key == requirement_key)
        .where(Requirement.superseded_by_id.is_(None))
    )
    return [
        CrosswalkResult(
            framework_name=cw.framework_name,
            citation=cw.citation,
            citation_text=cw.citation_text,
            source_url=cw.source_url,
        )
        for cw in session.scalars(stmt).all()
    ]


def find_provision_text_by_citation(session: Session, citation: str) -> str | None:
    """Verbatim text of the current (non-superseded) version of a standalone provision,
    by its citation -- for provisions ingested without a Requirement layer on top (e.g.
    Article 73, Article 3's definitions), unlike find_requirement_by_key."""
    stmt = (
        select(LegalProvision.text)
        .where(LegalProvision.citation == citation)
        .where(LegalProvision.superseded_by_id.is_(None))
    )
    return session.scalars(stmt).first()
