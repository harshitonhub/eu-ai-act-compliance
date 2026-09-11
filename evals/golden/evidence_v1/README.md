# Golden dataset — evidence_v1

8 hand-built cases against the Article 9-15 obligation set (see
`docs/legal-methodology.md`'s "Obligation mapping basis"). Pinned to prompt version
`evidence-assessor-v1` (`prompts/evidence_assessor/v1.py`).

## Difficulty distribution

| difficulty | count | what it tests |
|---|---|---|
| obvious | 2 | clear-cut compliant cases with thorough, specific, current evidence |
| partial | 1 | a generic/vague policy that exists but doesn't substantively support compliance |
| contradictory | 2 | two evidence documents disagreeing with each other (DoD-required coverage) |
| insufficient | 1 | evidence text present but contentless ("see attached documentation") |
| outdated | 1 | the currency dimension specifically -- a stale, pre-AI-Act security policy |
| no_evidence | 1 | the deterministic zero-LLM-call shortcut when evidence_text is empty |

## Scope note

Same caveat as `evals/golden/classification_v1/README.md`: this suite proves the
pipeline (schema validation, requirement_key matching, the no-evidence shortcut) wires
correctly given a known model output. It does not prove a live model would produce that
`fake_llm_response` -- particularly for the two `contradictory` cases, whose fixtures
represent the *correct* contradiction-detection output. Measuring whether a real model
actually notices the contradiction requires running these cases against
`AnthropicCompletionProvider` with a live key, not the default offline `pytest` suite.

## Format

Each `*.json` case has: `case_id`, `difficulty`, `obligation` (requirement_key/citation/
summary), `evidence_text`, `fake_llm_response` (raw JSON string, or `null` for the
no-evidence case where no LLM call happens), `expected_status`,
`expected_contradictions_present`, and a human-readable `notes` field.
