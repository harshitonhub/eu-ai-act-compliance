"""Maps each classification category to the requirement_key prefixes it may cite.

Deterministic and data-driven by the ingested corpus, not a database column, because it
changes only when docs/legal-methodology.md's "excerpts_ingested" list changes -- see
that file for what's ingested vs. deferred. An empty tuple means "no legal knowledge
ingested for this category yet": retrieval will return no candidates and classification
must answer INSUFFICIENT_INFORMATION without calling the LLM (see classify.py).
"""

from __future__ import annotations

from schemas.enums import ClassificationCategory

CATEGORY_KEY_PREFIXES: dict[ClassificationCategory, tuple[str, ...]] = {
    ClassificationCategory.SCOPE: (),
    ClassificationCategory.PROHIBITED_PRACTICES: ("EU-AI-ACT-ART5",),
    ClassificationCategory.HIGH_RISK: ("EU-AI-ACT-ART6", "EU-AI-ACT-ANNEXIII"),
    ClassificationCategory.GPAI: (),
    ClassificationCategory.TRANSPARENCY: (),
}
