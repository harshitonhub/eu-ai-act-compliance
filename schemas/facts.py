"""Structured output schema for the fact-extraction LLM stage.

Facts only -- no classification conclusions. A field left as None means the LLM found
no basis to state it; `insufficient_information_fields` names which fields that applies
to, so downstream classification can produce INSUFFICIENT_INFORMATION deliberately
rather than treating a missing field as a false/negative answer.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from schemas.enums import ActorRole


class ExtractedFacts(BaseModel):
    system_description: str = Field(min_length=1)
    intended_purpose: str = Field(min_length=1)
    actor_roles: list[ActorRole] = Field(default_factory=list)
    sector: str | None = None
    deployment_context: str | None = None
    affected_persons_description: str | None = None
    decisions_or_outcomes_influenced: str | None = None
    technology_description: str | None = None
    human_oversight_description: str | None = None
    uses_biometric_data: bool | None = None
    uses_profiling: bool | None = None
    is_safety_component_of_regulated_product: bool | None = None
    insufficient_information_fields: list[str] = Field(default_factory=list)
