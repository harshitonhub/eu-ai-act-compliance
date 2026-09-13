"""Shared enums for structured LLM outputs and persistence.

Defined once here (schemas/ sits above src/, per docs/architecture.md) so the
classification/evidence taxonomies in CLAUDE.md can't drift between the DB layer and
the LLM output layer.
"""

from __future__ import annotations

import enum


class ActorRole(str, enum.Enum):
    PROVIDER = "provider"
    DEPLOYER = "deployer"
    IMPORTER = "importer"
    DISTRIBUTOR = "distributor"
    ANY = "any"


class ClassificationCategory(str, enum.Enum):
    SCOPE = "scope"
    PROHIBITED_PRACTICES = "prohibited_practices"
    HIGH_RISK = "high_risk"
    GPAI = "gpai"
    TRANSPARENCY = "transparency"


class ClassificationState(str, enum.Enum):
    YES = "YES"
    NO = "NO"
    POSSIBLY = "POSSIBLY"
    INSUFFICIENT_INFORMATION = "INSUFFICIENT_INFORMATION"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class EvidenceStatus(str, enum.Enum):
    COMPLIANT = "COMPLIANT"
    PARTIALLY_COMPLIANT = "PARTIALLY_COMPLIANT"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    NON_COMPLIANT = "NON_COMPLIANT"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class EvidenceDimension(str, enum.Enum):
    RELEVANCE = "relevance"
    COMPLETENESS = "completeness"
    SPECIFICITY = "specificity"
    CURRENCY = "currency"
    TRACEABILITY = "traceability"
    CONSISTENCY = "consistency"
    SUFFICIENCY = "sufficiency"


class UserRole(str, enum.Enum):
    """Least-privilege ladder. ADMIN is the only role that can manage users; VIEWER is
    read-only, so an auditor can be given access without the ability to alter the record
    they are auditing. See src/api/auth.py for where each is enforced."""

    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class IncidentSeverity(str, enum.Enum):
    """The four Article 3(49) 'serious incident' categories plus Article 3(61)
    'widespread infringement' -- together, every category Article 73 sets a distinct
    reporting deadline for. See src/incidents/registry.py for the deadline mapping."""

    DEATH_OR_SERIOUS_HEALTH_HARM = "death_or_serious_health_harm"  # Art 3(49)(a)
    CRITICAL_INFRASTRUCTURE_DISRUPTION = "critical_infrastructure_disruption"  # Art 3(49)(b)
    FUNDAMENTAL_RIGHTS_INFRINGEMENT = "fundamental_rights_infringement"  # Art 3(49)(c)
    PROPERTY_OR_ENVIRONMENT_HARM = "property_or_environment_harm"  # Art 3(49)(d)
    WIDESPREAD_INFRINGEMENT = "widespread_infringement"  # Art 3(61)
