# Architecture

Modular monolith, Python 3.12 + FastAPI. See `.claude/rules/architecture.md` for the constraints this must satisfy.

## Module layout

```
src/
  legal/          # legal knowledge domain: sources, provisions, requirements, versioning (deterministic, no LLM)
  facts/          # fact extraction from user input/evidence (LLM-assisted, schema-validated)
  classification/ # scope/prohibited/high-risk/GPAI/transparency assessors (LLM + deterministic rule engine)
  evidence/       # evidence assessment against requirements (LLM-assisted)
  obligations/    # deterministic mapping: classification -> obligations (rule tables, no LLM)
  gaps/           # deterministic diff: obligations vs evidence -> gaps
  review/         # human-review routing rules (deterministic triggers)
  reporting/      # compliance report assembly (no new legal conclusions)
  llm/            # provider-agnostic LLM client interface + structured-output enforcement
  retrieval/      # hybrid retrieval over legal corpus: exact article/annex lookup + semantic search
  api/            # FastAPI routers, request/response schemas
  web/            # Jinja2 + HTMX templates, minimal forms
  persistence/    # SQLAlchemy models, migrations (Alembic), tenant-scoped queries
  observability/  # structured logging, assessment-trace reconstruction
schemas/          # Pydantic/JSON Schema for every LLM structured output
prompts/          # versioned prompt templates per role
legal/            # ingested legal source documents + structured requirement records (versioned)
evals/            # golden dataset, adversarial cases, eval harness, regression runner
tests/            # unit / integration / contract, mirrors src/ structure
```

## Boundaries that must hold

- `legal/`, `obligations/`, `gaps/`, `review/` never import `src/llm` — these are deterministic-only. Enforce with an import-boundary test once those modules have code in them.
- `schemas/` sits above `src/`, not inside it — prompts, eval harness, and API layer all validate against the same versioned contract.
- No vector database until eval data shows semantic recall is the bottleneck. Legal corpus at MVP scale fits in relational tables with full-text search.
- Storage via SQLAlchemy (Postgres in prod, SQLite for local dev). Every row carries `tenant_id` from the start.
- Web UI is server-rendered (Jinja2 + HTMX) — no separate frontend build/toolchain until UI complexity requires it.

Full rationale and the phased build order live in the architecture assessment that preceded this scaffold (see project history / plan record).
