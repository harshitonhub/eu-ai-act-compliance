"""Explicit to_dict/from_dict for the plain (non-Pydantic) dataclasses that flow into an
AssessmentRecord. Kept explicit per dataclass rather than a generic dataclasses.asdict()
+ default=str: enum fields need their .value, not repr(), to round-trip correctly.
"""

from __future__ import annotations

from datetime import datetime

from schemas.enums import ClassificationCategory, EvidenceStatus
from src.gaps.compute import Gap
from src.observability.instrumented_client import LLMCallRecord
from src.obligations.mapping import Obligation
from src.review.triggers import ReviewFlag, ReviewTrigger


def obligation_to_dict(o: Obligation) -> dict:
    return {
        "requirement_key": o.requirement_key,
        "citation": o.citation,
        "summary": o.summary,
        "triggered_by": o.triggered_by.value,
    }


def obligation_from_dict(d: dict) -> Obligation:
    return Obligation(
        requirement_key=d["requirement_key"],
        citation=d["citation"],
        summary=d["summary"],
        triggered_by=ClassificationCategory(d["triggered_by"]),
    )


def gap_to_dict(g: Gap) -> dict:
    return {
        "requirement_key": g.requirement_key,
        "citation": g.citation,
        "obligation_summary": g.obligation_summary,
        "evidence_status": g.evidence_status.value,
        "rationale": g.rationale,
    }


def gap_from_dict(d: dict) -> Gap:
    return Gap(
        requirement_key=d["requirement_key"],
        citation=d["citation"],
        obligation_summary=d["obligation_summary"],
        evidence_status=EvidenceStatus(d["evidence_status"]),
        rationale=d["rationale"],
    )


def review_flag_to_dict(f: ReviewFlag) -> dict:
    return {"trigger": f.trigger.value, "detail": f.detail}


def review_flag_from_dict(d: dict) -> ReviewFlag:
    return ReviewFlag(trigger=ReviewTrigger(d["trigger"]), detail=d["detail"])


def llm_call_record_to_dict(c: LLMCallRecord) -> dict:
    return {
        "timestamp": c.timestamp.isoformat(),
        "provider": c.provider,
        "model": c.model,
        "prompt_version": c.prompt_version,
        "response_model_name": c.response_model_name,
        "succeeded": c.succeeded,
        "input_tokens": c.input_tokens,
        "output_tokens": c.output_tokens,
        "retried": c.retried,
        "latency_ms": c.latency_ms,
        "error": c.error,
    }


def llm_call_record_from_dict(d: dict) -> LLMCallRecord:
    return LLMCallRecord(
        timestamp=datetime.fromisoformat(d["timestamp"]),
        provider=d["provider"],
        model=d["model"],
        prompt_version=d["prompt_version"],
        response_model_name=d["response_model_name"],
        succeeded=d["succeeded"],
        input_tokens=d["input_tokens"],
        output_tokens=d["output_tokens"],
        retried=d["retried"],
        latency_ms=d["latency_ms"],
        error=d.get("error"),
    )
