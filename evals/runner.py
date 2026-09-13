"""Golden-dataset eval runner for the classification pipeline.

Loads hand-built cases from evals/golden/classification_v1/*.json, replays each one
through the real classify_system() pipeline (real retrieval, real schema validation,
real citation verification) using a FakeCompletionProvider primed with each case's
pre-authored `fake_llm_responses`. This is a harness/regression check, not a live model
quality eval: it proves the pipeline wires facts -> retrieval -> LLM call -> validation
-> citation check -> result correctly for a known input/output pair. Running the same
suite against AnthropicCompletionProvider instead (manually, with a real API key) is how
you'd measure actual model quality -- see evals/golden/classification_v1/README.md.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from sqlalchemy.orm import Session

from schemas.enums import ClassificationCategory
from schemas.facts import ExtractedFacts
from src.classification.category_scope import CATEGORY_KEY_PREFIXES
from src.classification.classify import classify_system
from src.legal.ingest import ingest_seed
from src.llm.fake_client import FakeCompletionProvider
from src.llm.interface import LLMClient
from src.retrieval.retrieval import retrieve

GOLDEN_DIR = Path(__file__).resolve().parent / "golden" / "classification_v1"


@dataclass
class CaseResult:
    case_id: str
    difficulty: str
    passed: bool
    mismatches: list[str]
    # (category, expected_state, actual_state) per asserted category. Kept so the report
    # generator can build a confusion matrix instead of only a pass/fail tally --
    # "14/16 passed" hides *which* state the pipeline confused for which.
    observations: list[tuple[str, str, str]] = field(default_factory=list)


@dataclass
class EvalReport:
    case_results: list[CaseResult]

    @property
    def total(self) -> int:
        return len(self.case_results)

    @property
    def passed(self) -> int:
        return sum(1 for c in self.case_results if c.passed)

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    def by_difficulty(self, difficulty: str) -> list[CaseResult]:
        return [c for c in self.case_results if c.difficulty == difficulty]


def load_cases(cases_dir: Path = GOLDEN_DIR) -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted(cases_dir.glob("*.json"))]


def _categories_requiring_an_llm_call(session: Session, case: dict, as_of: date) -> list[ClassificationCategory]:
    """Mirrors classify_system's own candidate-availability logic, so the fake provider's
    response queue lines up with the calls classify_system will actually make."""
    query_text = f"{case['facts']['system_description']} {case['facts']['intended_purpose']}"
    needs_llm = []
    for category in ClassificationCategory:
        prefixes = CATEGORY_KEY_PREFIXES[category]
        if not prefixes:
            continue
        candidates = retrieve(session, query_text=query_text, as_of=as_of, requirement_key_prefixes=prefixes)
        if candidates:
            needs_llm.append(category)
    return needs_llm


def run_case(session: Session, case: dict) -> CaseResult:
    as_of = date.fromisoformat(case["as_of"])
    facts = ExtractedFacts(**case["facts"])

    categories_needing_llm = _categories_requiring_an_llm_call(session, case, as_of)
    fake_responses = case.get("fake_llm_responses", {})
    missing = [c.value for c in categories_needing_llm if c.value not in fake_responses]
    if missing:
        raise AssertionError(f"case {case['case_id']!r} is missing fake_llm_responses for: {missing}")

    # A category's entry may be a single response, or a list (e.g. an adversarial case
    # deliberately exercising LLMClient's retry-on-validation-failure path, which
    # consumes two responses for one category's call).
    responses: list[str] = []
    for category in categories_needing_llm:
        entry = fake_responses[category.value]
        if isinstance(entry, list):
            responses.extend(entry)
        else:
            responses.append(entry)

    provider = FakeCompletionProvider(responses)
    client = LLMClient(provider, model="fake-model")

    result = classify_system(client, session, facts, as_of=as_of)

    mismatches = []
    observations = []
    for category_value, expected_state in case["expected_states"].items():
        actual_state = result.for_category(ClassificationCategory(category_value)).state.value
        observations.append((category_value, expected_state, actual_state))
        if actual_state != expected_state:
            mismatches.append(f"{category_value}: expected {expected_state}, got {actual_state}")

    return CaseResult(
        case_id=case["case_id"],
        difficulty=case["difficulty"],
        passed=not mismatches,
        mismatches=mismatches,
        observations=observations,
    )


def run_golden_suite(session: Session, cases_dir: Path = GOLDEN_DIR) -> EvalReport:
    ingest_seed(session)  # idempotent; guarantees the suite runs against the expected corpus
    return EvalReport(case_results=[run_case(session, case) for case in load_cases(cases_dir)])


if __name__ == "__main__":  # pragma: no cover -- convenience entrypoint, CI uses pytest
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    print(
        "Run the suites via `uv run pytest` (they are wired into the test suite), or\n"
        "`uv run python scripts/generate_eval_report.py` to regenerate docs/eval-results.md\n"
        "with pass rates, confusion matrices, and coverage gaps."
    )
