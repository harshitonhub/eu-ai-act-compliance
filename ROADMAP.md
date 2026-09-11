# Roadmap

Ordered by dependency, not just preference — several later phases need a foundation
earlier phases build. Effort is rough (S = hours, M = a day, L = multi-day). Nothing
here is started; this is the plan, not a changelog.

## Phase A — AI system registry (S/M)
**Unlocks:** B, D, E, and makes the history page group by system instead of a flat list.

New `AISystem` table (name, description, owner note, created_at). `AssessmentRecord`
gets an `ai_system_id` FK. `/history` becomes "My AI Systems," each with its own
assessment history, instead of one flat list of unrelated runs. Without this, re-
assessment reminders, deadline tracking, and update alerts have nothing to attach to.

## Phase B — Regulatory update alerts (S)
**Depends on:** A. **Why cheap:** the versioning infra (`supersede_requirement`,
`superseded_by_id`) already exists from Phase 1 — this is the first feature to actually
use it for something user-facing.

When a requirement gets superseded, flag every AI system whose latest assessment cited
the old version: "this conclusion may be outdated — a newer version of EU-AI-ACT-ART9
exists." No competitor surfaced in the research does this because most tools don't
track requirement versions at all, let alone diff against a user's past conclusions.

## Phase C — Auto-generated Impact Assessment / export (S)
**Depends on:** nothing new — `ComplianceReport` already has every field needed.

Print-friendly CSS + a formatted document view of the existing report data (no new
dependency; browser "print to PDF" off clean CSS). Directly answers a gap the research
confirmed nobody in the market has solved ("no platform generates AI Impact Assessments
for you").

## Phase D — Deadlines dashboard (S)
**Depends on:** A. Aggregates, per system: re-assessment due date (`as_of` + N months),
and any `NOT_APPLICABLE` classification that will flip to applicable on a known future
date (Article 113 dates are already stored). One view instead of checking each system.

## Phase E — Incident logging, Article 73 (M)
**Depends on:** A (an incident belongs to a system). Net-new: no current feature covers
this at all. New `Incident` table, deadline countdown (2 days for severe/widespread, 15
otherwise, per the Article 73 text), reported/not-reported state.

## Phase F — Reusable evidence vault (M)
**Independent**, but touches the evidence-submission UI significantly. New
`EvidenceDocument` table — upload a policy once, attach it to any obligation on any
system, instead of re-uploading the same document per obligation per assessment. This
is the concrete answer to the actual cost driver behind SME compliance (research: 1-2
FTE doing repetitive manual work).

## Phase G — Real RBAC + multi-tenancy (L)
**Independent of A-F**, but a prerequisite for H. Replaces the single shared Basic Auth
pair with a `User` table, real login, and roles. Wires the already-existing but unused
`tenant_id` column into actual query-level isolation. This is the biggest single lift
in this roadmap — everything else is additive; this touches auth on every route.

## Phase H — Gap ownership + status (S)
**Depends on:** G (needs real users to assign to). Turns a `Gap` from a report line
into a lightweight task: assigned owner, status (open/in-progress/done). Requires
persisting gaps as rows, not just computing them on the fly per report.

## Phase I — "Am I affected?" scope quiz (S)
**Independent.** A 5-question, no-login entry point before the full assessment form —
thin wrapper around existing scope/prohibited-practice logic. Lowers the barrier for
the 78% of orgs (per the research) who haven't started because they don't know where
they stand.

## Phase J — NIST AI RMF corpus (M)
**Independent.** NIST AI RMF is US public domain — can be verbatim-ingested the same
way Article 5/6/9-15 were. **ISO 42001 cannot be done this way — its text is
copyrighted/paywalled**, unlike EUR-Lex or NIST. An ISO 42001 layer would have to
reference clause *numbers* only, never quote the standard, which is weaker than this
system's citation-enforcement story. Do NIST first; treat ISO 42001 as a separate,
lower-confidence follow-up if pursued at all.

---

## Suggested build order

1. **A → B** (foundation + the one genuinely novel differentiator, both cheap)
2. **C** (closes a confirmed market gap, no dependencies, cheap)
3. **D, E** (natural extensions of A, moderate effort)
4. **F** (biggest real cost-reduction for actual users, independent)
5. **G → H** (biggest lift, only worth it once ready for real multi-user/production use)
6. **I, J** (independent, do whenever — I is nearly free, J is content work)
