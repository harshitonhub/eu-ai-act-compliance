"""Hybrid retrieval over the legal knowledge tables: exact key lookup + deterministic
keyword-overlap ranking. No LLM, no vector database -- per docs/architecture.md, a
vector store is deferred until eval data shows semantic recall is the bottleneck; at
the current corpus size (a handful of requirements) keyword overlap is enough to rank
candidates within a category.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from schemas.enums import ActorRole
from src.legal.queries import RequirementResult, find_requirement_by_key, find_requirements

_STOPWORDS = {
    "the", "a", "an", "to", "of", "in", "for", "and", "or", "is", "are", "that", "this",
    "on", "with", "by", "as", "be", "it", "its", "at", "from", "any", "not", "shall",
}
_WORD_PATTERN = re.compile(r"[a-zA-Z]{3,}")


@dataclass(frozen=True)
class RetrievedRequirement:
    requirement_key: str
    summary: str
    citation: str
    provision_text: str
    exceptions: tuple[str, ...]
    relevance_score: float


def _significant_words(text: str) -> set[str]:
    return {w for w in _WORD_PATTERN.findall(text.lower()) if w not in _STOPWORDS}


def keyword_score(query_text: str, candidate_text: str) -> float:
    """Fraction of the query's significant words that appear in the candidate text."""
    query_words = _significant_words(query_text)
    if not query_words:
        return 0.0
    candidate_words = _significant_words(candidate_text)
    return len(query_words & candidate_words) / len(query_words)


def _to_retrieved(result: RequirementResult, score: float) -> RetrievedRequirement:
    return RetrievedRequirement(
        requirement_key=result.requirement_key,
        summary=result.summary,
        citation=result.citation,
        provision_text=result.provision_text,
        exceptions=result.exceptions,
        relevance_score=score,
    )


def retrieve(
    session: Session,
    *,
    query_text: str,
    annex_iii_category: str | None = None,
    actor_role: ActorRole | None = None,
    as_of: date | None = None,
    requirement_key_prefixes: tuple[str, ...] | None = None,
    limit: int = 10,
) -> list[RetrievedRequirement]:
    """Deterministic candidate filter (exact applicability match) ranked by keyword overlap.

    `requirement_key_prefixes=None` applies no prefix filter; an empty tuple `()` matches
    nothing (used by callers to represent "no legal knowledge ingested for this scope yet").
    """
    candidates = find_requirements(
        session, annex_iii_category=annex_iii_category, actor_role=actor_role, as_of=as_of
    )
    if requirement_key_prefixes is not None:
        candidates = [c for c in candidates if c.requirement_key.startswith(requirement_key_prefixes)]

    # Score against `summary` only, not `provision_text`: several requirements sharing one
    # ingested provision (e.g. all 8 Annex III areas cite the same Annex III text block --
    # see docs/legal-methodology.md's point-level-splitting deferral) would otherwise all
    # score near-identically against that shared, much larger text.
    scored = [(keyword_score(query_text, c.summary), c) for c in candidates]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [_to_retrieved(c, score) for score, c in scored[:limit]]


def retrieve_by_key(session: Session, requirement_key: str) -> RetrievedRequirement | None:
    """Exact lookup of a single requirement by its stable key, with relevance_score=1.0."""
    result = find_requirement_by_key(session, requirement_key)
    if result is None:
        return None
    return _to_retrieved(result, score=1.0)
