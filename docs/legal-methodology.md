# Legal Methodology

## Sourcing

Legal text is fetched directly from EUR-Lex (`https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:<id>`)
via a plain HTTP GET, then boundaries between articles/annexes are located by exact
heading-text search in the stripped HTML. **No LLM is used anywhere in the extraction
path** — this avoids paraphrase or hallucination risk in what is supposed to be verbatim
legal text (`.claude/rules/legal-reasoning.md`: "never invent an article, annex,
obligation, deadline, exception, or interpretation").

Each ingested slice records:
- the CELEX ID and OJ reference
- the raw fetch's SHA-256 hash (so a re-fetch can be diffed against what was actually ingested)
- the retrieval timestamp and method (`automated_fetch_verbatim_extraction`)
- the exact source URL

See `legal/sources/eu_ai_act_2024_1689/metadata.json` for the full record.

## Granularity

- **LegalProvision**: article- or annex-level in this seed slice (Article 5, Article 6,
  Annex III, and Articles 9-15, one row each). Point-level provision splitting (e.g. a
  row per Article 5(1) point) is deferred — the current `Requirement` layer already
  provides point-level addressability by citing the same parent provision, which is
  sufficient for Phase 1-4's query needs. Revisit if a future phase needs to cite
  point-level text independently of its article.
- **Requirement**: one row per distinct legal rule an assessment needs to reason about —
  one per Article 5(1) prohibited-practice point (a-h), one per Article 6 classification
  pathway (6(1) product-safety route, 6(2)/(3) Annex-III route with its derogation), one
  per Annex III numbered area (1-8), and one per Article 9-15 high-risk obligation
  (Phase 4). Each has a stable `requirement_key` (`EU-AI-ACT-<citation>[-<point>]`) that
  survives future legal-text amendments.

## Requirement summaries

`Requirement.summary` is an engineer-authored restatement of the verbatim provision it
cites, written during ingestion — not LLM-generated. Every summary is traceable to
`primary_provision_id`, whose `text` field is authoritative. Downstream consumers
(classification, reporting) must cite the provision text, not just the summary, per
`.claude/rules/legal-reasoning.md` ("distinguish legal requirements from implementation
recommendations").

## Effective dates

Application dates come from Article 113 ("Entry into force and application"), quoted
verbatim in `metadata.json`. Three dates matter for this seed slice:
- **2025-02-02** — Chapters I and II (includes Article 5, prohibited practices)
- **2026-08-02** — general application date (covers Article 6(2)/(3) and Annex III)
- **2027-08-02** — Article 6(1) and its corresponding obligations specifically

`ApplicabilityCondition.temporal_start` is set per-requirement from these three dates,
not a single blanket date — this is why `find_requirements(as_of=...)` correctly excludes
Annex III requirements when queried against a date before 2026-08-02 even though Article 5
prohibitions are already in force.

## Versioning

A legal amendment never overwrites a `Requirement` row. `src/legal/versioning.py:supersede_requirement`
creates a new row with `version = old.version + 1`, sets `old.superseded_by_id`, and leaves
the old row's `summary`/`primary_provision_id` untouched — so a historical assessment that
cited the old version remains fully reconstructable. Same pattern applies to
`LegalProvision` for future article-text amendments (not yet exercised — no amendment has
occurred against this seed slice).

## Obligation mapping basis (Phase 4)

Articles 9-15 (Chapter III, Section 2, "Requirements for high-risk AI systems") were
added to the seed slice specifically because `src/obligations/` needs a legal basis for
what obligations attach to a `high_risk=YES/POSSIBLY` classification — obligation
mapping cannot invent obligation text any more than classification can invent a
citation. These seven articles were extracted from the *same raw fetch* already made in
Phase 1 (`raw_fetch_sha256` unchanged; see `metadata.json`'s `excerpts_extraction_note`)
— no new HTTP request was needed, since the full regulation text was already captured.

Actor role for these seven requirements is `PROVIDER`: Article 8 (not ingested)
establishes Section 2 as provider obligations; deployer obligations live in Section 3
(Article 26), also not ingested — deployer-side obligation mapping is deferred.

## What's deliberately out of scope for this slice

- The remaining ~170 articles and 13 annexes of the Regulation (GPAI obligations, conformity
  assessment procedures, governance/enforcement chapters, deployer obligations (Article 26),
  Annexes I/II/IV-XIII).
- Commission implementing acts, AI Office guidance, and codes of practice.
- Point-level `LegalProvision` rows for Article 5(1)(a)-(h) and Annex III's numbered areas.
- An automated re-fetch/diff pipeline for legal-source-update (`legal-source-update` skill)
  — today's ingestion is a one-time seed script (`src/legal/ingest.py`), run manually.

These are Phase 7+ work per the approved implementation plan, deferred until the
classification/evidence/reporting pipeline is proven against this representative slice.
