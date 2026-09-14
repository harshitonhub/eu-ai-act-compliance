"""Structured output schema for the classification LLM stage.

Enforces two mandate rules structurally, not by convention:
- a YES/POSSIBLY classification must cite at least one requirement (never a bare assertion)
- a full result must independently assess all 5 categories, exactly once each
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from schemas.enums import ClassificationCategory, ClassificationState

CITED_STATES = {ClassificationState.YES, ClassificationState.POSSIBLY}


class CitedRequirement(BaseModel):
    requirement_key: str = Field(min_length=1)
    citation: str = Field(min_length=1)
    relevance: str = Field(min_length=1)


class CategoryClassification(BaseModel):
    category: ClassificationCategory
    state: ClassificationState
    cited_requirements: list[CitedRequirement] = Field(default_factory=list)
    rationale: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def require_citation_for_affirmative_states(self) -> CategoryClassification:
        if self.state in CITED_STATES and not self.cited_requirements:
            raise ValueError(
                f"state={self.state.value} requires at least one cited_requirement "
                "(never assert YES/POSSIBLY without a legal basis)"
            )
        return self


class ClassificationResult(BaseModel):
    assessments: list[CategoryClassification]

    @model_validator(mode="after")
    def require_every_category_exactly_once(self) -> ClassificationResult:
        categories = [a.category for a in self.assessments]
        if set(categories) != set(ClassificationCategory) or len(categories) != len(ClassificationCategory):
            raise ValueError(
                f"must assess every category exactly once; got {[c.value for c in categories]}"
            )
        return self

    def for_category(self, category: ClassificationCategory) -> CategoryClassification:
        return next(a for a in self.assessments if a.category == category)
