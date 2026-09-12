"""Deterministic ingestion of the seed legal corpus into the legal knowledge tables:
the EU AI Act slice, GDPR Articles 22/35 (Phase M), NIST AI RMF crosswalks (Phase N),
and NIST CSF crosswalks (Phase O).

No LLM involved anywhere in this module. Legal text is read verbatim from
legal/sources/<source>/*.txt; structured requirements, applicability conditions, and
exceptions below are engineer-authored restatements that cite the verbatim provision
they are derived from, per .claude/rules/legal-reasoning.md.

Idempotent: re-running this against an already-seeded database is a no-op.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from schemas.enums import ActorRole
from src.persistence.models import (
    ApplicabilityCondition,
    EntityType,
    FrameworkCrosswalk,
    LegalException,
    LegalProvision,
    ProvenanceRecord,
    Requirement,
    RetrievalMethod,
    SourceDocument,
)

SOURCES_DIR = Path(__file__).resolve().parents[2] / "legal" / "sources" / "eu_ai_act_2024_1689"
GDPR_SOURCES_DIR = Path(__file__).resolve().parents[2] / "legal" / "sources" / "gdpr_2016_679"
NIST_AI_RMF_SOURCES_DIR = Path(__file__).resolve().parents[2] / "legal" / "sources" / "nist_ai_rmf_1_0"


@dataclass(frozen=True)
class ProvisionSeed:
    citation: str
    heading: str
    text_file: str
    effective_date: date


@dataclass(frozen=True)
class ExceptionSeed:
    description: str
    provision_citation: str


@dataclass(frozen=True)
class RequirementSeed:
    requirement_key: str
    summary: str
    provision_citation: str
    actor_role: ActorRole | None
    annex_iii_category: str | None
    temporal_start: date
    exceptions: tuple[ExceptionSeed, ...] = ()


PROHIBITED_PRACTICES_START = date(2025, 2, 2)  # Chapters I and II, Article 113(a)
HIGH_RISK_GENERAL_START = date(2026, 8, 2)  # general application date, Article 113
ARTICLE_6_1_START = date(2027, 8, 2)  # Article 6(1) and corresponding obligations, Article 113(c)

PROVISION_SEEDS = [
    ProvisionSeed("Article 5", "Prohibited AI practices", "article_5.txt", PROHIBITED_PRACTICES_START),
    ProvisionSeed(
        "Article 6", "Classification rules for high-risk AI systems", "article_6.txt", ARTICLE_6_1_START
    ),
    ProvisionSeed(
        "Annex III", "High-risk AI systems referred to in Article 6(2)", "annex_iii.txt", HIGH_RISK_GENERAL_START
    ),
    # Chapter III, Section 2 -- requirements for high-risk AI systems, applying from the
    # general application date (Article 113); these ground Phase 4's obligation mapping.
    ProvisionSeed("Article 9", "Risk management system", "article_9.txt", HIGH_RISK_GENERAL_START),
    ProvisionSeed("Article 10", "Data and data governance", "article_10.txt", HIGH_RISK_GENERAL_START),
    ProvisionSeed("Article 11", "Technical documentation", "article_11.txt", HIGH_RISK_GENERAL_START),
    ProvisionSeed("Article 12", "Record-keeping", "article_12.txt", HIGH_RISK_GENERAL_START),
    ProvisionSeed(
        "Article 13",
        "Transparency and provision of information to deployers",
        "article_13.txt",
        HIGH_RISK_GENERAL_START,
    ),
    ProvisionSeed("Article 14", "Human oversight", "article_14.txt", HIGH_RISK_GENERAL_START),
    ProvisionSeed(
        "Article 15", "Accuracy, robustness and cybersecurity", "article_15.txt", HIGH_RISK_GENERAL_START
    ),
    # Chapter IX, Section 2 -- incident reporting deadlines, ground Phase E's incident log.
    ProvisionSeed(
        "Article 73", "Reporting of serious incidents", "article_73.txt", HIGH_RISK_GENERAL_START
    ),
    # Chapter I definitions Article 73 references for its deadline tiers -- only these two
    # of Article 3's ~68 points are ingested, each as its own narrow provision.
    ProvisionSeed(
        "Article 3(49)", "Definition: 'serious incident'", "article_3_point_49.txt", PROHIBITED_PRACTICES_START
    ),
    ProvisionSeed(
        "Article 3(61)", "Definition: 'widespread infringement'", "article_3_point_61.txt", PROHIBITED_PRACTICES_START
    ),
]

# One requirement per Section 2 article -- the obligations that attach once a system is
# classified high-risk. Actor role is PROVIDER: Article 8 (not ingested -- see
# docs/legal-methodology.md) establishes this Section's requirements as provider
# obligations; deployer obligations live in Section 3 (Article 26), also not ingested.
HIGH_RISK_OBLIGATION_REQUIREMENTS = [
    RequirementSeed(
        "EU-AI-ACT-ART9",
        "Providers must establish, implement, document, and maintain a risk management "
        "system for the high-risk AI system, run as a continuous iterative process "
        "throughout its lifecycle.",
        "Article 9",
        ActorRole.PROVIDER,
        None,
        HIGH_RISK_GENERAL_START,
    ),
    RequirementSeed(
        "EU-AI-ACT-ART10",
        "Training, validation, and testing data sets must be subject to data governance "
        "practices appropriate to the intended purpose, covering relevant design choices, "
        "data collection, bias examination, and gaps or shortcomings.",
        "Article 10",
        ActorRole.PROVIDER,
        None,
        HIGH_RISK_GENERAL_START,
    ),
    RequirementSeed(
        "EU-AI-ACT-ART11",
        "Providers must draw up technical documentation before the system is placed on "
        "the market or put into service, and keep it up to date, demonstrating compliance "
        "with this Section's requirements.",
        "Article 11",
        ActorRole.PROVIDER,
        None,
        HIGH_RISK_GENERAL_START,
    ),
    RequirementSeed(
        "EU-AI-ACT-ART12",
        "High-risk AI systems must technically allow automatic recording of events (logs) "
        "over the system's lifetime, sufficient to identify risk-relevant situations and "
        "support post-market monitoring.",
        "Article 12",
        ActorRole.PROVIDER,
        None,
        HIGH_RISK_GENERAL_START,
    ),
    RequirementSeed(
        "EU-AI-ACT-ART13",
        "High-risk AI systems must be designed to allow deployers to interpret and use "
        "their output appropriately, with instructions for use covering the information "
        "deployers need for compliant, informed use.",
        "Article 13",
        ActorRole.PROVIDER,
        None,
        HIGH_RISK_GENERAL_START,
    ),
    RequirementSeed(
        "EU-AI-ACT-ART14",
        "High-risk AI systems must be designed to allow effective human oversight during "
        "the period they are in use, including through built-in measures the provider "
        "identifies before market placement and measures deployers can implement.",
        "Article 14",
        ActorRole.PROVIDER,
        None,
        HIGH_RISK_GENERAL_START,
    ),
    RequirementSeed(
        "EU-AI-ACT-ART15",
        "High-risk AI systems must achieve an appropriate level of accuracy, robustness, "
        "and cybersecurity, and perform consistently across their lifecycle, with "
        "resilience against errors, faults, and attempts to exploit vulnerabilities.",
        "Article 15",
        ActorRole.PROVIDER,
        None,
        HIGH_RISK_GENERAL_START,
    ),
]

# Article 5(1) prohibited practices, one requirement per point, citing the full
# Article 5 provision (point-level provision splitting is deferred to a later phase).
PROHIBITED_PRACTICE_REQUIREMENTS = [
    RequirementSeed(
        "EU-AI-ACT-ART5-1-A",
        "Prohibits placing on the market, putting into service, or using an AI system "
        "that deploys subliminal, manipulative, or deceptive techniques that materially "
        "distort a person's behaviour and cause or are reasonably likely to cause significant harm.",
        "Article 5",
        ActorRole.ANY,
        None,
        PROHIBITED_PRACTICES_START,
    ),
    RequirementSeed(
        "EU-AI-ACT-ART5-1-B",
        "Prohibits AI systems that exploit vulnerabilities due to age, disability, or "
        "social/economic situation to materially distort behaviour causing significant harm.",
        "Article 5",
        ActorRole.ANY,
        None,
        PROHIBITED_PRACTICES_START,
    ),
    RequirementSeed(
        "EU-AI-ACT-ART5-1-C",
        "Prohibits social scoring: evaluating or classifying natural persons over time based on "
        "social behaviour or inferred/predicted characteristics leading to unjustified or "
        "context-unrelated detrimental treatment.",
        "Article 5",
        ActorRole.ANY,
        None,
        PROHIBITED_PRACTICES_START,
    ),
    RequirementSeed(
        "EU-AI-ACT-ART5-1-D",
        "Prohibits AI systems that assess or predict the risk of a natural person committing a "
        "criminal offence based solely on profiling or personality traits.",
        "Article 5",
        ActorRole.ANY,
        None,
        PROHIBITED_PRACTICES_START,
        exceptions=(
            ExceptionSeed(
                "this prohibition shall not apply to AI systems used to support the human "
                "assessment of the involvement of a person in a criminal activity, which is "
                "already based on objective and verifiable facts directly linked to a criminal activity",
                "Article 5",
            ),
        ),
    ),
    RequirementSeed(
        "EU-AI-ACT-ART5-1-E",
        "Prohibits AI systems that create or expand facial recognition databases through "
        "untargeted scraping of facial images from the internet or CCTV footage.",
        "Article 5",
        ActorRole.ANY,
        None,
        PROHIBITED_PRACTICES_START,
    ),
    RequirementSeed(
        "EU-AI-ACT-ART5-1-F",
        "Prohibits AI systems that infer emotions of a natural person in the workplace or "
        "education institutions.",
        "Article 5",
        ActorRole.ANY,
        None,
        PROHIBITED_PRACTICES_START,
        exceptions=(
            ExceptionSeed(
                "except where the use of the AI system is intended to be put in place or into "
                "the market for medical or safety reasons",
                "Article 5",
            ),
        ),
    ),
    RequirementSeed(
        "EU-AI-ACT-ART5-1-G",
        "Prohibits biometric categorisation systems that categorise natural persons based on "
        "biometric data to infer or deduce race, political opinions, trade union membership, "
        "religious or philosophical beliefs, sex life, or sexual orientation.",
        "Article 5",
        ActorRole.ANY,
        None,
        PROHIBITED_PRACTICES_START,
    ),
    RequirementSeed(
        "EU-AI-ACT-ART5-1-H",
        "Prohibits 'real-time' remote biometric identification in publicly accessible spaces for "
        "law enforcement purposes, subject to the narrowly-defined exceptions and judicial/"
        "administrative authorisation procedure set out in Article 5(2)-(7).",
        "Article 5",
        ActorRole.ANY,
        None,
        PROHIBITED_PRACTICES_START,
    ),
]

# Article 6 classification pathways (deterministic pathway, not a per-point prohibition).
CLASSIFICATION_PATHWAY_REQUIREMENTS = [
    RequirementSeed(
        "EU-AI-ACT-ART6-1",
        "An AI system is high-risk if it is a safety component (or is itself) a product covered "
        "by Union harmonisation legislation in Annex I AND that product requires third-party "
        "conformity assessment under that legislation.",
        "Article 6",
        ActorRole.ANY,
        None,
        ARTICLE_6_1_START,
    ),
    RequirementSeed(
        "EU-AI-ACT-ART6-2",
        "An AI system referred to in Annex III is considered high-risk, subject to the Article "
        "6(3) derogation.",
        "Article 6",
        ActorRole.ANY,
        None,
        HIGH_RISK_GENERAL_START,
        exceptions=(
            ExceptionSeed(
                "an AI system referred to in Annex III shall not be considered to be high-risk "
                "where it does not pose a significant risk of harm to the health, safety or "
                "fundamental rights of natural persons, including by not materially influencing "
                "the outcome of decision making [applies where: narrow procedural task; improves "
                "result of a previously completed human activity; detects deviations from prior "
                "decision-making patterns without replacing/influencing human assessment; or "
                "performs a preparatory task] -- Notwithstanding the foregoing, an AI system "
                "referred to in Annex III shall always be considered high-risk where it performs "
                "profiling of natural persons.",
                "Article 6",
            ),
        ),
    ),
]

# One requirement per Annex III numbered area (1-8), all sharing the Article 6(2)/(3) pathway.
ANNEX_III_AREA_REQUIREMENTS = [
    RequirementSeed(
        "EU-AI-ACT-ANNEXIII-1", "Biometrics: remote biometric identification, biometric "
        "categorisation by sensitive/protected attributes, and emotion recognition (where permitted "
        "under Union/national law).", "Annex III", ActorRole.ANY, "1", HIGH_RISK_GENERAL_START,
    ),
    RequirementSeed(
        "EU-AI-ACT-ANNEXIII-2", "Critical infrastructure: safety components in critical digital "
        "infrastructure, road traffic, or water/gas/heating/electricity supply.",
        "Annex III", ActorRole.ANY, "2", HIGH_RISK_GENERAL_START,
    ),
    RequirementSeed(
        "EU-AI-ACT-ANNEXIII-3", "Education and vocational training: access/admission decisions, "
        "evaluating learning outcomes, assessing appropriate education level, monitoring prohibited "
        "test behaviour.", "Annex III", ActorRole.ANY, "3", HIGH_RISK_GENERAL_START,
    ),
    RequirementSeed(
        "EU-AI-ACT-ANNEXIII-4", "Employment and workers' management: recruitment/selection, and "
        "decisions on work-related relationships, task allocation, or performance monitoring.",
        "Annex III", ActorRole.ANY, "4", HIGH_RISK_GENERAL_START,
    ),
    RequirementSeed(
        "EU-AI-ACT-ANNEXIII-5", "Access to essential private/public services: eligibility for public "
        "assistance benefits, creditworthiness/credit scoring, life/health insurance risk assessment "
        "and pricing, emergency call evaluation/dispatch.", "Annex III", ActorRole.ANY, "5",
        HIGH_RISK_GENERAL_START,
    ),
    RequirementSeed(
        "EU-AI-ACT-ANNEXIII-6", "Law enforcement (where permitted under Union/national law): risk "
        "assessment of individuals, polygraphs, evidence reliability evaluation, offending/"
        "re-offending risk assessment, profiling in criminal investigations.", "Annex III",
        ActorRole.ANY, "6", HIGH_RISK_GENERAL_START,
    ),
    RequirementSeed(
        "EU-AI-ACT-ANNEXIII-7", "Migration, asylum and border control management (where permitted "
        "under Union/national law): polygraphs, risk assessment of persons entering a Member State, "
        "examination of asylum/visa/residence applications, identification of natural persons.",
        "Annex III", ActorRole.ANY, "7", HIGH_RISK_GENERAL_START,
    ),
    RequirementSeed(
        "EU-AI-ACT-ANNEXIII-8", "Administration of justice and democratic processes: assisting "
        "judicial authorities in researching/interpreting facts and law, or influencing election/"
        "referendum outcomes or voting behaviour.", "Annex III", ActorRole.ANY, "8",
        HIGH_RISK_GENERAL_START,
    ),
]

ALL_REQUIREMENT_SEEDS = (
    PROHIBITED_PRACTICE_REQUIREMENTS
    + CLASSIFICATION_PATHWAY_REQUIREMENTS
    + ANNEX_III_AREA_REQUIREMENTS
    + HIGH_RISK_OBLIGATION_REQUIREMENTS
)

# GDPR Article 22/35 -- additional obligations that attach alongside the AI Act's Articles
# 9-15 whenever a system is classified high-risk (a high-risk AI decision about a person is
# almost always also GDPR "automated decision-making"). See ROADMAP.md Phase M.
GDPR_HIGH_RISK_START = date(2018, 5, 25)  # GDPR Article 99(2): applicable from 25 May 2018

GDPR_PROVISION_SEEDS = [
    ProvisionSeed(
        "Article 22", "Automated individual decision-making, including profiling",
        "article_22.txt", GDPR_HIGH_RISK_START,
    ),
    ProvisionSeed(
        "Article 35", "Data protection impact assessment", "article_35.txt", GDPR_HIGH_RISK_START,
    ),
]

GDPR_OBLIGATION_REQUIREMENTS = [
    RequirementSeed(
        "GDPR-ART22",
        "Data subjects have the right not to be subject to a decision based solely on "
        "automated processing (including profiling) that produces legal or similarly "
        "significant effects on them, unless a narrow exception applies -- and even then, "
        "the controller must provide safeguards including human intervention, the right to "
        "express a viewpoint, and the right to contest the decision.",
        "Article 22",
        ActorRole.ANY,
        None,
        GDPR_HIGH_RISK_START,
    ),
    RequirementSeed(
        "GDPR-ART35",
        "Where processing (in particular automated profiling that produces legal or "
        "similarly significant effects) is likely to result in a high risk to individuals' "
        "rights and freedoms, the controller must carry out a data protection impact "
        "assessment before the processing begins.",
        "Article 35",
        ActorRole.ANY,
        None,
        GDPR_HIGH_RISK_START,
    ),
]


@dataclass(frozen=True)
class CrosswalkSeed:
    requirement_key: str
    citation: str
    text_file: str


NIST_AI_RMF_NAME = "NIST AI RMF 1.0"
NIST_AI_RMF_URL = "https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf"

# Voluntary-framework annotations, not new obligations -- see FrameworkCrosswalk's
# docstring and ROADMAP.md's "Multi-framework scope" section. One subcategory per
# requirement, except EU-AI-ACT-ART15 which covers three distinct properties (accuracy,
# robustness, cybersecurity) that map to three separate MEASURE subcategories.
NIST_CROSSWALK_SEEDS = [
    CrosswalkSeed("EU-AI-ACT-ART9", "GOVERN 1.4", "govern_1_4.txt"),
    CrosswalkSeed("EU-AI-ACT-ART10", "MAP 2.3", "map_2_3.txt"),
    CrosswalkSeed("EU-AI-ACT-ART11", "GOVERN 4.2", "govern_4_2.txt"),
    CrosswalkSeed("EU-AI-ACT-ART12", "MEASURE 2.4", "measure_2_4.txt"),
    CrosswalkSeed("EU-AI-ACT-ART13", "MEASURE 2.8", "measure_2_8.txt"),
    CrosswalkSeed("EU-AI-ACT-ART14", "GOVERN 3.2", "govern_3_2.txt"),
    CrosswalkSeed("EU-AI-ACT-ART15", "MEASURE 2.6", "measure_2_6.txt"),
    CrosswalkSeed("EU-AI-ACT-ART15", "MEASURE 2.7", "measure_2_7.txt"),
    CrosswalkSeed("GDPR-ART22", "GOVERN 3.2", "govern_3_2.txt"),
    CrosswalkSeed("GDPR-ART35", "MAP 5.1", "map_5_1.txt"),
]

NIST_CSF_NAME = "NIST CSF 2.0"
NIST_CSF_URL = "https://nvlpubs.nist.gov/nistpubs/CSWP/NIST.CSWP.29.pdf"
NIST_CSF_SOURCES_DIR = Path(__file__).resolve().parents[2] / "legal" / "sources" / "nist_csf_2_0"

# Narrower than NIST_CROSSWALK_SEEDS (Phase O): CSF is general cybersecurity guidance,
# not AI-specific, so it only meaningfully crosswalks against EU-AI-ACT-ART15
# (accuracy, robustness, cybersecurity) rather than all seven high-risk obligations.
NIST_CSF_CROSSWALK_SEEDS = [
    CrosswalkSeed("EU-AI-ACT-ART15", "ID.RA-01", "id_ra_01.txt"),
    CrosswalkSeed("EU-AI-ACT-ART15", "PR.IR-03", "pr_ir_03.txt"),
]


def crosswalks_seeded(session: Session, framework_name: str = NIST_AI_RMF_NAME) -> bool:
    return session.query(FrameworkCrosswalk).filter_by(framework_name=framework_name).first() is not None


def _ingest_crosswalks(
    session: Session, framework_name: str, source_url: str, sources_dir: Path, seeds: list[CrosswalkSeed]
) -> None:
    """Load one framework's crosswalk annotations. No-op if already present.

    Requires the target Requirement rows to already be seeded.
    """
    if crosswalks_seeded(session, framework_name):
        return

    for seed in seeds:
        requirement = (
            session.query(Requirement)
            .filter_by(requirement_key=seed.requirement_key, superseded_by_id=None)
            .one()
        )
        text = (sources_dir / seed.text_file).read_text()
        session.add(
            FrameworkCrosswalk(
                requirement_id=requirement.id,
                framework_name=framework_name,
                citation=seed.citation,
                citation_text=text,
                source_url=source_url,
            )
        )
    session.commit()


def ingest_crosswalks(session: Session) -> None:
    """Load every voluntary-framework crosswalk. Each framework is independently
    idempotent, so this is safe to call regardless of which are already present."""
    _ingest_crosswalks(session, NIST_AI_RMF_NAME, NIST_AI_RMF_URL, NIST_AI_RMF_SOURCES_DIR, NIST_CROSSWALK_SEEDS)
    _ingest_crosswalks(session, NIST_CSF_NAME, NIST_CSF_URL, NIST_CSF_SOURCES_DIR, NIST_CSF_CROSSWALK_SEEDS)


def seed_is_present(session: Session) -> bool:
    ai_act = session.query(SourceDocument).filter_by(source_key="eu_ai_act_2024_1689").first()
    gdpr = session.query(SourceDocument).filter_by(source_key="gdpr_2016_679").first()
    return ai_act is not None and gdpr is not None


def _ingest_source(
    session: Session,
    sources_dir: Path,
    provision_seeds: list[ProvisionSeed],
    requirement_seeds: list[RequirementSeed],
) -> None:
    """Load one source document's provisions and requirements. No-op if already present."""
    metadata = json.loads((sources_dir / "metadata.json").read_text())
    if session.query(SourceDocument).filter_by(source_key=metadata["source_document_key"]).first():
        return

    source_document = SourceDocument(
        source_key=metadata["source_document_key"],
        celex_id=metadata["celex_id"],
        official_title=metadata["official_title"],
        oj_reference=metadata["oj_reference"],
        date_of_act=date.fromisoformat(metadata["date_of_act"]),
        date_published=date.fromisoformat(metadata["date_published"]),
        date_entry_into_force=date.fromisoformat(metadata["date_entry_into_force"]),
        source_url=metadata["source_url"],
        raw_fetch_sha256=metadata["raw_fetch_sha256"],
        retrieved_at=datetime.fromisoformat(metadata["retrieved_at"].replace("Z", "+00:00")),
    )
    session.add(source_document)
    session.flush()

    provisions_by_citation: dict[str, LegalProvision] = {}
    for seed in provision_seeds:
        text = (sources_dir / seed.text_file).read_text()
        provision = LegalProvision(
            source_document_id=source_document.id,
            citation=seed.citation,
            heading=seed.heading,
            text=text,
            effective_date=seed.effective_date,
        )
        session.add(provision)
        session.flush()
        provisions_by_citation[seed.citation] = provision

        session.add(
            ProvenanceRecord(
                entity_type=EntityType.PROVISION,
                entity_id=provision.id,
                source_document_id=source_document.id,
                retrieved_at=source_document.retrieved_at,
                retrieval_method=RetrievalMethod.AUTOMATED,
                url=source_document.source_url,
            )
        )

    session.add(
        ProvenanceRecord(
            entity_type=EntityType.SOURCE_DOCUMENT,
            entity_id=source_document.id,
            source_document_id=source_document.id,
            retrieved_at=source_document.retrieved_at,
            retrieval_method=RetrievalMethod.AUTOMATED,
            url=source_document.source_url,
        )
    )

    for seed in requirement_seeds:
        provision = provisions_by_citation[seed.provision_citation]
        requirement = Requirement(
            requirement_key=seed.requirement_key,
            summary=seed.summary,
            primary_provision_id=provision.id,
        )
        session.add(requirement)
        session.flush()

        session.add(
            ApplicabilityCondition(
                requirement_id=requirement.id,
                actor_role=seed.actor_role,
                annex_iii_category=seed.annex_iii_category,
                temporal_start=seed.temporal_start,
            )
        )

        for exc in seed.exceptions:
            session.add(
                LegalException(
                    requirement_id=requirement.id,
                    description=exc.description,
                    source_provision_id=provisions_by_citation[exc.provision_citation].id,
                )
            )

        session.add(
            ProvenanceRecord(
                entity_type=EntityType.REQUIREMENT,
                entity_id=requirement.id,
                source_document_id=source_document.id,
                retrieved_at=source_document.retrieved_at,
                retrieval_method=RetrievalMethod.MANUAL,
                url=source_document.source_url,
            )
        )

    session.commit()


def ingest_seed(session: Session) -> None:
    """Load every seed source document into the database. Each source is independently
    idempotent, so this is safe to call regardless of which sources are already present."""
    _ingest_source(session, SOURCES_DIR, PROVISION_SEEDS, ALL_REQUIREMENT_SEEDS)
    _ingest_source(session, GDPR_SOURCES_DIR, GDPR_PROVISION_SEEDS, GDPR_OBLIGATION_REQUIREMENTS)
    ingest_crosswalks(session)
