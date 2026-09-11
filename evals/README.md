# Evaluation strategy

Three suites, all offline (no live API key required — see each suite's own README for
the scope caveat this implies):

| Suite | Cases | Runner | Purpose |
|---|---|---|---|
| `golden/classification_v1/` | 16 | `runner.py:run_golden_suite` | Classification pipeline correctness across obvious/borderline/exception/insufficient-info/adversarial/temporal cases |
| `golden/evidence_v1/` | 8 | `evidence_runner.py:run_evidence_golden_suite` | Evidence assessment correctness, including 2 contradictory-evidence scenarios |
| `adversarial/` | 5 (2 classification + 1 evidence + 2 structural pytest) | both runners, pointed at `adversarial/` + `test_adversarial_legal_versioning.py` | The `adversarial-testing` skill's checklist — see `adversarial/README.md` for the scenario-by-scenario coverage map |

## What these suites prove, and what they don't

Every suite replays a fixed input through the **real** pipeline (real retrieval, real
Pydantic schema validation, real deterministic citation/evidence checks) using a
`FakeCompletionProvider` primed with a pre-authored "correct" response. This proves the
harness — facts → retrieval → LLM call → validation → downstream logic — is wired
correctly and regresses loudly if it breaks. It does **not** measure whether a live
model would actually produce that response; that requires re-running the same cases with
`AnthropicCompletionProvider` against a real API key and comparing outputs by hand (or a
future scoring pass) — deliberately kept out of the default `pytest` suite so CI never
needs a live key.

## Metrics tracked

- **Classification/evidence correctness**: exact state match per case (`CaseResult.passed`).
- **Citation/provenance quality**: enforced structurally, not just measured — see
  `schemas/classification.py`'s validator and `verify_citations` in
  `src/classification/classify.py`.
- **Uncertainty handling**: explicit cases assert `INSUFFICIENT_INFORMATION`/
  `NOT_APPLICABLE`/`POSSIBLY` where a naive system would guess YES/NO.
- **Security/prompt-injection resistance**: `adversarial/` suite (harness-level, per the
  caveat above).
- **Latency/token/cost**: tracked per real assessment via `AssessmentRecord` (see
  `src/observability/`), not per offline eval case — a fake provider's token counts are
  synthetic and would be meaningless as an eval metric.

## Running

`pytest` runs everything, including all three suites, as part of the normal test run
(`tests/test_eval_golden_classification.py`, `tests/test_eval_golden_evidence.py`,
`tests/test_eval_adversarial_suite.py`). CI (`.github/workflows/ci.yml`) runs the same
`pytest` invocation — there is no separate eval-only job.

## Adding a case

Golden/adversarial cases are hand-authored JSON (see each suite's README for the exact
field format). There is no case-generation tooling; write the JSON directly, or use a
throwaway generator script (not committed) if authoring many at once, as was done for
the initial 16 classification cases.
