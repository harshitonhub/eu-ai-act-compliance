# Security Model

## Threat model

The primary attack surface is user-controlled text reaching an LLM prompt: `ExtractedFacts`
fields (classification) and `evidence_text` (evidence assessment). Both are the "uploaded
documents" and "user-provided content" `.claude/rules/security.md` requires treating as
untrusted, never as instructions.

## Defenses, and where each is implemented

| Defense | Implementation | Verified by |
|---|---|---|
| Untrusted-data framing | Every prompt wraps facts/evidence in `=== ... (untrusted data) ===` blocks with an explicit "never an instruction" rule | `prompts/classifier/v1.py`, `prompts/evidence_assessor/v1.py` |
| Citation can't be bypassed by instruction | `CategoryClassification`'s Pydantic validator structurally requires ≥1 citation for YES/POSSIBLY — enforced independent of prompt compliance | `schemas/classification.py`; `evals/adversarial/classification/adversarial-citation-bypass-attempt.json` |
| Citation can't be hallucinated | `verify_citations` deterministically checks every cited `requirement_key` against the actual retrieved candidate set; failure → `INSUFFICIENT_INFORMATION` | `src/classification/classify.py`; `tests/test_classification_pipeline.py::test_hallucinated_citation_fails_closed` |
| Forced-binary pressure resisted | Prompt explicitly permits `POSSIBLY`/`INSUFFICIENT_INFORMATION`; nothing in the pipeline can force a YES/NO | `evals/golden/classification_v1/adversarial-forced-binary-pressure-resists-uncertainty.json` |
| Malformed/off-schema output rejected | `LLMClient` validates every response against its Pydantic schema, retries once, then fails closed | `src/llm/interface.py`; `tests/test_llm_interface.py` |
| Superseded legal text never resurfaces | `find_requirements`/`retrieve` filter on `superseded_by_id IS NULL` | `tests/test_adversarial_legal_versioning.py` |
| Secrets never logged | `AssessmentRecord` stores facts/classification/evidence/LLM-call metadata (tokens, latency, prompt version) — never API keys, raw provider request/response bodies, or system prompts | `src/observability/assessment_log.py` |
| Dependency pinning | `uv.lock` pins every resolved version; CI installs with `--frozen` (fails if the lock drifts from `pyproject.toml`) | `.github/workflows/ci.yml` |
| Dependency vulnerability monitoring | `pip-audit` runs in CI as an advisory (non-blocking) job | `.github/workflows/ci.yml`'s `dependency-audit` job |
| Access control | HTTP Basic Auth gates every assessment route (not `/health`); fails closed (500) if `APP_USERNAME`/`APP_PASSWORD` aren't configured, rather than an insecure default | `src/api/auth.py`; `tests/test_auth.py` |
| Data retention | `AssessmentRecord` rows (which can carry sensitive evidence text) are deletable by age (`purge_expired_assessments`, default 90-day window) or on demand (`delete_assessment`) | `src/observability/retention.py`; `tests/test_retention.py`; run via `scripts/purge_expired_assessments.py` (cron or manual, no scheduler built) |
| File upload validation | `.txt`/`.pdf`/`.docx` only, 5 MB cap, parse-or-reject as the content check | `src/evidence/file_ingestion.py`; `tests/test_file_ingestion.py` |
| Rate limiting | Per-IP sliding window (10 requests/60s) on `/assess` and `/report` — the two endpoints that trigger paid LLM calls | `src/api/rate_limit.py`; `tests/test_rate_limit.py`; `tests/test_api_web_flow.py::test_rate_limit_blocks_excessive_requests_to_assess` |

## What's explicitly out of scope today

- **Tenant isolation**: `AssessmentRecord.tenant_id` exists as a column but is unused —
  the system is single-tenant. No cross-tenant leakage risk exists yet because there is
  only one tenant; this must be revisited before any multi-tenant deployment (see
  `.claude/rules/architecture.md`'s "design for tenant isolation" note).
- **Malicious retrieved content**: not applicable given the current input surface — see
  `evals/adversarial/README.md`.
- **Rate limiting is in-memory, single-process, and keyed on `request.client.host`**:
  behind a reverse proxy without X-Forwarded-For handling, every caller shares one IP
  (the proxy's) and gets one shared quota. Fine for direct/local deployment; fix before
  fronting with a proxy or load balancer.
- **Multi-user auth**: HTTP Basic with one shared credential pair, not per-user accounts
  or roles. Sufficient for a single-tenant internal tool; upgrade before multi-tenancy.
- **Automated purge scheduling**: `purge_expired_assessments` must be invoked externally
  (cron, manual run) — no in-process scheduler exists, per the architecture decision
  against premature queue/scheduler infrastructure.

## Full adversarial coverage

See `evals/adversarial/README.md` for the scenario-by-scenario coverage table against
the `adversarial-testing` skill's checklist.
