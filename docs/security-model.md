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
| Authentication | Signed session cookies (HMAC-SHA256 over `user_id\|expiry`, `httponly`, `samesite=lax`); fails closed if `SESSION_SECRET` is unset. Passwords are PBKDF2-HMAC-SHA256 at 600k iterations, per-password salt | `src/auth/sessions.py`, `src/auth/passwords.py`; `tests/test_auth.py` |
| Authorization (RBAC) | Three roles: ADMIN, MEMBER, VIEWER. Every write route depends on `require_writer`, so VIEWER is genuinely read-only -- an auditor can be given access without the ability to alter what they audit | `src/api/auth.py`; `tests/test_auth.py::test_viewer_cannot_write` |
| **Tenant isolation** | Enforced by SQLAlchemy event listeners, not by query-site discipline: every ORM SELECT touching a tenant-owned table has the tenant filter injected automatically, every insert is stamped, and cross-tenant writes are refused on flush. A query that *forgets* to filter cannot leak -- it raises or returns only the bound tenant's rows | `src/persistence/tenancy.py`; `tests/test_tenant_isolation.py`, `tests/test_tenant_isolation_http.py` |
| IDOR resistance | Knowing another tenant's UUID is not enough: `/systems/{id}`, `/assessments/{id}`, `/incidents/{id}/mark-reported` all 404 across a tenant boundary, and the 404 body never distinguishes "absent" from "not yours" | `tests/test_tenant_isolation_http.py` |
| Credential-stuffing resistance | `/login` has its own rate limit (10 per 5 min per IP), separate from the public one, and returns an identical message for unknown-email and wrong-password with comparable timing | `src/api/rate_limit.py`, `src/auth/users.py::authenticate` |
| Data retention | `AssessmentRecord` rows (which can carry sensitive evidence text) are deletable by age (`purge_expired_assessments`, default 90-day window) or on demand (`delete_assessment`) | `src/observability/retention.py`; `tests/test_retention.py`; run via `scripts/purge_expired_assessments.py` (cron or manual, no scheduler built) |
| File upload validation | `.txt`/`.pdf`/`.docx` only, 5 MB cap, parse-or-reject as the content check | `src/evidence/file_ingestion.py`; `tests/test_file_ingestion.py` |
| Rate limiting | Per-IP sliding window: 10 requests/60s on the authenticated `/assess` and `/report`; a stricter 3 requests/60s on the public, no-auth `/ai-risk-check`; and a separate 10-per-5-min budget on `/login` | `src/api/rate_limit.py`; `tests/test_rate_limit.py`; `tests/test_api_web_flow.py::test_rate_limit_blocks_excessive_requests_to_assess`; `tests/test_ai_risk_check.py::test_public_rate_limit_is_stricter_than_authenticated_endpoints` |

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
- **Account lifecycle**: users are provisioned by `scripts/create_user.py`; there is no
  self-service sign-up, password reset, email verification, or MFA. Deliberate for an
  invite-only B2B tool, but all four are table stakes before open registration.
- **Session revocation**: sessions are stateless signed cookies, so a stolen cookie stays
  valid until it expires (12h) -- there is no server-side session store to revoke against.
  Rotating `SESSION_SECRET` invalidates every session at once, which is the current blunt
  instrument. Add a session table if per-session revocation is needed.
- **Automated purge scheduling**: `purge_expired_assessments` must be invoked externally
  (cron, manual run) — no in-process scheduler exists, per the architecture decision
  against premature queue/scheduler infrastructure.

## Full adversarial coverage

See `evals/adversarial/README.md` for the scenario-by-scenario coverage table against
the `adversarial-testing` skill's checklist.
