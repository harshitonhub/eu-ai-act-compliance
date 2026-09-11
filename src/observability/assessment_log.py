"""Persist and reconstruct assessments, per the mandate's "Observability and
reproducibility" list: assessment ID, timestamp, legal knowledge version, retrieved/
computed facts, classification, obligations, evidence, review, token usage, latency,
and errors must all be recoverable for a past assessment.

Explicitly not covered here (documented, not silently dropped): tenant/context is a
column (`tenant_id`) but unused -- single-tenant so far; model/prompt/retrieval
*version* strings are captured per LLM call via LLMCallRecord.prompt_version, but there
is no separate global "retrieval configuration" version yet since retrieval has had only
one implementation (keyword-overlap ranking) since Phase 3.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy.orm import Session

from schemas.classification import ClassificationResult
from schemas.evidence import EvidenceAssessment
from schemas.facts import ExtractedFacts
from src.gaps.compute import Gap
from src.observability.instrumented_client import LLMCallRecord
from src.observability.serialization import (
    gap_from_dict,
    gap_to_dict,
    llm_call_record_from_dict,
    llm_call_record_to_dict,
    obligation_from_dict,
    obligation_to_dict,
    review_flag_from_dict,
    review_flag_to_dict,
)
from src.obligations.mapping import Obligation
from src.persistence.models import AssessmentRecord
from src.review.triggers import ReviewFlag


@dataclass(frozen=True)
class ReconstructedAssessment:
    assessment_id: str
    created_at: datetime
    as_of: date
    legal_knowledge_source_key: str
    facts: ExtractedFacts
    classification: ClassificationResult
    obligations: list[Obligation]
    evidence_assessments: list[EvidenceAssessment]
    gaps: list[Gap]
    review_flags: list[ReviewFlag]
    llm_calls: list[LLMCallRecord]
    total_input_tokens: int
    total_output_tokens: int
    total_latency_ms: float
    error: str | None


def record_assessment(
    session: Session,
    *,
    as_of: date,
    legal_knowledge_source_key: str,
    facts: ExtractedFacts,
    classification: ClassificationResult,
    obligations: list[Obligation],
    evidence_assessments: list[EvidenceAssessment],
    gaps: list[Gap],
    review_flags: list[ReviewFlag],
    llm_calls: list[LLMCallRecord],
    error: str | None = None,
) -> str:
    """Persist a completed assessment. Returns the assessment_id."""
    record = AssessmentRecord(
        as_of=as_of,
        legal_knowledge_source_key=legal_knowledge_source_key,
        facts_json=facts.model_dump_json(),
        classification_json=classification.model_dump_json(),
        obligations_json=json.dumps([obligation_to_dict(o) for o in obligations]),
        evidence_assessments_json=json.dumps([e.model_dump(mode="json") for e in evidence_assessments]),
        gaps_json=json.dumps([gap_to_dict(g) for g in gaps]),
        review_flags_json=json.dumps([review_flag_to_dict(f) for f in review_flags]),
        llm_calls_json=json.dumps([llm_call_record_to_dict(c) for c in llm_calls]),
        total_input_tokens=sum(c.input_tokens for c in llm_calls),
        total_output_tokens=sum(c.output_tokens for c in llm_calls),
        total_latency_ms=sum(c.latency_ms for c in llm_calls),
        error=error,
    )
    session.add(record)
    session.commit()
    return record.id


def reconstruct_assessment(session: Session, assessment_id: str) -> ReconstructedAssessment | None:
    record = session.get(AssessmentRecord, assessment_id)
    if record is None:
        return None

    return ReconstructedAssessment(
        assessment_id=record.id,
        created_at=record.created_at,
        as_of=record.as_of,
        legal_knowledge_source_key=record.legal_knowledge_source_key,
        facts=ExtractedFacts.model_validate_json(record.facts_json),
        classification=ClassificationResult.model_validate_json(record.classification_json),
        obligations=[obligation_from_dict(d) for d in json.loads(record.obligations_json)],
        evidence_assessments=[
            EvidenceAssessment.model_validate(d) for d in json.loads(record.evidence_assessments_json)
        ],
        gaps=[gap_from_dict(d) for d in json.loads(record.gaps_json)],
        review_flags=[review_flag_from_dict(d) for d in json.loads(record.review_flags_json)],
        llm_calls=[llm_call_record_from_dict(d) for d in json.loads(record.llm_calls_json)],
        total_input_tokens=record.total_input_tokens,
        total_output_tokens=record.total_output_tokens,
        total_latency_ms=record.total_latency_ms,
        error=record.error,
    )
