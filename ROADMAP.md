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

## Phase A — AI system registry (S/M) — **delivered**
**Unlocks:** B, D, E, and makes the history page group by system instead of a flat list.

New `AISystem` table (name, description, owner note, created_at); `AssessmentRecord`
gets a nullable `ai_system_id` FK, so every historical assessment stays valid ungrouped.
The assessment form gets an optional "AI system" field (autocompleted against existing
names via a datalist); naming it at submission time gets-or-creates the `AISystem` by
exact name and links the new assessment to it. `/history` is now "My AI Systems" --
grouped by system, with an "Ungrouped" section for one-off checks -- and each system
gets its own permalink (`/systems/{id}`) showing just its assessment history. See
`src/systems/registry.py`.

## Phase B — Regulatory update alerts (S) — **delivered**
**Depended on:** A. Reused the versioning infra (`supersede_requirement`,
`superseded_by_id`) from Phase 1 for the first time for something user-facing.

No assessment stores which exact requirement *version* it cited (only the stable
`requirement_key`, since citations only ever come from the live, non-superseded row at
query time) -- so "outdated" is inferred from timestamps instead: if a requirement_key
has a version created after an AI system's latest assessment ran, that assessment's
conclusion may be outdated. See `src/legal/update_alerts.py`. Surfaced as an "Update
available" badge next to the system on `/history`, and a full banner ("this conclusion
may be outdated — a newer version of X exists") on that system's `/systems/{id}` page.
No competitor surfaced in the research does this because most tools don't track
requirement versions at all, let alone diff against a user's past conclusions.

## Phase C — Auto-generated Impact Assessment / export (S) — **delivered**
`ComplianceReport` already had every field needed -- no new backend logic, just a new
document-style template (`/assessments/{id}/impact-assessment`) restating the same
already-established results (system description, classification, obligations +
crosswalks, evidence status, gaps, recommended actions, review flags) in a formal,
numbered-section layout instead of the compact web report. Print-friendly CSS
(`@media print` in `base.html`) hides the nav/toolbar so the browser's own "print to
PDF" produces a clean document -- no new dependency. Directly answers a gap the
research confirmed nobody in the market has solved ("no platform generates AI Impact
Assessments for you").

## Phase D — Deadlines dashboard + drift-triggered reassessment (S/M) — **dashboard half delivered**
**Depended on:** A. `/deadlines` aggregates, per AI system: re-assessment due date
(latest `as_of` + 12 months -- a product default, not itself an AI Act requirement),
and any `NOT_APPLICABLE` classification that will flip to applicable on a known future
date, computed from the same `ApplicabilityCondition.temporal_start` rows Article 113's
dates were seeded into (Phase 1). One view instead of checking each system. See
`src/legal/deadlines.py`.

Sharper than a calendar reminder alone: orgs that catch AI issues via internal
monitoring hit 87.5% compliance vs. 5.3% for externally-detected incidents — the real
problem isn't "the assessment is old," it's "did the underlying system change."
**Not yet delivered:** drift-triggered reassessment (prompting a re-classification when
a system's description/facts are edited) -- there's no facts-editing feature on an
`AISystem` yet for an edit to trigger from. The dashboard's due-date half stands on its
own; this half is still open.

## Phase E — Incident logging, Article 73 (M) — **delivered**
**Depended on:** A (an incident belongs to a system). New `Incident` table, deadline
countdown, reported/not-reported state, surfaced on each AI system's `/systems/{id}`
page (log a new incident, see open ones with their deadline and citation, mark
reported).

Article 73's actual text has three deadline tiers, not two -- verified against the
verbatim text rather than assumed from this roadmap's original two-tier description:
**15 days** by default (Art 73(2)); **10 days** for death or serious health harm (Art
73(4), citing Art 3(49)(a)); **2 days** for critical-infrastructure disruption or
widespread infringement (Art 73(3), citing Art 3(49)(b) and Art 3(61)). Ingested Article
73 plus the two Article 3 definition points it references (not the whole 68-point
Definitions article) into the existing AI Act source. See `src/incidents/registry.py`.

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
**Depends on:** G (**now delivered** -- real users exist to assign to). Turns a `Gap` from a report line
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

## Phase N — NIST AI RMF crosswalk (M) — **delivered**
New `FrameworkCrosswalk` table (`requirement_id` -> framework name + citation + verbatim
text) maps the 7 AI Act Article 9-15 obligations and the 2 GDPR obligations to 9 NIST AI
RMF 1.0 subcategories across GOVERN/MAP/MEASURE (ART15 crosswalks to two MEASURE
subcategories, since it covers accuracy/robustness/cybersecurity as distinct
properties). Shown as an additional citation on the same obligation card in the report,
not a separate assessment. Only the crosswalked subcategories were ingested, not the
full 72-subcategory framework — see `docs/legal-methodology.md`.

## Phase O — NIST CSF crosswalk (S/M) — **delivered**
Reused Phase N's `FrameworkCrosswalk` table with a second `framework_name` ("NIST CSF
2.0"). Narrower scope than N, as planned: CSF is general cybersecurity guidance, not
AI-specific, so it only crosswalks against `EU-AI-ACT-ART15` (accuracy/robustness/
cybersecurity) -- 2 subcategories (`ID.RA-01`: vulnerability identification,
`PR.IR-03`: resilience in normal/adverse situations), not spread across all 9 AI
Act/GDPR obligations. `ART15` now carries crosswalk entries from both frameworks side
by side in the report.

With M, N, and O all delivered, the full public-domain multi-framework scope from the
"Multi-framework scope" section above is complete: GDPR obligations plus NIST AI RMF
and NIST CSF crosswalks, all verbatim-sourced, all citation-enforced, zero paid
licenses.

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

1. **A → B** (foundation + the one genuinely novel differentiator, both cheap) — **delivered**
2. **C** (closes a confirmed market gap, no dependencies, cheap, also serves the
   fundraising-due-diligence persona directly) — **delivered**
3. **K** (cheap, reuses existing logic, opens a second persona for ~S effort)
4. **D, E** (natural extensions of A, moderate effort) — **D's dashboard half and E delivered**
5. **F** (biggest real cost-reduction for actual users, independent)
6. **G → H** (biggest lift, only worth it once ready for real multi-user/production use)
   — **G delivered**
7. **M** (GDPR — highest-leverage framework addition, directly overlaps existing
   high-risk obligations, same ingestion method already proven)
8. **N → O** (NIST crosswalks — cheap once M exists to crosswalk against, closes the
   "no unified cross-framework register" gap the research confirmed nobody has solved)
9. **I, K, L** (independent, do whenever — I is nearly free, L opens the
   engineering-team persona whenever there's appetite for an API surface)
