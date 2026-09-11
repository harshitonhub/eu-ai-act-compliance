"""Golden-dataset eval runner for evidence assessment. Mirrors evals/runner.py's
design: replays each case through the real assess_evidence() pipeline using a
FakeCompletionProvider primed with the case's own fake_llm_response. Same scope note
applies -- this is a harness/regression check, not a live model quality eval. See
evals/golden/evidence_v1/README.md.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from src.evidence.assess import assess_evidence
from src.llm.fake_client import FakeCompletionProvider
from src.llm.interface import LLMClient
from src.obligations.mapping import Obligation
from schemas.enums import ClassificationCategory

GOLDEN_DIR = Path(__file__).resolve().parent / "golden" / "evidence_v1"


@dataclass
class CaseResult:
    case_id: str
    difficulty: str
    passed: bool
    mismatches: list[str]


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


def run_case(case: dict) -> CaseResult:
    obligation = Obligation(
        requirement_key=case["obligation"]["requirement_key"],
        citation=case["obligation"]["citation"],
        summary=case["obligation"]["summary"],
        triggered_by=ClassificationCategory.HIGH_RISK,  # every evidence_v1 case is an Article 9-15 obligation
    )
    responses = [case["fake_llm_response"]] if case["fake_llm_response"] is not None else []
    client = LLMClient(FakeCompletionProvider(responses), model="fake-model")

    result = assess_evidence(client, obligation, case["evidence_text"])

    mismatches = []
    if result.status.value != case["expected_status"]:
        mismatches.append(f"status: expected {case['expected_status']}, got {result.status.value}")

    expects_contradictions = case.get("expected_contradictions_present", False)
    has_contradictions = bool(result.contradictions)
    if expects_contradictions != has_contradictions:
        mismatches.append(
            f"contradictions: expected present={expects_contradictions}, got present={has_contradictions}"
        )

    return CaseResult(
        case_id=case["case_id"], difficulty=case["difficulty"], passed=not mismatches, mismatches=mismatches
    )


def run_evidence_golden_suite(cases_dir: Path = GOLDEN_DIR) -> EvalReport:
    return EvalReport(case_results=[run_case(case) for case in load_cases(cases_dir)])
