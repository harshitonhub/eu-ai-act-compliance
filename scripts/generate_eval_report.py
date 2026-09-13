"""Regenerate docs/eval-results.md from an actual run of the eval suites.

    python scripts/generate_eval_report.py

The suites already run in CI as a pass/fail gate. This exists because a pass/fail gate
is not evidence: "the tests pass" tells a reader nothing about *which* states the
pipeline confuses for which, or whether the uncertainty states are ever actually
exercised. The mandate asked for classification correctness, a confusion matrix, and
uncertainty-handling correctness as named metrics -- this writes them down.

Committed output, regenerated deliberately rather than on every CI run, so the numbers
in the repo are a claim someone made on a date, and a diff shows when they moved.
"""

from __future__ import annotations

import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from evals.evidence_runner import run_evidence_golden_suite
from evals.runner import run_golden_suite
from schemas.enums import ClassificationState, EvidenceStatus
from src.persistence.models import Base, Tenant
from src.persistence.tenancy import bind_tenant

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT = REPO_ROOT / "docs" / "eval-results.md"
EVALS = REPO_ROOT / "evals"

DEMO_TENANT_ID = "00000000-0000-0000-0000-0000000000ev"


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    session.add(Tenant(id=DEMO_TENANT_ID, name="Eval Tenant"))
    session.commit()
    bind_tenant(session, DEMO_TENANT_ID)
    return session


def _pct(passed: int, total: int) -> str:
    return f"{(passed / total * 100):.0f}%" if total else "n/a"


def _difficulty_table(report) -> str:
    difficulties = sorted({c.difficulty for c in report.case_results})
    rows = ["| Difficulty | Cases | Passed | Rate |", "|---|---|---|---|"]
    for difficulty in difficulties:
        cases = report.by_difficulty(difficulty)
        passed = sum(1 for c in cases if c.passed)
        rows.append(f"| {difficulty} | {len(cases)} | {passed} | {_pct(passed, len(cases))} |")
    rows.append(f"| **all** | **{report.total}** | **{report.passed}** | **{_pct(report.passed, report.total)}** |")
    return "\n".join(rows)


def _confusion(reports: list, label: str) -> str:
    """Expected state -> what the pipeline actually produced. A diagonal-only table means
    no state is ever mistaken for another."""
    pairs = Counter()
    for report in reports:
        for case in report.case_results:
            for _field, expected, actual in case.observations:
                pairs[(expected, actual)] += 1
    if not pairs:
        return "_No observations recorded._"

    expected_states = sorted({e for e, _ in pairs})
    actual_states = sorted({a for _, a in pairs})
    header = f"| expected \\ actual | {' | '.join(actual_states)} |"
    divider = "|---" * (len(actual_states) + 1) + "|"
    rows = [f"**{label}**", "", header, divider]
    for expected in expected_states:
        cells = []
        for actual in actual_states:
            count = pairs.get((expected, actual), 0)
            if count == 0:
                cells.append("·")
            elif expected == actual:
                cells.append(f"**{count}**")
            else:
                cells.append(f"⚠ {count}")
        rows.append(f"| {expected} | {' | '.join(cells)} |")
    return "\n".join(rows)


def _uncertainty_coverage(reports: list) -> str:
    """How often each state is actually asserted, *including the ones that never are*.

    Counting only what appears is self-flattering: a state absent from the dataset shows
    up as no row at all rather than as a gap. Every state in the taxonomy is listed, so a
    zero is visible."""
    expected = Counter()
    for report in reports:
        for case in report.case_results:
            for _field, exp, _actual in case.observations:
                expected[exp] += 1

    all_states = [s.value for s in ClassificationState] + [s.value for s in EvidenceStatus]
    seen = list(dict.fromkeys(all_states))  # de-dupe NOT_APPLICABLE, shared by both enums

    rows = ["| State | Times asserted | |", "|---|---|---|"]
    for state in sorted(seen, key=lambda st: -expected.get(st, 0)):
        count = expected.get(state, 0)
        flag = "**never tested**" if count == 0 else ("thinly tested" if count < 3 else "")
        rows.append(f"| `{state}` | {count} | {flag} |")

    uncovered = [st for st in seen if expected.get(st, 0) == 0]
    note = ""
    if uncovered:
        note = (
            "\n\n> **Gap:** " + ", ".join(f"`{u}`" for u in uncovered) + " "
            + ("is" if len(uncovered) == 1 else "are")
            + " never asserted by any case. `POSSIBLY` in particular is load-bearing for this\n"
            "> project's central claim -- that it returns calibrated uncertainty rather than a\n"
            "> forced binary -- so the claim is currently supported by the schema and the\n"
            "> prompt, not by the eval dataset. Cases asserting it are the highest-value\n"
            "> addition to the golden set."
        )
    return "\n".join(rows) + note


def _failures(report, name: str) -> str:
    failed = [c for c in report.case_results if not c.passed]
    if not failed:
        return f"No failing cases in {name}."
    lines = [f"**{len(failed)} failing case(s) in {name}:**", ""]
    for case in failed:
        lines.append(f"- `{case.case_id}` ({case.difficulty}): {'; '.join(case.mismatches)}")
    return "\n".join(lines)


def main() -> None:
    session = _session()
    classification = run_golden_suite(session)
    adversarial_classification = run_golden_suite(session, cases_dir=EVALS / "adversarial" / "classification")
    evidence = run_evidence_golden_suite()
    adversarial_evidence = run_evidence_golden_suite(cases_dir=EVALS / "adversarial" / "evidence")

    total_cases = sum(r.total for r in (classification, adversarial_classification, evidence, adversarial_evidence))
    total_passed = sum(r.passed for r in (classification, adversarial_classification, evidence, adversarial_evidence))
    adversarial_total = adversarial_classification.total + adversarial_evidence.total
    adversarial_passed = adversarial_classification.passed + adversarial_evidence.passed

    content = f"""# Evaluation Results

<!-- GENERATED by scripts/generate_eval_report.py -- do not edit by hand. -->

Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d')} against the corpus and
prompts committed at that date. Regenerate with:

```
python scripts/generate_eval_report.py
```

## What these numbers do and don't prove

Every suite runs against `FakeCompletionProvider` with pre-authored responses, so these
measure the **pipeline**, not the model: retrieval, schema validation, citation
verification, uncertainty propagation, and the deterministic stages all being wired
correctly for a known input/output pair. A passing suite means a regression in any of
those breaks the build.

It is not a measure of how well a real LLM classifies AI systems. That requires running
the same cases against `AnthropicCompletionProvider` with a live key -- see
`evals/golden/classification_v1/README.md`. Reporting fake-provider results as model
accuracy would be the exact kind of overclaim this project's rules forbid.

## Headline

| Metric | Value |
|---|---|
| Total eval cases | {total_cases} |
| Passing | {total_passed} ({_pct(total_passed, total_cases)}) |
| Adversarial cases | {adversarial_total} |
| Adversarial resistance | {adversarial_passed}/{adversarial_total} ({_pct(adversarial_passed, adversarial_total)}) |

## Classification golden set

{_difficulty_table(classification)}

{_failures(classification, "the classification golden set")}

## Evidence golden set

{_difficulty_table(evidence)}

{_failures(evidence, "the evidence golden set")}

## Adversarial suites

Prompt injection, citation-bypass attempts, forced-binary pressure, and conflicting
actor roles. See `evals/adversarial/README.md` for the scenario-by-scenario coverage map.

| Suite | Cases | Passed | Rate |
|---|---|---|---|
| classification | {adversarial_classification.total} | {adversarial_classification.passed} | {_pct(adversarial_classification.passed, adversarial_classification.total)} |
| evidence | {adversarial_evidence.total} | {adversarial_evidence.passed} | {_pct(adversarial_evidence.passed, adversarial_evidence.total)} |

{_failures(adversarial_classification, "the adversarial classification suite")}

{_failures(adversarial_evidence, "the adversarial evidence suite")}

## Confusion matrices

Rows are what the case asserts; columns are what the pipeline produced. Bold on the
diagonal is correct; a ⚠ off-diagonal is a state being confused for another, which
matters more than the headline rate -- confusing `NO` for `INSUFFICIENT_INFORMATION` is
a very different failure from confusing it for `YES`.

{_confusion([classification, adversarial_classification], "Classification state")}

{_confusion([evidence, adversarial_evidence], "Evidence status")}

## Uncertainty coverage

The system's central claim is that it refuses to guess. That claim is only tested to the
extent the dataset actually asserts uncertain outcomes, so this counts how often each
state is expected across all suites.

{_uncertainty_coverage([classification, adversarial_classification, evidence, adversarial_evidence])}

A state with a low count is under-tested, not necessarily well-handled. The large
`INSUFFICIENT_INFORMATION` count is also partly an artefact rather than a virtue: three
of the five classification categories (scope, GPAI, transparency) have no ingested
corpus, so they return that state deterministically without any reasoning taking place.
It is counted here because the pipeline genuinely produces it, but it should not be read
as sixty demonstrations of good uncertainty handling.

## Not measured here

- **Live-model accuracy** -- needs an API key, see above.
- **Latency and token cost** -- the fake provider makes both meaningless.
- **Retrieval recall over the full Regulation** -- the corpus is a deliberate slice
  (`docs/legal-methodology.md`), so recall is measured against what is ingested, not
  against all ~180 articles.
"""
    OUTPUT.write_text(content)
    print(f"Wrote {OUTPUT.relative_to(REPO_ROOT)}: {total_passed}/{total_cases} cases passing.")


if __name__ == "__main__":
    main()
