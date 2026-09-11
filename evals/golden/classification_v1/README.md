# Golden dataset — classification_v1

16 hand-built cases against the seed legal corpus (Article 5, Article 6, Annex III --
see `docs/legal-methodology.md`). Pinned to prompt version `classifier-v1`
(`prompts/classifier/v1.py`); bump the directory name (`classification_v2/`) if the
prompt or schema changes in a way that would invalidate these cases' expected outputs.

## Difficulty distribution

| difficulty | count | what it tests |
|---|---|---|
| obvious | 6 | clear-cut YES/NO cases across prohibited practices and Annex III areas |
| exception | 2 | the Article 5(1)(d) and 5(1)(f) built-in exception clauses |
| borderline | 2 | the Article 6(3) narrow-procedural-task derogation, including its profiling carve-back |
| insufficient_information | 2 | facts too vague to support a definite answer |
| adversarial | 2 | prompt injection and forced-binary pressure embedded in system facts |
| temporal | 2 | `NOT_APPLICABLE` vs `INSUFFICIENT_INFORMATION` around Article 113's effective dates |

## What running this suite proves, and what it doesn't

`evals/runner.py` replays each case through the real `classify_system()` pipeline --
real retrieval, real schema validation, real deterministic citation verification --
using a `FakeCompletionProvider` primed with each case's own `fake_llm_responses`. This
is a **harness and regression check**: it proves the pipeline correctly wires facts
through to a classification given a known model output, and that the deterministic
guardrails (citation verification, temporal NOT_APPLICABLE handling, zero-candidate
short-circuiting) behave as designed.

It does **not** prove a live model would produce those `fake_llm_responses` in the first
place. The two `adversarial` cases in particular have fixtures representing the
*correct, resistant* output — they validate that the pipeline scores a resistant
response correctly, not that a real model resists the embedded injection. Measuring
actual model quality/robustness requires re-running these same cases with
`AnthropicCompletionProvider` in place of the fake, against a live API key, and
comparing outputs to `expected_states` by hand or with a scoring pass — that's manual/CI-
optional work, not part of the default `pytest` suite (which must stay offline per
Phase 2's DoD).

## Format

Each `*.json` case has: `case_id`, `difficulty`, `as_of` (ISO date), `facts` (an
`ExtractedFacts`-shaped dict), `fake_llm_responses` (raw JSON strings keyed by category,
one per category the pipeline will actually call the LLM for for this case — see
`evals/runner.py:_categories_requiring_an_llm_call`), `expected_states` (all 5 category
values), and a human-readable `notes` field.
