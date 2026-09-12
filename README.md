# EU AI Act Compliance Platform

A compliance-intelligence system for the EU AI Act (Regulation (EU) 2024/1689): given a
description of an AI system, it classifies the system against the Act, maps the
obligations that attach, assesses submitted evidence against those obligations, and
produces a compliance report with citations, gaps, and human-review flags.

Built to a production-grade mandate, not a demo: legal text is never invented, every
conclusion traces back to a verbatim source citation, and the pipeline is designed
around one hard rule — deterministic code decides facts, dates, and business rules; an
LLM is only used where genuine interpretation is required, and even then its output is
schema-validated and fails closed on doubt.

**Open source and self-hostable.** The commercial AI-governance platforms covering the
EU AI Act (Credo AI, Holistic AI, OneTrust AI Governance) are closed-source,
custom-quoted enterprise sales (commonly $30K-150K+/year, no free or self-serve tier) —
out of reach for the SMEs the Act itself estimates spend €50K-500K just on per-system
compliance. This is MIT-licensed and runs on your own infrastructure with your own
Anthropic key.

## Pipeline

```
Legal sources (EUR-Lex, verbatim)
  -> structured requirements (versioned, provenance-tracked)
  -> facts (from a web form today)
  -> classification (5 independent categories: scope, prohibited practices,
     high-risk, GPAI, transparency)
  -> obligation mapping (deterministic: classification -> Articles 9-15)
  -> evidence assessment (LLM-assisted, 7 dimensions, never "a policy exists = compliant")
  -> gap analysis (deterministic: anything not COMPLIANT is a gap)
  -> human review routing (deterministic triggers)
  -> compliance report (no new legal conclusions introduced at this stage)
```

Every stage is a separate, independently-tested module — see `docs/architecture.md`.

## What makes this different from "wrap an LLM in a form"

- **Citations are structurally required, not prompted for.** A classification of
  YES/POSSIBLY literally cannot be constructed without at least one cited
  `requirement_key` — enforced by a Pydantic validator, not prompt wording. Every
  citation is also checked against the actual retrieved candidate set; an unverifiable
  citation fails the response closed to `INSUFFICIENT_INFORMATION`.
- **Legal text is fetched, not written from memory.** Every ingested article/annex is
  pulled verbatim from EUR-Lex via a plain HTTP fetch and regex tag-strip — no LLM in
  the extraction path. See `docs/legal-methodology.md`.
- **Uncertainty is a first-class result.** `POSSIBLY`, `INSUFFICIENT_INFORMATION`, and
  `NOT_APPLICABLE` are distinct, deliberately-used states — including a genuine
  distinction between "we don't have enough facts" and "this legal requirement isn't in
  force yet as of this date," which are different things.
- **Every assessment is reconstructable — and browsable.** Facts, classification,
  obligations, evidence, LLM call metadata (model, prompt version, tokens, latency), and
  errors are all persisted (`src/observability/`) and viewable later at a permanent
  `/assessments/<id>` URL, with a `/history` page listing every past run.
- **Citations link to the actual verbatim law**, not a bare code. Click a citation
  in the UI and the exact quoted Article/Annex text is right there — the same text
  ingested from EUR-Lex, not a paraphrase.
- **It's been adversarially tested**, not just happy-path tested: prompt injection,
  forced-binary pressure, conflicting actor roles, citation-bypass attempts, and
  outdated/superseded legal sources all have dedicated tests. See
  `evals/adversarial/README.md` for the full coverage map against the
  `adversarial-testing` skill's checklist.

## Try it without logging in

`/hiring-ai-check` is a standalone, public, no-auth page: describe a hiring/recruitment
tool in one sentence, get one plain-English answer with a citation — no setup, no
credentials. It's the committed starting niche (see `ROADMAP.md`), not the full
workflow; it hands off to the full authenticated assessment for obligations and
evidence tracking once a system is flagged high-risk.

## Scope

Legal corpus covers a representative, not exhaustive, slice: Article 5 (prohibited
practices), Article 6 + Annex III (high-risk classification), Articles 9-15 (high-risk
obligations). GPAI and transparency obligations, deployer-side obligations, and most of
the Regulation's ~180 articles are not yet ingested — the pipeline correctly returns
`INSUFFICIENT_INFORMATION` for those categories rather than guessing. See
`docs/legal-methodology.md`'s "What's deliberately out of scope" section.

## Docs

| Doc | Covers |
|---|---|
| `docs/architecture.md` | Module layout and the boundaries that must hold |
| `docs/legal-methodology.md` | Sourcing method, granularity decisions, versioning |
| `docs/security-model.md` | Threat model, defenses, what's explicitly out of scope |
| `evals/README.md` | Evaluation strategy across all three test suites |
| `prompts/README.md` | Prompt versioning and role-by-role status |

## Running locally

```
uv sync --frozen --extra dev
uv run alembic upgrade head
uv run python scripts/seed_legal_corpus.py
APP_USERNAME=<user> APP_PASSWORD=<password> ANTHROPIC_API_KEY=<key> uv run uvicorn src.api.main:app --reload
```

`APP_USERNAME`/`APP_PASSWORD` gate every assessment route via HTTP Basic Auth; the
server refuses to serve without them. `ANTHROPIC_API_KEY` is read by the `anthropic`
SDK directly — omit it to fail fast at classification time rather than starting with a
broken LLM client. `/assess` and `/report` are rate-limited (10 requests/60s per IP);
`/hiring-ai-check` is public and rate-limited harder (3 requests/60s per IP) since it
has no auth barrier at all — see `docs/security-model.md`.

Run `python scripts/purge_expired_assessments.py` periodically (e.g. via cron) to
enforce the assessment data retention window (default 90 days).

## Testing

```
uv run pytest
```

140 tests: unit/integration tests per module, 16 classification + 8 evidence golden
cases, and the adversarial suite — all offline via a fake LLM provider, so CI never
needs a live API key. See `evals/README.md` for what these suites do and don't prove.

## License

MIT — see `LICENSE`.
