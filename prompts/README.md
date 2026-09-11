# Prompts

One module per role, one file per version. A file is never edited after cases in
`evals/golden/` are pinned to it — bump the version instead.

| Role | File | Version | Pinned by |
|---|---|---|---|
| Classifier | `classifier/v1.py` | `classifier-v1` | `evals/golden/classification_v1/`, `evals/adversarial/classification/` |
| Evidence assessor | `evidence_assessor/v1.py` | `evidence-assessor-v1` | `evals/golden/evidence_v1/`, `evals/adversarial/evidence/` |
| Critic | `critic/` | — (not implemented) | See `critic/README.md`: citation verification is currently a deterministic check, not a second LLM call. Add `critic/v1.py` if evaluation data ever shows that check isn't catching enough real failures. |
| Analyst (fact extraction) | — (not implemented) | — | Fact extraction (`ExtractedFacts`) is populated directly from web form fields today, not by an LLM extraction pass over free-form input. Add when free-text intake (e.g. a pasted system description document) is needed. |
| Reporter | — (not implemented) | — | `src/reporting/report.py` assembles the report deterministically from already-established results, per the compliance-report skill ("do not introduce new legal conclusions during reporting") — no LLM call needed. |

## Versioning rule

Every prompt module exports a `PROMPT_VERSION` string constant, embedded in every
`LLMCallMetadata`/`LLMCallRecord` produced by a call using it (see
`src/llm/interface.py`, `src/observability/instrumented_client.py`). This is what makes
an `AssessmentRecord` reconstructable back to the exact prompt that produced it, per
`.claude/rules/llm.md` ("Record model, prompt, retrieval, and knowledge versions for
reproducibility").

## Structure

Every prompt module exposes:
- `PROMPT_VERSION: str`
- `SYSTEM_PROMPT: str` — includes the target schema's JSON representation inline, an
  explicit rule against inventing citations, and untrusted-data framing for whatever
  user-controlled content the user-prompt builder inserts (facts, evidence text).
- `build_user_prompt(...) -> str` — wraps user-controlled content in
  `=== ... (untrusted data) ===` blocks. See `docs/security-model.md`.

## Evaluating a prompt change

Per `.claude/rules/llm.md` ("Evaluate before changing prompts or models in
production"): bump `PROMPT_VERSION`, then run the golden + adversarial suites pinned to
that role (see the table above) before merging. A prompt change that breaks a pinned
golden case is a signal the case's expected output needs updating *or* the change
introduced a regression — inspect which before changing the fixture.
