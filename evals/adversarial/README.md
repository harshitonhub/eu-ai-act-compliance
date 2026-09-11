# Adversarial suite — coverage map

The `adversarial-testing` skill lists ten scenarios to test. Rather than duplicate
coverage that already exists in `evals/golden/*` from Phases 3-4, this suite adds only
what closes a genuine gap; everything else is mapped to where it's already covered.

| Skill scenario | Coverage | Where |
|---|---|---|
| Misleading system descriptions | Existing | `classification_v1/adversarial-prompt-injection-in-description.json` |
| Contradictory evidence | Existing | `evidence_v1/non-compliant-contradictory-human-oversight-docs.json`, `non-compliant-contradictory-risk-assessments.json` |
| Missing critical facts | Existing | `classification_v1/insufficient-info-*.json` (2 cases) |
| Prompt injection in uploaded documents | **New** | `adversarial/evidence/injection-in-evidence-text.json` -- an evidence text embeds an instruction demanding a COMPLIANT rating; the fixture's correct/resistant response is NON_COMPLIANT |
| Malicious retrieved content | **N/A given current input surface** | Retrieved legal text comes only from the vetted, manually-ingested corpus (`legal/sources/`) -- there is no user-controlled path into what gets retrieved for classification. Revisit if/when retrieval ever indexes user-supplied documents. |
| Outdated legal sources | **New** | `tests/test_adversarial_legal_versioning.py` -- verifies a superseded `Requirement` version is permanently excluded from `find_requirements`/`retrieve`, regardless of query or `as_of` |
| Forced YES/NO classification | Existing | `classification_v1/adversarial-forced-binary-pressure-resists-uncertainty.json` |
| Conflicting actor roles | **New** | `adversarial/classification/adversarial-conflicting-actor-roles.json` |
| Edge cases around exceptions | Existing | `classification_v1/exception-*.json` (2 cases), `borderline-highrisk-narrow-task-with-profiling-yes.json` |
| Attempts to make the model ignore provenance | **New** | `adversarial/classification/adversarial-citation-bypass-attempt.json` -- demonstrates the citation requirement is enforced structurally (Pydantic validator on `CategoryClassification`), not just by prompt instruction, so no prompt-level "ignore provenance" instruction can bypass it |

## What's genuinely new here vs. Phase 3/4

- Two new classification-format cases (`adversarial/classification/`), run via the same
  `evals/runner.py:run_golden_suite` used for the main golden set, just pointed at this
  directory.
- One new evidence-format case (`adversarial/evidence/`), run via
  `evals/evidence_runner.py:run_evidence_golden_suite` pointed at this directory.
- One new structural pytest (`test_adversarial_legal_versioning.py`) for a scenario that
  isn't really an "LLM response" case -- it's a guarantee about the deterministic
  retrieval layer, so it's tested directly rather than via a replayed fake LLM response.
