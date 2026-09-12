# Roadmap

Ordered by dependency, not just preference — several later phases need a foundation
earlier phases build. Effort is rough (S = hours, M = a day, L = multi-day). Nothing
here is started; this is the plan, not a changelog.

## Committed starting niche: hiring/recruitment AI (Annex III point 4)

Decided over the other 7 Annex III categories for reasons that hold up independent of
which category happened to get researched first: employment is the only **horizontal**
Annex III category (every company that hires anyone is a potential deployer, unlike
credit/infrastructure/migration/justice which are vertical-specific); most companies
**deploy** rather than build recruitment AI (Workday/Greenhouse/HireVue-style tools),
so the target user describes a vendor's tool rather than needing to understand a model
they built themselves — a much lower usability bar; and it was the largest of the
first three EU AI Act fines (€18M of €47M, for missing conformity docs and no human
oversight). Not independently verified against the other 7 categories — a fair
challenge to revisit if this niche underperforms.

First build against this niche: a standalone, public, no-login "AI Risk Check" —
one text box, one plain-English answer, reusing the existing classification pipeline
end to end. The hero copy leads with the hiring-AI fine as the hook, but the check
itself was broadened to cover any AI system across all 8 Annex III categories almost
immediately — the classify_system pipeline already checked all of them regardless;
narrowing the page to hiring-only was a copy choice, not a technical constraint, and it
made the tool feel more limited than it is. See `src/api/routers/ai_risk_check.py`.

## Why this matters now, concretely

First EU AI Act enforcement action (August 2026) issued €47M across three cases: €18M
for hiring AI deployed without conformity assessment documentation or human oversight,
€14M for a credit-scoring "black box" that denied consumers an explanation, €15M for a
prohibited real-time emotion-recognition system. Those three cases map directly onto
scenario types already in this project's golden dataset (Annex III-4 recruitment,
Annex III-5 creditworthiness, Article 5(1)(f) emotion recognition) — not a coincidence
worth burying, a direct proof point that this system is built for what regulators are
actually fining.

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

## Phase D — Deadlines dashboard + drift-triggered reassessment (S/M)
**Depends on:** A. Aggregates, per system: re-assessment due date (`as_of` + N months),
and any `NOT_APPLICABLE` classification that will flip to applicable on a known future
date (Article 113 dates are already stored). One view instead of checking each system.

Sharper than a calendar reminder alone: orgs that catch AI issues via internal
monitoring hit 87.5% compliance vs. 5.3% for externally-detected incidents — the real
problem isn't "the assessment is old," it's "did the underlying system change." If a
system's description/facts are edited, prompt a re-classification rather than waiting
for a date to pass — a retrained/updated model is "a materially different risk object"
even under the same name.

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

## Phase K — "Explain this rejection" mode (S)
**Independent**, reuses all existing classification logic. A stripped-down single-
purpose flow answering just "why was this decision high-risk / not high-risk" — aimed
at the person fielding a candidate's or customer's question (HR, support), not the
compliance officer running a full assessment. Directly answers a documented gap: "can
you explain how this AI system makes hiring decisions?" is a question HR teams
increasingly can't answer, and it's the literal accountability gap regulators are
fining for (see the €14M credit-scoring "black box" case above). Reuses the plain-
language state explanations and citation click-through already built.

## Phase L — CI/API compliance check (M)
**Independent.** Everything so far is a web form for a compliance officer. Engineering
teams have a different complaint: GRC tooling built for quarterly audits collides with
weekly release cycles, and the friction pushes teams toward "shadow AI" that bypasses
governance entirely. A thin API wrapping the existing classification pipeline, callable
from CI, targets that buyer directly — "does this change alter the system's risk
classification" as a merge-gate check, not a form to fill out after the fact.

## Buyer personas this now covers, and which phases serve them

- **Compliance officer at an SME** (the original target): A, B, D, E, F, G, H
- **Founder preparing for VC due diligence**: C (a document to hand an investor,
  fast) — a different urgency than an ongoing governance program; investors explicitly
  ask about human-in-the-loop, incident response, and who owns AI compliance
- **HR/non-technical staff fielding a real question**: K
- **Engineering team shipping weekly**: L

---

## Suggested build order

1. **A → B** (foundation + the one genuinely novel differentiator, both cheap)
2. **C** (closes a confirmed market gap, no dependencies, cheap, also serves the
   fundraising-due-diligence persona directly)
3. **K** (cheap, reuses existing logic, opens a second persona for ~S effort)
4. **D, E** (natural extensions of A, moderate effort)
5. **F** (biggest real cost-reduction for actual users, independent)
6. **G → H** (biggest lift, only worth it once ready for real multi-user/production use)
7. **I, J, L** (independent, do whenever — I is nearly free, J is content work, L opens
   the engineering-team persona whenever there's appetite for an API surface)
