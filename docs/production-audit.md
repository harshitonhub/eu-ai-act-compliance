# Production Readiness Audit

Self-audit against `.claude/skills/production-audit`, run 2026-09-14 against the state
at commit `5bcf8c0` (post multi-tenancy/RBAC), plus the fixes recorded below. Updated
2026-09-15 after closing H2's domain-attribution gap (see F4).

Findings are recorded as **area → severity → evidence → risk → recommendation → next
action**. Severity is about consequence if the finding is left alone, not about how hard
it is to fix.

A self-audit has an obvious conflict of interest: the person who built it is deciding
what counts as a problem. It is published anyway, with the unflattering findings kept in,
because the alternative — asserting production-readiness with no findings at all — is
less credible, not more. **H3 and M4 in particular are gaps a reviewer would otherwise
find first.**

---

## Verdict

**CONDITIONAL_PASS.**

Suitable for **internal single-organisation deployment** once H1 is closed.
**Not** suitable for selling as multi-customer compliance software until the High and
Medium findings are closed — chiefly the unaddressed legal-liability posture (H3), which
is not an engineering problem at all, and the missing security-event audit trail (M7),
which is a narrower gap than H2 was but still real: domain actions are now attributable
(see F4), authentication/authorization events still are not.

The core pipeline, isolation model, and legal-provenance chain are sound. What is missing
is mostly operational and organisational, not architectural — no finding below requires
redesigning anything already built.

| Severity | Count | Blocks internal use? | Blocks commercial use? |
|---|---|---|---|
| High | 2 | H1 | all |
| Medium | 6 | no | yes |
| Low | 5 | no | no |
| Fixed during audit | 4 | — | — |

---

## Fixed during this audit

### F1 · Architecture · was Medium
**Evidence:** `DETERMINISTIC_PACKAGES` in `tests/test_architecture_boundaries.py` listed
six packages. `systems/`, `incidents/`, `auth/`, and `persistence/` were all added later,
all documented in their own docstrings as deterministic/no-LLM, and none were enforced.
**Risk:** The "deterministic code decides business rules" invariant — the project's
central architectural claim — was unenforced for four of ten packages. An LLM import into
`incidents/` (deadline calculation) or `auth/` would have passed CI silently.
**Fix applied:** All four added to the list. Verified by injecting `from src.llm import
LLMClient` into `src/systems/registry.py` and confirming the test fails with
`src/systems/registry.py imports src.llm`, then reverting.
**Owner:** closed.

### F2 · Evaluation · was Medium
**Evidence:** No published eval metrics existed; suites ran as an opaque CI pass/fail.
**Risk:** "Fails closed on doubt" and "production-grade" were assertions with no evidence
a reader could check.
**Fix applied:** `scripts/generate_eval_report.py` → `docs/eval-results.md`, with pass
rates by difficulty, confusion matrices, and state-coverage gaps. Immediately surfaced
M4 below.
**Owner:** closed.

### F3 · Security · was Medium
**Evidence:** No password policy in the service layer — `create_user()` in
`src/auth/users.py` accepted any string. The 12-character minimum existed only in
`scripts/create_user.py`, i.e. in the CLI rather than the domain.
**Risk:** Any future signup route, admin UI, or import script would bypass the policy
entirely. The control was in the wrong layer — the same class of mistake as filtering by
tenant at the route instead of in the ORM.
**Fix applied:** `validate_password()` moved into `src/auth/users.py` and called by
`create_user()`, so every caller inherits it; the CLI now surfaces the domain error
instead of duplicating the rule. Length-only by design, per NIST SP 800-63B's advice
against composition rules. Covered by two new tests.
**Owner:** closed.

### F4 · Data governance / Observability · was High (H2)
**Evidence:** No table recorded *which user* performed any action. `AssessmentRecord` had
`tenant_id` and `ai_system_id` but no `created_by_user_id`; `Incident` likewise, plus no
`resolved_by_user_id` to say who marked it reported. Confirmed by grep across
`src/persistence/models.py`.
**Risk:** This was an audit and compliance tool whose own records could not answer "who
did this?" — disqualifying, since it undercut the RBAC work (roles constrain what can be
done, but nothing recorded who did it).
**Fix applied:** Added `created_by_user_id` (FK to `users`, nullable — historical rows
predate the column and nothing should synthesize an answer for them) to
`AssessmentRecord`; `created_by_user_id` and `resolved_by_user_id` to `Incident`. Threaded
through `src/observability/assessment_log.py` and `src/incidents/registry.py` as raw ids
(resolution to a display email is the router's job, keeping those modules decoupled from
auth), captured from the authenticated user on every write route, and rendered in
`report.html`, `impact_assessment.html`, `history.html`, and `ai_system_detail.html`.
Migration `807e76e09ecc` uses SQLite batch mode (plain `ALTER ... ADD CONSTRAINT` isn't
supported); upgrade/downgrade round-trip verified by hand. 7 new tests covering round-trip
persistence and end-to-end HTML rendering; also verified live against `scripts/demo.py`
via Playwright — every surface shows the acting user's email after a real login.
**Scope note:** This closes the "who performed this domain action" half of H2. The other
half — a dedicated append-only audit log for security events (login, failed login, role
change) independent of the domain tables — is not done; tracked as [M7](#m7).
**Owner:** closed.

---

## High

### H1 · Operational readiness · High
**Evidence:** `DATABASE_URL` defaults to `sqlite:///./dev.db` (`src/persistence/db.py`).
No backup procedure, restore drill, or migration runbook is documented anywhere.
**Risk:** Total, unrecoverable data loss from a single deleted file. For a system holding
the evidence trail behind regulatory compliance decisions, losing history may itself be a
compliance failure — the customer can no longer show what they assessed or when.
**Recommendation:** Postgres for any real deployment (SQLAlchemy already abstracts it —
no code change). Automated backups with a *tested* restore, not just a configured one.
**Next action:** Document the Postgres + backup path in `README.md` before any non-throwaway
deployment.

### H3 · Legal knowledge / Governance · High
**Evidence:** `Requirement.summary` values are engineer-authored restatements
(`docs/legal-methodology.md` says so plainly). No qualified legal review has occurred.
The corpus covers ~15 of ~180 AI Act articles and 2 of ~99 GDPR articles.
**Risk:** Users may act on a classification derived from a non-lawyer's paraphrase of the
law. A wrong `NO` on a prohibited practice has regulatory consequences for the user and
liability consequences for the operator. Not mitigated by engineering quality.
**Recommendation:** Legal review and sign-off of every requirement summary before any
commercial use; professional indemnity cover; prominent in-product disclaimer that output
is decision support, not legal advice.
**Next action:** Blocks commercial use only. Not an engineering task — do not attempt to
solve it with code.

---

## Medium

### M1 · Security · Medium
**Evidence:** Rate limiting is an in-process dict (`src/api/rate_limit.py`), keyed on
`request.client.host` with no `X-Forwarded-For` handling. Documented as a known limit.
**Risk:** Behind a load balancer every caller shares the proxy's IP — one user exhausts
everyone's quota (DoS), or the limit is trivially bypassed across instances. Applies to
the login limiter too, weakening credential-stuffing defence.
**Recommendation:** Redis-backed limiter and trusted-proxy `X-Forwarded-For` parsing
before running more than one instance.
**Next action:** Required before horizontal scaling; harmless single-instance.

### M2 · Security · Medium
**Evidence:** No server-side session store. Sessions are stateless signed cookies with a
12-hour expiry (`src/auth/sessions.py`).
**Risk:** A stolen cookie is valid until expiry and cannot be revoked. Rotating
`SESSION_SECRET` is the only remedy and signs out every user of every tenant.
**Recommendation:** `Session` table with a revocable id, checked per request.
**Next action:** Before handling genuinely sensitive customer data.

### M4 · Evaluation · Medium
**Evidence:** `docs/eval-results.md` (generated) shows `POSSIBLY` asserted by **zero**
cases across all four suites. Separately, 60 of 90 classification observations expect
`INSUFFICIENT_INFORMATION`, most of which come from three categories with no ingested
corpus rather than from genuine uncertainty reasoning.
**Risk:** The project's headline claim is calibrated uncertainty over forced binaries.
`POSSIBLY` is the state that embodies it and it is supported by the schema and prompt but
never by a test. A regression that stopped the pipeline ever returning `POSSIBLY` would
pass CI green.
**Recommendation:** Add golden cases asserting `POSSIBLY` — the Article 6(3) derogation
and borderline Annex III cases are natural candidates.
**Next action:** Highest-value evaluation work. ~2 hours.

### M5 · Reliability · Medium
**Evidence:** `/health` returns a static `{"status": "ok"}` without touching the database
or checking migration state. No metrics, no error tracking, no alerting.
**Risk:** A healthy-looking instance with an unreachable database or an un-migrated schema
passes its own health check. Failures are discovered by users.
**Recommendation:** `/health` should verify DB connectivity and Alembic head; add error
tracking (Sentry or equivalent) and uptime monitoring.
**Next action:** Before any deployment with real users.

### M6 · Observability · Medium
**Evidence:** No application logging anywhere in `src/` — no `logging` import, no logger.
`AssessmentRecord` persists rich per-assessment traces, but there is no operational log of
requests, auth outcomes, or errors.
**Risk:** Production issues are undiagnosable after the fact. Combined with M7, a security
incident would leave almost nothing to investigate.
**Recommendation:** Structured JSON logging with a request id; never log evidence text,
credentials, or session cookies.
**Next action:** Pair with M7 — same sitting.

### M7 · Observability / Security · Medium
**Evidence:** No append-only security-event log. Login, failed login, logout, and role
change (`src/auth/sessions.py`, `src/auth/users.py`) are not recorded anywhere — the
domain-attribution gap this replaces ([F4](#f4-data-governance--observability--was-high-h2))
covers *what a user did in the product*, not *who tried to authenticate or was granted a
new role*.
**Risk:** A brute-force attempt, a suspicious login pattern, or a privilege escalation
leaves no record to investigate after the fact — the same blind spot H2 used to describe,
narrowed now to the auth boundary specifically.
**Recommendation:** A dedicated append-only `AuditEvent` table (actor id, event type,
timestamp, source IP) written on login success/failure, logout, and role change — separate
from `AssessmentRecord`/`Incident` so it survives even if domain rows are deleted or
redacted.
**Next action:** Natural pairing with M6 — same sitting.

---

## Low

### L1 · Security · Low
CSRF defence rests entirely on `samesite=lax` (`src/api/routers/auth_routes.py`). That
does block cross-site POSTs in current browsers, so this is defence-in-depth rather than
an open hole, but there is no token as a second layer.
**Next action:** Add per-session CSRF tokens if the app ever serves a wider audience.

### L2 · Security · Low
No account lockout after repeated failed logins — only the 10-per-5-minute IP rate limit.
A distributed attacker with many IPs is unthrottled per-account.
**Next action:** Per-account failure counter alongside the per-IP limit.

### L3 · Data governance · Low
Evidence text — potentially containing personal data — is stored unencrypted at rest.
Retention (90 days) and on-demand deletion exist; encryption does not.
**Next action:** Rely on database-level/disk encryption in deployment; document it as a
deployment requirement rather than an application feature.

### L4 · Legal knowledge · Low
No automated re-fetch/diff of source legal text. The `legal-source-update` skill was never
implemented, so a change to the underlying law is detected by a human noticing.
`supersede_requirement` and the Phase B alerting exist to *handle* an update; nothing
*detects* one.
**Next action:** Scheduled re-fetch comparing `raw_fetch_sha256`. Note EUR-Lex now blocks
automated access — use the Cellar API path documented in `docs/legal-methodology.md`.

### L5 · Reproducibility · Low
Per-LLM-call `prompt_version` is captured, but there is no single retrieval-configuration
version stamp. Documented in `src/observability/assessment_log.py` as acceptable while
retrieval has had one implementation.
**Next action:** Add when a second retrieval strategy lands.

---

## Areas assessed with no findings above Low

- **Architecture.** Boundaries hold and are now enforced for all ten deterministic
  packages (F1). No circular dependencies; `src/llm` is not reachable from deterministic
  code; the modular monolith is appropriate to the scale.
- **AI/LLM behaviour.** Citations are structurally required by a Pydantic validator, not
  by prompt wording; hallucinated citations are caught deterministically by
  `verify_citations` and fail closed to `INSUFFICIENT_INFORMATION`; malformed output
  retries once then fails closed. Prompt injection, forced-binary pressure, and
  citation-bypass all have adversarial cases.
- **Security (tenant isolation).** Enforced at the ORM layer with fail-closed behaviour on
  three distinct failure modes, and the test suite is mutation-verified — disabling the
  read filter fails 11 of 17 cases, disabling the write guard errors 15. This is the
  strongest control in the system.
- **Legal knowledge (provenance).** Every provision traces to a verbatim fetch with a
  recorded SHA-256; no LLM sits in the extraction path; versioning never overwrites.
  Article 73's three-tier deadline structure was verified against source text and
  corrected a wrong assumption in this project's own planning notes.
- **Reproducibility.** Any past assessment reconstructs fully from stored data — facts,
  classification, obligations, evidence, review flags, LLM call metadata.
- **Documentation.** Unusually complete and, importantly, honest about scope limits.
  `docs/security-model.md` names what is *not* covered.

---

## If only three things get done

1. **H1** — a real database and a tested backup/restore path, since SQLite-with-no-backup
   is one deleted file from unrecoverable data loss.
2. **M4** — golden cases for `POSSIBLY`, so the central claim is tested rather than
   asserted.
3. **M7 + M6 + M5** — a security-event audit log, application logging, and a health check
   that actually checks something; together they make a deployed instance diagnosable and
   investigable.

F1, F2, F3, and F4 were closed during the audit itself.
