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

## Phase I — "Am I affected?" scope quiz (S) — **partially delivered**
**Independent.** A 5-question, no-login entry point before the full assessment form —
thin wrapper around existing scope/prohibited-practice logic. Lowers the barrier for
the 78% of orgs (per the research) who haven't started because they don't know where
they stand.

`/ai-risk-check` (built) covers the "no-login, near-zero-friction entry" need with a
single free-text question instead of a 5-question quiz — smaller scope than originally
planned here, but shipped. A structured multi-question quiz is still a reasonable
follow-up if the single-question version proves too open-ended for some users.

## Multi-framework scope: public-domain only

Decision (see conversation, not re-litigated here): extend to GDPR, NIST AI RMF, and
NIST CSF — all public-domain government/EU text, verbatim-ingestible the same way
Article 5/6/9-15 were. Explicitly **not** ISO 27001, ISO 42001, or SOC 2's AICPA Trust
Services Criteria — those are copyrighted/paywalled; a layer for them could only
reference clause *numbers*, never quote the actual standard, which is a materially
weaker, different kind of feature than everything else in this system. Skipped, not
deferred — revisit only if someone is willing to pay for the licenses (real recurring
cost, conflicts with the low-cost goal).

The three approved frameworks aren't architecturally identical, so they don't get the
same treatment:

- **GDPR is binding law with its own obligations** — Article 22 (automated
  decision-making) and Article 35 (DPIA) trigger real requirements that are *additional
  to*, not a relabeling of, the AI Act's Article 9-15 obligations. These become new
  `Requirement` rows (same `SourceDocument`/`LegalProvision` model, no schema change
  needed — it was never AI-Act-specific) and `map_obligations` gets extended to add
  them when `high_risk` is YES/POSSIBLY, since a high-risk AI decision about a person is
  almost always also GDPR automated-decision-making.
- **NIST AI RMF and NIST CSF are voluntary frameworks, not obligations** — the value is
  showing "this same obligation also satisfies NIST GOVERN-1.1," not inventing a
  parallel classification pipeline. This needs a new `FrameworkCrosswalk` table
  (`requirement_id` -> framework name + citation + verbatim text) shown alongside the
  existing obligation, not a new obligation of its own. This is the concrete answer to
  the confirmed research gap: "no platform maintains a single cross-framework register."

## Phase M — GDPR obligations layer (M) — **delivered**
Ingested Article 22 (automated decision-making/profiling) and Article 35 (DPIA) verbatim
— the two GDPR articles most directly overlapping with what's already classified.
Sourced via the EU Publications Office's Cellar repository rather than EUR-Lex directly,
since EUR-Lex's public site now sits behind AWS WAF bot detection (see
`docs/legal-methodology.md`). `map_obligations` extended to add `GDPR-ART22`/`GDPR-ART35`
whenever `high_risk` is YES/POSSIBLY, alongside the existing Article 9-15 obligations.
Article 5 (principles) and Articles 13/14 (transparency) are natural follow-ups, not
required for this first slice.

## Phase N — NIST AI RMF crosswalk (M)
**Depends on:** nothing new — `Requirement` rows already exist to crosswalk against.
Ingest NIST AI RMF's four functions (GOVERN/MAP/MEASURE/MANAGE) verbatim (US government,
public domain). New `FrameworkCrosswalk` table maps existing `EU-AI-ACT-ART9`..`ART15`
(and the new GDPR) requirements to their NIST equivalents. Shown as an additional
citation on the same obligation card, not a separate assessment.

## Phase O — NIST CSF crosswalk (S/M)
**Depends on:** N (reuses `FrameworkCrosswalk`). Narrower scope than N: NIST CSF is
general cybersecurity, not AI-specific, so it only meaningfully crosswalks against
`EU-AI-ACT-ART15` (accuracy/robustness/cybersecurity) rather than all seven obligations.

---

## Phase K — "Explain this rejection" mode (S) — **substantially delivered as `/ai-risk-check`**
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
7. **M** (GDPR — highest-leverage framework addition, directly overlaps existing
   high-risk obligations, same ingestion method already proven)
8. **N → O** (NIST crosswalks — cheap once M exists to crosswalk against, closes the
   "no unified cross-framework register" gap the research confirmed nobody has solved)
9. **I, K, L** (independent, do whenever — I is nearly free, L opens the
   engineering-team persona whenever there's appetite for an API surface)
