"""Classification pipeline: ExtractedFacts -> ClassificationResult.

Retrieval and the "no legal knowledge for this category" shortcut are deterministic.
The LLM is used only to reason over facts + retrieved requirements for a single
category at a time (never a giant multi-category prompt, per code-quality.md).
Citation verification (the critic stage's core check -- see prompts/critic/README.md)
is deterministic and fails the result closed to INSUFFICIENT_INFORMATION rather than
trusting an unverifiable citation.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from prompts.classifier.v1 import PROMPT_VERSION, SYSTEM_PROMPT, build_user_prompt
from schemas.classification import CategoryClassification, ClassificationResult
from schemas.enums import ClassificationCategory, ClassificationState
from schemas.facts import ExtractedFacts
from src.classification.category_scope import CATEGORY_KEY_PREFIXES
from src.llm import LLMClient, StructuredOutputError
from src.retrieval.retrieval import RetrievedRequirement, retrieve


def verify_citations(
    classification: CategoryClassification, candidates: list[RetrievedRequirement]
) -> list[str]:
    valid_keys = {c.requirement_key for c in candidates}
    return [
        f"cited unretrieved requirement_key {cited.requirement_key!r}"
        for cited in classification.cited_requirements
        if cited.requirement_key not in valid_keys
    ]


def _insufficient_information(category: ClassificationCategory, rationale: str) -> CategoryClassification:
    return CategoryClassification(
        category=category,
        state=ClassificationState.INSUFFICIENT_INFORMATION,
        rationale=rationale,
        confidence=0.0,
    )


def classify_category(
    llm_client: LLMClient,
    category: ClassificationCategory,
    facts: ExtractedFacts,
    candidates: list[RetrievedRequirement],
) -> CategoryClassification:
    if not candidates:
        return _insufficient_information(
            category, f"No ingested legal requirements available for category={category.value}."
        )

    try:
        classification, _metadata = llm_client.generate_structured(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=build_user_prompt(category, facts, candidates),
            response_model=CategoryClassification,
            prompt_version=PROMPT_VERSION,
        )
    except StructuredOutputError:
        return _insufficient_information(
            category, "Model output failed schema validation twice; failing closed."
        )

    if classification.category != category:
        return _insufficient_information(
            category,
            f"Model returned classification for category={classification.category.value}, "
            f"expected {category.value}; failing closed.",
        )

    problems = verify_citations(classification, candidates)
    if problems:
        return _insufficient_information(
            category,
            classification.rationale + " [citation verification failed: " + "; ".join(problems) + "]",
        )

    return classification


def _not_yet_in_force(category: ClassificationCategory, as_of: date) -> CategoryClassification:
    return CategoryClassification(
        category=category,
        state=ClassificationState.NOT_APPLICABLE,
        rationale=(
            f"Legal requirements exist for category={category.value} but none are in force "
            f"as of {as_of.isoformat()}."
        ),
        confidence=1.0,
    )


def classify_system(
    llm_client: LLMClient, session: Session, facts: ExtractedFacts, *, as_of: date
) -> ClassificationResult:
    """Assesses each category independently.

    Two distinct reasons a category can have zero candidates are kept separate rather
    than both collapsing to INSUFFICIENT_INFORMATION: no legal knowledge ingested for
    the category at all (a knowledge-base gap -- state INSUFFICIENT_INFORMATION) versus
    requirements that exist but are not yet in force as of `as_of` (a deterministically
    known fact -- state NOT_APPLICABLE). Conflating these would misrepresent a definite
    temporal fact as mere uncertainty.
    """
    query_text = f"{facts.system_description} {facts.intended_purpose}"
    primary_actor_role = facts.actor_roles[0] if facts.actor_roles else None

    assessments = []
    for category in ClassificationCategory:
        prefixes = CATEGORY_KEY_PREFIXES[category]
        if not prefixes:
            assessments.append(
                _insufficient_information(
                    category, f"No legal requirements ingested for category={category.value} yet."
                )
            )
            continue

        candidates = retrieve(
            session,
            query_text=query_text,
            actor_role=primary_actor_role,
            as_of=as_of,
            requirement_key_prefixes=prefixes,
        )
        if not candidates:
            candidates_any_time = retrieve(
                session,
                query_text=query_text,
                actor_role=primary_actor_role,
                as_of=None,
                requirement_key_prefixes=prefixes,
            )
            assessments.append(
                _not_yet_in_force(category, as_of)
                if candidates_any_time
                else _insufficient_information(
                    category, f"No legal requirements ingested for category={category.value} yet."
                )
            )
            continue

        assessments.append(classify_category(llm_client, category, facts, candidates))

    return ClassificationResult(assessments=assessments)
