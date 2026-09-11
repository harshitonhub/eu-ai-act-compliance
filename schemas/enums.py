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
