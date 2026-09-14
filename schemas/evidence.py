"""Structured output schema for the evidence-assessment LLM stage.

All seven canonical dimensions are required, each individually, so "a policy exists"
can't silently stand in for "the policy is specific, current, and traceable" -- per the
evidence-assessment skill: existence of a policy is not proof of implementation.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from schemas.enums import EvidenceDimension, EvidenceStatus


class DimensionAssessment(BaseModel):
    dimension: EvidenceDimension
    met: bool
    note: str = Field(min_length=1)


class EvidenceAssessment(BaseModel):
    requirement_key: str = Field(min_length=1)
    status: EvidenceStatus
    dimensions: list[DimensionAssessment] = Field(min_length=1)
    rationale: str = Field(min_length=1)
    contradictions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def dimensions_cover_all_seven_exactly_once(self) -> EvidenceAssessment:
        seen = [d.dimension for d in self.dimensions]
        if len(seen) != len(set(seen)):
            raise ValueError("each dimension may be assessed at most once")
        if set(seen) != set(EvidenceDimension):
            missing = set(EvidenceDimension) - set(seen)
            raise ValueError(
                f"must assess all seven evidence dimensions; missing: {sorted(d.value for d in missing)}"
            )
        return self

    @model_validator(mode="after")
    def compliant_status_requires_all_dimensions_met(self) -> EvidenceAssessment:
        if self.status == EvidenceStatus.COMPLIANT and not all(d.met for d in self.dimensions):
            raise ValueError("status=COMPLIANT requires every assessed dimension to be met")
        return self
