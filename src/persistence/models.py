from __future__ import annotations

import enum
import uuid
from datetime import date, datetime, UTC

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from schemas.enums import ActorRole, IncidentSeverity, UserRole
from src.persistence.tenancy import TenantScoped


def _uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class SourceDocument(Base):
    """An authoritative legal source document (e.g. a Regulation as published on EUR-Lex).

    Append-only: a new publication/consolidation of the same instrument is a new row,
    never an in-place edit of an existing one.
    """

    __tablename__ = "source_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    source_key: Mapped[str] = mapped_column(String(128), unique=True)
    celex_id: Mapped[str] = mapped_column(String(32))
    official_title: Mapped[str] = mapped_column(Text)
    oj_reference: Mapped[str] = mapped_column(String(128))
    date_of_act: Mapped[date] = mapped_column(Date)
    date_published: Mapped[date] = mapped_column(Date)
    date_entry_into_force: Mapped[date] = mapped_column(Date)
    source_url: Mapped[str] = mapped_column(Text)
    raw_fetch_sha256: Mapped[str] = mapped_column(String(64))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    provisions: Mapped[list[LegalProvision]] = relationship(back_populates="source_document")


class LegalProvision(Base):
    """A citable unit of legal text (an article, paragraph, point, or annex entry) copied verbatim.

    Versioned: an amendment creates a new row with version = old.version + 1 and sets
    old.superseded_by_id; the old row is never deleted or overwritten.
    """

    __tablename__ = "legal_provisions"
    __table_args__ = (UniqueConstraint("citation", "version", name="uq_provision_citation_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    source_document_id: Mapped[str] = mapped_column(ForeignKey("source_documents.id"))
    citation: Mapped[str] = mapped_column(String(128))  # e.g. "Article 5(1)(a)", "Annex III point 1(a)"
    heading: Mapped[str | None] = mapped_column(Text, nullable=True)
    text: Mapped[str] = mapped_column(Text)  # verbatim source text, never LLM-paraphrased
    effective_date: Mapped[date] = mapped_column(Date)
    version: Mapped[int] = mapped_column(default=1)
    superseded_by_id: Mapped[str | None] = mapped_column(
        ForeignKey("legal_provisions.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    source_document: Mapped[SourceDocument] = relationship(back_populates="provisions")


class Requirement(Base):
    """A structured, queryable legal requirement derived from one or more LegalProvisions.

    Stable `requirement_key` persists across legal updates; `version` and `superseded_by_id`
    track changes to the requirement's own summary/scope without breaking historical
    assessments that cite this requirement.
    """

    __tablename__ = "requirements"
    __table_args__ = (UniqueConstraint("requirement_key", "version", name="uq_requirement_key_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    requirement_key: Mapped[str] = mapped_column(String(128))  # stable across versions, e.g. EU-AI-ACT-ART5-1-A
    version: Mapped[int] = mapped_column(default=1)
    summary: Mapped[str] = mapped_column(Text)  # engineer-authored restatement; verbatim provision is authoritative
    primary_provision_id: Mapped[str] = mapped_column(ForeignKey("legal_provisions.id"))
    superseded_by_id: Mapped[str | None] = mapped_column(ForeignKey("requirements.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    primary_provision: Mapped[LegalProvision] = relationship()
    applicability_conditions: Mapped[list[ApplicabilityCondition]] = relationship(
        back_populates="requirement"
    )
    exceptions: Mapped[list[LegalException]] = relationship(back_populates="requirement")


class ApplicabilityCondition(Base):
    """Structured applicability metadata for a Requirement.

    All fields are nullable/independent so a condition can express "applies to any actor
    role" (actor_role=None) vs. a specific one, per legal-reasoning.md: applicability is
    contextual, not a single flag.
    """

    __tablename__ = "applicability_conditions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    requirement_id: Mapped[str] = mapped_column(ForeignKey("requirements.id"))
    actor_role: Mapped[ActorRole | None] = mapped_column(Enum(ActorRole), nullable=True)
    sector: Mapped[str | None] = mapped_column(String(128), nullable=True)
    annex_iii_category: Mapped[str | None] = mapped_column(String(8), nullable=True)  # "1".."8"
    temporal_start: Mapped[date] = mapped_column(Date)
    temporal_end: Mapped[date | None] = mapped_column(Date, nullable=True)

    requirement: Mapped[Requirement] = relationship(back_populates="applicability_conditions")


class LegalException(Base):
    """A legally-grounded exception/carve-out to a Requirement, quoted verbatim."""

    __tablename__ = "exceptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    requirement_id: Mapped[str] = mapped_column(ForeignKey("requirements.id"))
    description: Mapped[str] = mapped_column(Text)  # verbatim quote of the exception clause
    source_provision_id: Mapped[str] = mapped_column(ForeignKey("legal_provisions.id"))

    requirement: Mapped[Requirement] = relationship(back_populates="exceptions")
    source_provision: Mapped[LegalProvision] = relationship()


class FrameworkCrosswalk(Base):
    """A voluntary-framework citation crosswalked to an existing binding Requirement.

    Not a new obligation -- an annotation showing the same obligation also satisfies a
    voluntary framework's control (e.g. NIST AI RMF GOVERN 1.4), shown alongside the
    obligation rather than triggering a parallel classification. See ROADMAP.md's
    "Multi-framework scope" section for why voluntary frameworks (NIST) get this
    treatment while binding law (GDPR) gets new Requirement rows instead.
    """

    __tablename__ = "framework_crosswalks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    requirement_id: Mapped[str] = mapped_column(ForeignKey("requirements.id"))
    framework_name: Mapped[str] = mapped_column(String(64))  # e.g. "NIST AI RMF 1.0"
    citation: Mapped[str] = mapped_column(String(64))  # e.g. "GOVERN 1.4"
    citation_text: Mapped[str] = mapped_column(Text)  # verbatim subcategory text, never LLM-paraphrased
    source_url: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    requirement: Mapped[Requirement] = relationship()


class RetrievalMethod(str, enum.Enum):
    MANUAL = "manual"
    AUTOMATED = "automated"


class EntityType(str, enum.Enum):
    SOURCE_DOCUMENT = "source_document"
    PROVISION = "provision"
    REQUIREMENT = "requirement"


class ProvenanceRecord(Base):
    """Immutable record of where a legal entity's text came from and how it was retrieved."""

    __tablename__ = "provenance_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    entity_type: Mapped[EntityType] = mapped_column(Enum(EntityType))
    entity_id: Mapped[str] = mapped_column(String(36))
    source_document_id: Mapped[str] = mapped_column(ForeignKey("source_documents.id"))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime)
    retrieval_method: Mapped[RetrievalMethod] = mapped_column(Enum(RetrievalMethod))
    url: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class Tenant(Base):
    """An isolated customer workspace. Every tenant-owned row FKs back here, and
    src/persistence/tenancy.py enforces that no query crosses the boundary."""

    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class User(Base):
    """A login belonging to exactly one tenant.

    Deliberately *not* TenantScoped: authentication has to find the user by email before
    any tenant context exists -- that's the lookup that establishes it. Tenant scoping of
    user administration is enforced explicitly in src/auth/users.py instead, which is why
    that module is the one place querying this table.
    """

    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email", name="uq_user_email"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), index=True)
    email: Mapped[str] = mapped_column(String(320))
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    tenant: Mapped[Tenant] = relationship()


class AISystem(Base, TenantScoped):
    """A named AI system a user tracks assessments against (Phase A registry).

    Assessments aren't required to belong to one -- `AssessmentRecord.ai_system_id` is
    nullable so ungrouped/ad-hoc assessments stay valid.
    """

    __tablename__ = "ai_systems"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(256))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class Incident(Base, TenantScoped):
    """A serious incident reported (or awaiting report) for an AI system, per Article 73.

    Unlike AssessmentRecord.ai_system_id, this FK is required -- an incident always
    belongs to exactly one system (Phase E). `detected_at` is when the provider/deployer
    became aware, per Article 73(2)-(4): that date, not the report date, is what starts
    the reporting-deadline countdown -- see src/incidents/registry.py.
    """

    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    ai_system_id: Mapped[str] = mapped_column(ForeignKey("ai_systems.id"))
    severity: Mapped[IncidentSeverity] = mapped_column(Enum(IncidentSeverity))
    description: Mapped[str] = mapped_column(Text)
    detected_at: Mapped[date] = mapped_column(Date)
    reported_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))


class AssessmentRecord(Base, TenantScoped):
    """Everything needed to reconstruct a past assessment, per the mandate's
    "Observability and reproducibility" list. Nested objects (facts, classification,
    obligations, evidence, gaps, review flags, LLM call log) are stored as JSON text
    columns rather than a normalized schema -- they're written once and read back whole
    (never queried by sub-field), so normalization would add migration surface for no
    query benefit.
    """

    __tablename__ = "assessment_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    ai_system_id: Mapped[str | None] = mapped_column(ForeignKey("ai_systems.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    as_of: Mapped[date] = mapped_column(Date)
    legal_knowledge_source_key: Mapped[str] = mapped_column(String(128))
    facts_json: Mapped[str] = mapped_column(Text)
    classification_json: Mapped[str] = mapped_column(Text)
    obligations_json: Mapped[str] = mapped_column(Text)
    evidence_assessments_json: Mapped[str] = mapped_column(Text)
    gaps_json: Mapped[str] = mapped_column(Text)
    review_flags_json: Mapped[str] = mapped_column(Text)
    llm_calls_json: Mapped[str] = mapped_column(Text)
    total_input_tokens: Mapped[int] = mapped_column(default=0)
    total_output_tokens: Mapped[int] = mapped_column(default=0)
    total_latency_ms: Mapped[float] = mapped_column(default=0.0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
