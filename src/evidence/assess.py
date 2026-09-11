"""Evidence assessment: Obligation + evidence text -> EvidenceAssessment.

Mirrors src/classification/classify.py's deterministic guardrails: skip the LLM
entirely when there's nothing to assess (empty evidence), and fail closed to
INSUFFICIENT_EVIDENCE rather than trusting a response that doesn't actually match the
obligation it was asked about.
"""

from __future__ import annotations

from prompts.evidence_assessor.v1 import PROMPT_VERSION, SYSTEM_PROMPT, build_user_prompt
from schemas.enums import EvidenceDimension, EvidenceStatus
from schemas.evidence import DimensionAssessment, EvidenceAssessment
from src.llm import LLMClient, StructuredOutputError
from src.obligations.mapping import Obligation


def _insufficient_evidence(obligation: Obligation, rationale: str) -> EvidenceAssessment:
    return EvidenceAssessment(
        requirement_key=obligation.requirement_key,
        status=EvidenceStatus.INSUFFICIENT_EVIDENCE,
        dimensions=[
            DimensionAssessment(dimension=d, met=False, note="Not assessed.") for d in EvidenceDimension
        ],
        rationale=rationale,
    )


def assess_evidence(llm_client: LLMClient, obligation: Obligation, evidence_text: str) -> EvidenceAssessment:
    if not evidence_text or not evidence_text.strip():
        return _insufficient_evidence(obligation, f"No evidence supplied for {obligation.requirement_key}.")

    try:
        assessment, _metadata = llm_client.generate_structured(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=build_user_prompt(obligation, evidence_text),
            response_model=EvidenceAssessment,
            prompt_version=PROMPT_VERSION,
        )
    except StructuredOutputError:
        return _insufficient_evidence(
            obligation, "Model output failed schema validation twice; failing closed."
        )

    if assessment.requirement_key != obligation.requirement_key:
        return _insufficient_evidence(
            obligation,
            f"Model returned an assessment for requirement_key={assessment.requirement_key!r}, "
            f"expected {obligation.requirement_key!r}; failing closed.",
        )

    return assessment


def assess_all_obligations(
    llm_client: LLMClient, obligations: list[Obligation], evidence_by_key: dict[str, str]
) -> list[EvidenceAssessment]:
    return [
        assess_evidence(llm_client, obligation, evidence_by_key.get(obligation.requirement_key, ""))
        for obligation in obligations
    ]
